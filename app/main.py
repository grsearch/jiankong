from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.clients import load_clients
from app.models import Side, TokenProfile, TradeEvent, TokenRuntime
from app.signal_engine import SignalEngine
from app.state import STATE

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("sol-meme-monitor")

app = FastAPI(title="Sol Meme Monitor")
engine = SignalEngine()
birdeye, helius = load_clients()


class TokenWebhook(BaseModel):
    mint: str = Field(..., min_length=30)
    symbol: str


class TradeWebhook(BaseModel):
    mint: str
    wallet: str
    side: Side
    amount_usd: float
    timestamp: datetime | None = None
    price: float | None = None
    is_bundle_wallet: bool = False
    wallet_roi: float | None = None
    wallet_win_rate: float | None = None
    holder_count: int | None = None
    liquidity_usd: float | None = None


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


async def resolve_holders(mint: str, metrics: dict) -> tuple[int | None, str, dict]:
    birdeye_holders = metrics.get("holders")
    birdeye_path = metrics.get("holders_path")

    # 如果 Birdeye 返回明显异常的小值（常见误字段为1），尝试 Helius 校正。
    if birdeye_holders is not None and birdeye_holders > 1:
        return birdeye_holders, "birdeye", {"holders_path": birdeye_path}

    helius_holders, helius_stats = await helius.get_holder_estimate(mint)

    if birdeye_holders is None and helius_holders is None:
        return None, "unknown", {"holders_path": birdeye_path, **helius_stats}

    if birdeye_holders is None:
        return helius_holders, "helius_estimated", {"holders_path": birdeye_path, **helius_stats}

    if helius_holders is None:
        return birdeye_holders, "birdeye", {"holders_path": birdeye_path, **helius_stats}

    # 两者都存在时取更可信的较大值。
    if helius_holders > birdeye_holders:
        return helius_holders, "helius_estimated", {"holders_path": birdeye_path, **helius_stats}
    return birdeye_holders, "birdeye", {"holders_path": birdeye_path, **helius_stats}


async def update_runtime_holders(runtime: TokenRuntime) -> None:
    metrics = await birdeye.get_token_metrics(runtime.profile.mint)
    holders, source, debug = await resolve_holders(runtime.profile.mint, metrics)
    runtime.profile.fdv_or_mcap = metrics.get("fdv") or metrics.get("mcap")
    runtime.profile.volume_24h = metrics.get("volume_24h")
    runtime.profile.holders = holders
    runtime.profile.holders_source = source
    runtime.profile.holders_path = debug.get("holders_path")
    runtime.profile.holders_refreshed_at = datetime.now(timezone.utc)

    logger.info(
        "[holders] final mint=%s holders=%s source=%s path=%s pages=%s accounts=%s owners=%s",
        runtime.profile.mint,
        holders,
        source,
        runtime.profile.holders_path,
        debug.get("pages"),
        debug.get("accounts"),
        debug.get("owners"),
    )


async def refresh_all_holders() -> int:
    updated = 0
    for runtime in STATE.tokens.values():
        await update_runtime_holders(runtime)
        updated += 1
    await STATE.broadcast({"type": "refresh", "count": updated})
    return updated


@app.on_event("startup")
async def startup_refresh_holders_if_enabled() -> None:
    if not env_flag("AUTO_REFRESH_HOLDERS_ON_START", default=False):
        return
    updated = await refresh_all_holders()
    logger.info("[holders] startup refresh complete updated=%s", updated)


@app.post("/webhook/token")
async def token_webhook(payload: TokenWebhook) -> dict:
    token = TokenProfile(mint=payload.mint, symbol=payload.symbol)
    runtime = STATE.whitelist_token(token)

    await update_runtime_holders(runtime)

    await STATE.broadcast({"type": "token", "mint": payload.mint})
    return {
        "ok": True,
        "mint": payload.mint,
        "holders": runtime.profile.holders,
        "holders_source": runtime.profile.holders_source,
    }


@app.post("/webhook/refresh-holders")
async def refresh_holders() -> dict:
    updated = await refresh_all_holders()
    return {"ok": True, "updated": updated}


@app.get("/api/debug/token/{mint}")
async def api_debug_token(mint: str) -> dict:
    runtime = STATE.tokens.get(mint)
    if not runtime:
        return {"ok": False, "message": "token not found"}
    return {
        "ok": True,
        "mint": mint,
        "symbol": runtime.profile.symbol,
        "holders": runtime.profile.holders,
        "holders_source": runtime.profile.holders_source,
        "holders_path": runtime.profile.holders_path,
        "holders_refreshed_at": runtime.profile.holders_refreshed_at.isoformat()
        if runtime.profile.holders_refreshed_at
        else None,
    }


@app.post("/webhook/trade")
async def trade_webhook(payload: TradeWebhook) -> dict:
    runtime = STATE.tokens.get(payload.mint)
    if not runtime:
        return {"ok": False, "message": "token not whitelisted"}

    event = TradeEvent(
        mint=payload.mint,
        wallet=payload.wallet,
        side=payload.side,
        amount_usd=payload.amount_usd,
        timestamp=payload.timestamp or datetime.now(timezone.utc),
        price=payload.price,
        is_bundle_wallet=payload.is_bundle_wallet,
        wallet_roi=payload.wallet_roi,
        wallet_win_rate=payload.wallet_win_rate,
        holder_count=payload.holder_count,
        liquidity_usd=payload.liquidity_usd,
    )
    runtime.trades.append(event)
    runtime.trades = runtime.trades[-1200:]

    signals = engine.evaluate(runtime)
    bot_url = os.getenv("BOT_WEBHOOK_URL")

    for signal in signals:
        if runtime.signal_history and runtime.signal_history[-1].signal == signal.signal:
            continue
        runtime.signal_history.append(signal)
        runtime.signal_history = runtime.signal_history[-200:]
        STATE.push_signal(signal)
        if bot_url:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    bot_url,
                    json={
                        "token": signal.symbol,
                        "mint": signal.mint,
                        "signal": signal.signal,
                        "detail": signal.detail,
                        "score": signal.score,
                        "created_at": signal.created_at.isoformat(),
                    },
                )

    await STATE.broadcast({"type": "trade", "mint": payload.mint, "signal_count": len(signals)})
    return {"ok": True, "signals": [s.signal for s in signals]}


@app.get("/api/whitelist")
async def api_whitelist() -> list[dict]:
    rows = []
    for rt in STATE.tokens.values():
        rows.append(
            {
                "symbol": rt.profile.symbol,
                "mint": rt.profile.mint,
                "fdv_or_mcap": rt.profile.fdv_or_mcap,
                "holders": rt.profile.holders,
                "holders_source": rt.profile.holders_source,
                "volume": rt.profile.volume_24h,
                "gmgn": f"https://gmgn.ai/sol/token/{rt.profile.mint}",
            }
        )
    return rows


@app.get("/api/signals")
async def api_signals() -> list[dict]:
    return [
        {
            "symbol": s.symbol,
            "mint": s.mint,
            "signal": s.signal,
            "detail": s.detail,
            "score": s.score,
            "created_at": s.created_at.isoformat(),
        }
        for s in STATE.global_signals
    ]


@app.websocket("/ws")
async def ws_updates(ws: WebSocket) -> None:
    await ws.accept()
    queue = asyncio.Queue()
    STATE.listeners.add(queue)
    try:
        while True:
            payload = await queue.get()
            await ws.send_json(payload)
    except WebSocketDisconnect:
        STATE.listeners.discard(queue)

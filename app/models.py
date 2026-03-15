from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass
class TokenProfile:
    mint: str
    symbol: str
    fdv_or_mcap: float | None = None
    holders: int | None = None
    volume_24h: float | None = None
    holders_source: str | None = None
    holders_path: str | None = None
    holders_refreshed_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class TradeEvent:
    mint: str
    wallet: str
    side: Side
    amount_usd: float
    timestamp: datetime
    price: float | None = None
    is_bundle_wallet: bool = False
    wallet_roi: float | None = None
    wallet_win_rate: float | None = None
    holder_count: int | None = None
    liquidity_usd: float | None = None


@dataclass
class SignalRecord:
    mint: str
    symbol: str
    signal: str
    detail: str
    score: float
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


@dataclass
class TokenRuntime:
    profile: TokenProfile
    trades: list[TradeEvent] = field(default_factory=list)
    signal_history: list[SignalRecord] = field(default_factory=list)
    baseline_liquidity: float | None = None

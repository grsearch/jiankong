from __future__ import annotations

import os
from typing import Any

import httpx


class BirdeyeClient:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key
        self.base = "https://public-api.birdeye.so"

    async def get_token_metrics(self, mint: str) -> dict[str, Any]:
        if not self.api_key:
            return {}
        headers = {"X-API-KEY": self.api_key, "x-chain": "solana"}
        async with httpx.AsyncClient(timeout=10) as client:
            price_resp = await client.get(f"{self.base}/defi/price", headers=headers, params={"address": mint})
            overview_resp = await client.get(
                f"{self.base}/defi/token_overview", headers=headers, params={"address": mint}
            )
        price_data = price_resp.json().get("data", {}) if price_resp.status_code == 200 else {}
        overview_data = overview_resp.json().get("data", {}) if overview_resp.status_code == 200 else {}
        return {
            "price": price_data.get("value"),
            "fdv": overview_data.get("fdv"),
            "mcap": overview_data.get("marketCap"),
            "volume_24h": overview_data.get("v24hUSD"),
            "liquidity": overview_data.get("liquidity"),
        }


class HeliusClient:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    async def get_holder_estimate(self, mint: str) -> int | None:
        if not self.api_key:
            return None
        url = f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
        payload = {
            "jsonrpc": "2.0",
            "id": "holders",
            "method": "getTokenAccounts",
            "params": {"page": 1, "limit": 1, "mint": mint},
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            return None
        return resp.json().get("result", {}).get("total")


def load_clients() -> tuple[BirdeyeClient, HeliusClient]:
    return BirdeyeClient(os.getenv("BIRDEYE_API_KEY")), HeliusClient(os.getenv("HELIUS_API_KEY"))

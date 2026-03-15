from __future__ import annotations

import os
from typing import Any


class BirdeyeClient:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key
        self.base = "https://public-api.birdeye.so"

    async def get_token_metrics(self, mint: str) -> dict[str, Any]:
        if not self.api_key:
            return {}
        import httpx

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
            "holders": self._extract_holders_from_overview(overview_data),
        }

    @staticmethod
    def _extract_holders_from_overview(overview_data: dict[str, Any]) -> int | None:
        for key in ("holder", "holders", "holderCount", "holdersCount"):
            value = overview_data.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None


class HeliusClient:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    async def get_holder_estimate(self, mint: str) -> int | None:
        if not self.api_key:
            return None
        import httpx

        url = f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
        owners: set[str] = set()
        page = 1
        max_pages = 20
        async with httpx.AsyncClient(timeout=10) as client:
            while page <= max_pages:
                payload = {
                    "jsonrpc": "2.0",
                    "id": f"holders-{page}",
                    "method": "getTokenAccounts",
                    "params": {
                        "page": page,
                        "limit": 1000,
                        "mint": mint,
                        "displayOptions": {"showZeroBalance": False},
                    },
                }
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    break

                token_accounts, has_more = self._extract_page_accounts(resp.json())
                if not token_accounts:
                    break

                for account in token_accounts:
                    owner = account.get("owner")
                    if owner:
                        owners.add(owner)

                if not has_more:
                    break
                page += 1

        return len(owners) if owners else None

    @staticmethod
    def _extract_page_accounts(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
        result = payload.get("result") or {}
        accounts = result.get("token_accounts") or result.get("accounts") or []
        cursor = result.get("cursor")
        total = result.get("total")
        limit = result.get("limit")
        has_more = bool(cursor)

        if isinstance(total, int) and isinstance(limit, int) and limit > 0:
            page = result.get("page", 1)
            has_more = has_more or (page * limit) < total

        return accounts if isinstance(accounts, list) else [], has_more


def load_clients() -> tuple[BirdeyeClient, HeliusClient]:
    return BirdeyeClient(os.getenv("BIRDEYE_API_KEY")), HeliusClient(os.getenv("HELIUS_API_KEY"))

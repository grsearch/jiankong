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
        holders, holders_path = self._extract_holders_from_overview(overview_data)
        return {
            "price": price_data.get("value"),
            "fdv": overview_data.get("fdv"),
            "mcap": overview_data.get("marketCap"),
            "volume_24h": overview_data.get("v24hUSD"),
            "liquidity": overview_data.get("liquidity"),
            "holders": holders,
            "holders_path": holders_path,
        }

    @classmethod
    def _extract_holders_from_overview(cls, overview_data: dict[str, Any]) -> tuple[int | None, str | None]:
        # NOTE: avoid singular "holder" which may not represent total holder count.
        key_candidates = {"holders", "holdercount", "holderscount", "uniqueholders"}

        def walk(node: Any, path: str) -> tuple[int | None, str | None]:
            if isinstance(node, dict):
                for key, value in node.items():
                    key_norm = str(key).lower()
                    next_path = f"{path}.{key}" if path else str(key)
                    if key_norm in key_candidates:
                        parsed = cls._parse_positive_int(value)
                        if parsed is not None:
                            return parsed, next_path
                    parsed, parsed_path = walk(value, next_path)
                    if parsed is not None:
                        return parsed, parsed_path
            elif isinstance(node, list):
                for i, value in enumerate(node):
                    parsed, parsed_path = walk(value, f"{path}[{i}]")
                    if parsed is not None:
                        return parsed, parsed_path
            return None, None

        return walk(overview_data, "data")

    @staticmethod
    def _parse_positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None


class HeliusClient:
    def __init__(self, api_key: str | None) -> None:
        self.api_key = api_key

    async def get_holder_estimate(self, mint: str) -> tuple[int | None, dict[str, int]]:
        if not self.api_key:
            return None, {"pages": 0, "accounts": 0, "owners": 0}
        import httpx

        url = f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
        owners: set[str] = set()
        page = 1
        max_pages = 20
        total_accounts = 0
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

                total_accounts += len(token_accounts)
                for account in token_accounts:
                    owner = self._extract_owner(account)
                    if owner:
                        owners.add(owner)

                if not has_more:
                    break
                page += 1

        stats = {"pages": page, "accounts": total_accounts, "owners": len(owners)}
        return (len(owners) if owners else None), stats

    @staticmethod
    def _extract_owner(account: dict[str, Any]) -> str | None:
        owner = account.get("owner")
        if isinstance(owner, str) and owner:
            return owner
        nested = account.get("token_info") or account.get("tokenInfo") or {}
        nested_owner = nested.get("owner")
        if isinstance(nested_owner, str) and nested_owner:
            return nested_owner
        return None

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

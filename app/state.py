from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Coroutine
from typing import Any

from app.models import SignalRecord, TokenProfile, TokenRuntime


class AppState:
    def __init__(self) -> None:
        self.tokens: dict[str, TokenRuntime] = {}
        self.global_signals: deque[SignalRecord] = deque(maxlen=300)
        self.listeners: set[asyncio.Queue] = set()
        self.background_tasks: set[asyncio.Task[Any]] = set()

    def whitelist_token(self, token: TokenProfile) -> TokenRuntime:
        existing = self.tokens.get(token.mint)
        if existing:
            existing.profile.symbol = token.symbol
            return existing
        runtime = TokenRuntime(profile=token)
        self.tokens[token.mint] = runtime
        return runtime

    def push_signal(self, signal: SignalRecord) -> None:
        self.global_signals.appendleft(signal)

    async def broadcast(self, payload: dict) -> None:
        for q in list(self.listeners):
            await q.put(payload)

    def spawn_task(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)


STATE = AppState()

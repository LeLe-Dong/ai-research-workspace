"""In-memory event bus for SSE real-time streaming.

Bridges the agent executor (which writes to the DB) to the SSE endpoint
(which streams to the browser). Without this, SSE would need to poll the
DB at tight intervals to feel "real-time"; with this, events are pushed
the moment they're committed.

Per-research asyncio.Queue:
- Executor: `await bus.publish(research_id, "timeline", evt_dict)`
- SSE:     `async for kind, payload in bus.subscribe(research_id): yield ...`

Lifecycle:
- Queue created lazily on first publish
- Queue kept for 5 minutes after last activity (so late SSE clients
  that connect after the agent finished can still drain catch-up via DB)
- Purged on memory pressure (LRU cap = 256)
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, AsyncIterator


class _ResearchBus:
    """One research's stream of typed envelopes."""

    __slots__ = ("queue", "last_used", "closed")

    def __init__(self) -> None:
        self.queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        self.last_used: float = time.monotonic()
        self.closed: bool = False

    def touch(self) -> None:
        self.last_used = time.monotonic()


class EventBus:
    """Global registry of per-research event buses."""

    _TTL_SECONDS = 300.0  # keep idle queues 5 min after last use
    _MAX_BUSES = 256       # cap to bound memory

    def __init__(self) -> None:
        # LRU-ordered: most-recently-used at the right end.
        self._buses: "OrderedDict[str, _ResearchBus]" = OrderedDict()
        self._lock = asyncio.Lock()

    async def publish(self, research_id: str, kind: str, payload: dict) -> None:
        """Push one envelope to a research's queue. Creates the bus if needed."""
        async with self._lock:
            bus = self._buses.get(research_id)
            if bus is None:
                bus = _ResearchBus()
                self._buses[research_id] = bus
                self._evict_if_needed()
            else:
                self._buses.move_to_end(research_id)
            bus.touch()
            await bus.queue.put((kind, payload))

    async def subscribe(self, research_id: str) -> AsyncIterator[tuple[str, dict]]:
        """Yield envelopes as they arrive. Caller-side timeout via generator."""
        async with self._lock:
            bus = self._buses.get(research_id)
            if bus is None:
                bus = _ResearchBus()
                self._buses[research_id] = bus
            else:
                self._buses.move_to_end(research_id)
        while True:
            try:
                kind, payload = await asyncio.wait_for(bus.queue.get(), timeout=1.0)
                bus.touch()
                yield kind, payload
            except asyncio.TimeoutError:
                # Periodic touch so the bus stays warm while SSE is connected
                bus.touch()
                yield "__heartbeat__", {"ts": time.time()}

    async def close_research(self, research_id: str) -> None:
        """Signal end-of-stream to consumers (e.g., research completed)."""
        async with self._lock:
            bus = self._buses.get(research_id)
            if bus and not bus.closed:
                bus.closed = True
                await bus.queue.put(("__end__", {"reason": "closed"}))

    def _evict_if_needed(self) -> None:
        """Drop the least-recently-used idle buses beyond MAX_BUSES."""
        while len(self._buses) > self._MAX_BUSES:
            rid, bus = next(iter(self._buses.items()))
            # Only evict if truly idle (TTL expired)
            if time.monotonic() - bus.last_used < self._TTL_SECONDS:
                # Active bus; stop evicting to avoid dropping a live stream
                return
            del self._buses[rid]


# Singleton shared across the FastAPI process
event_bus = EventBus()
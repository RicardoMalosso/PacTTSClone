"""Process-local notifications. SQLite remains authoritative; reconnects resync.

Only the latest value of each topic is retained. A slow/disconnected consumer
cannot accumulate an unbounded queue or block an integration/worker thread.
"""

import asyncio
import json
import logging
import threading
import time

logger = logging.getLogger(__name__)


class EventDispatcher:
    def __init__(self):
        self.lock = threading.Lock()
        self.revision = 0
        self.latest = {}
        self.dirty = set()
        self.connections = 0
        self.closed = False

    def invalidate(self, kind):
        with self.lock:
            self.dirty.add(kind)

    def changes(self):
        with self.lock:
            changes, self.dirty = self.dirty, set()
            return changes

    def publish(self, topic, value):
        # Serialize in the producer, once, so later mutation cannot alter an event.
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self.lock:
            previous = self.latest.get(topic)
            if previous and previous[1] == payload:
                return
            self.revision += 1
            self.latest[topic] = (self.revision, payload)

    def read(self, cursor):
        with self.lock:
            return self.revision, sorted(
                (revision, topic, payload)
                for topic, (revision, payload) in self.latest.items()
                if revision > cursor
            )

    async def stream(self, request):
        with self.lock:
            self.connections += 1
            cursor = self.revision
        try:
            # Always resync, including Last-Event-ID from a previous process. This
            # is a latest-state stream, not a durable event/command replay log.
            yield 'retry: 3000\nevent: sync\ndata: {}\n\n'
            # REST supplies the baseline; the captured cursor covers changes
            # made while that synchronization is in flight.
            heartbeat = time.monotonic()
            while not self.closed and not await request.is_disconnected():
                cursor, events = self.read(cursor)
                for revision, topic, payload in events:
                    yield f"id: {revision}\nevent: {topic}\ndata: {payload}\n\n"
                if time.monotonic() - heartbeat >= 10:
                    yield 'event: heartbeat\ndata: {}\n\n'
                    heartbeat = time.monotonic()
                await asyncio.sleep(0.25)
        finally:
            with self.lock:
                self.connections -= 1


class DashboardEvents:
    """One sampler for all browsers; expensive snapshots never run per client."""

    def __init__(self, dispatcher, state, resources, setup, studio, tunnel, updater):
        self.events = dispatcher
        self.state = state
        self.resources = resources
        self.setup = setup
        self.studio = studio
        self.tunnel = tunnel
        self.updater = updater
        self.task = None
        self.previous_transient = None
        self.versions = {}

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def close(self):
        self.events.closed = True
        if self.task:
            # Let any to_thread snapshot finish before SQLite/services close.
            await self.task

    def sample(self, periodic):
        changes = self.events.changes()
        if periodic:
            studio, service = self.studio, self.studio.service
            with studio.playback.lock:
                players = {
                    name: lease["until"] > studio.playback.clock()
                    for name, lease in studio.playback.leases.items()
                }
            transient = json.dumps([
                [(c["name"], c["connection"], c["connection_error"], c["event_connection"],
                  c["event_connection_error"], c["oauth_authorized"], c["event_errors"])
                 for c in studio.channels()],
                players, studio.playback.panic_revision, studio.hotkey.status,
                service.active_id, getattr(service.runner, "model_state", {}),
                service.runner.pid, service.settings.engine_id, service.setup_ready(),
            ], sort_keys=True)
            if transient != self.previous_transient:
                changes.add("connections")
                self.previous_transient = transient
            self.events.publish("resources", self.resources())
            self.events.publish("setup", self.setup.snapshot())
            self.events.publish("discord", studio.discord.snapshot())
            self.events.publish("tunnel", self.tunnel.snapshot())
            self.events.publish("updates", self.updater.snapshot())
        if changes:
            for kind in changes:
                self.versions[kind] = self.versions.get(kind, 0) + 1
            # Cumulative versions let slow consumers notice every changed section
            # even if intermediate state frames were coalesced away.
            self.events.publish("state", {"value": self.state(), "versions": self.versions})

    async def run(self):
        next_sample = 0
        while not self.events.closed:
            if self.events.connections:
                periodic = time.monotonic() >= next_sample
                try:
                    await asyncio.to_thread(self.sample, periodic)
                    self.events.publish("stream_health", {"available": True})
                except Exception:
                    # A failed monitor must never stop generation/integrations.
                    # Browser freshness watchdog switches to REST until recovery.
                    logger.exception("Dashboard event sampling failed")
                    self.events.invalidate("connections")
                    self.events.publish("stream_health", {"available": False})
                if periodic:
                    next_sample = time.monotonic() + 2
            await asyncio.sleep(0.25)

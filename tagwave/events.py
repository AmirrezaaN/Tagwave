"""Tiny publish/subscribe bus feeding the UI's Server-Sent-Events stream."""

from __future__ import annotations

import json
import queue
import threading


class EventBus:
    def __init__(self):
        self._subs: list = []
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=10000)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, kind: str, data=None) -> None:
        payload = json.dumps({"type": kind, "data": data}, ensure_ascii=False)
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(payload)
            except queue.Full:
                pass

"""How fast a batch is moving and how long it has left, from the bytes
moved over the last few seconds."""
from __future__ import annotations

import time
from collections import deque
from typing import Callable

from .panes import human_size

WINDOW_S = 5.0  # Seconds of samples the speed is measured over.
MIN_S = 1.0     # Less than this measured says nothing: the first blocks go at once into the network buffer.


class RateMeter:
    def __init__(self, window: float = WINDOW_S, clock: Callable[[], float] = time.monotonic) -> None:
        self.window = window
        self.clock = clock
        self.start(0)

    def start(self, total: int) -> None:
        """A new batch of total bytes."""
        self.total = total
        self.done = 0
        self.skipped = 0  # Bytes of files already there: done, but not moved.
        self.samples: deque[tuple[float, int]] = deque([(self.clock(), 0)])

    def skip(self, size: int) -> None:
        """A file of size bytes was skipped; the next update includes it."""
        self.skipped += size

    def update(self, done: int) -> None:
        """done: bytes of the batch done so far, skipped files included."""
        now = self.clock()
        self.done = done
        self.samples.append((now, done - self.skipped))
        while len(self.samples) > 2 and now - self.samples[1][0] >= self.window:
            self.samples.popleft()

    def speed(self) -> float | None:
        """Bytes per second, or None until there's something to measure."""
        (t0, moved0), (t1, moved1) = self.samples[0], self.samples[-1]
        if t1 - t0 < MIN_S or moved1 <= moved0:
            return None
        return (moved1 - moved0) / (t1 - t0)

    def remaining(self) -> float | None:
        """Seconds left at the current speed."""
        speed = self.speed()
        return None if speed is None else max(self.total - self.done, 0) / speed


def duration(seconds: float) -> str:
    seconds = round(seconds)
    if seconds < 5:
        return "a few seconds"
    if seconds < 60:
        return f"{seconds} s"
    if seconds < 3600:
        return f"{seconds // 60} min {seconds % 60} s"
    return f"{seconds // 3600} h {seconds % 3600 // 60} min"


def describe(done: int, total: int, speed: float | None, remaining: float | None) -> str:
    """'11.7 MB of 1.1 GB · 3.9 MB/s · 4 min 50 s left'."""
    parts = [f"{human_size(done)} of {human_size(total)}"]
    if speed is not None:
        parts.append(f"{human_size(speed)}/s")
    if remaining is not None:
        parts.append(f"{duration(remaining)} left")
    return " · ".join(parts)

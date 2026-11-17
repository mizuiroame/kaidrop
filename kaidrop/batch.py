"""A batch of transfers and its rows in the queue, and what's left of it
after the connection was lost, to continue once reconnected."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from .ftp import Status

# Rows that ended like this are done; any other (failed, or never reached)
# goes again when the batch continues.
DONE = {Status.SENT, Status.SKIPPED, Status.COPY, Status.CANCELLED}


@dataclass(frozen=True)
class Batch:
    kind: str               # "up" or "down".
    plan: Any               # A Plan (up) or a DownloadPlan (down).
    rows: tuple[str, ...]   # The queue row of each of the plan's items.
    folder: Any             # Where it goes: a server folder (up) or a Path (down).


def leftover(batch: Batch, ended: dict[str, Status]) -> Batch | None:
    """The batch's items that didn't end done, with their rows; None if all did."""
    keep = [i for i, row in enumerate(batch.rows) if ended.get(row) not in DONE]
    if not keep:
        return None
    return replace(batch, plan=replace(batch.plan, items=tuple(batch.plan.items[i] for i in keep)),
                   rows=tuple(batch.rows[i] for i in keep))

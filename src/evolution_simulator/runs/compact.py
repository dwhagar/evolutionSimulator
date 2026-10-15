"""Compacting a run file (``STORE.3``): a full ``VACUUM`` that never leaves the run half-done.

Retention and ``incremental_vacuum`` already give freed pages back, so a run file stays close to the
size of what it holds; compacting also rewrites it from scratch (no free pages, tables and indexes
packed in order), which is worth doing once after a lot was deleted or an old run was imported.

The file is never changed in place. The steps, and what an interruption at each one leaves:

1. Take the writer's claim in ``meta`` (refused if a program that is running holds it). Nothing but
   this one row changes; a claim left by a program that died is ignored, so a crash from here on
   leaves the run as it was.
2. ``VACUUM INTO`` a new file beside it (``run.sqlite.compact``). The run file is untouched; a crash
   leaves a stray copy that the next attempt deletes.
3. Check the copy: ``integrity_check``, the schema numbers, and the same rows in every table and the
   same bytes in the checkpoint blobs. Then clear the claim in the copy and fold its WAL in, which
   also syncs it to disk.
4. Close the original (its WAL is emptied; one that cannot be emptied because another program is
   reading stops the swap) and ``os.replace`` the copy over it. The swap is one rename: the folder has
   the old file or the new one, never a mixture.

The blobs are copied as bytes, so nothing here depends on how a world or a recorder is written.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evolution_simulator.runs.database import RunFile
from evolution_simulator.runs.errors import RunError

log = logging.getLogger(__name__)

SUFFIX = ".compact"
SIDE_FILES = ("-wal", "-shm", "-journal")


@dataclass(frozen=True, slots=True)
class Compacted:
    run_id: str
    before: int
    """Bytes the run file took (with its WAL) before."""
    after: int

    @property
    def saved(self) -> int:
        return self.before - self.after


def file_size(path: Path) -> int:
    """The run file and its WAL, in bytes."""
    total = 0
    for suffix in ("", "-wal"):
        with contextlib.suppress(OSError):
            total += Path(str(path) + suffix).stat().st_size
    return total


def _remove_with_side_files(path: Path) -> None:
    for suffix in ("", *SIDE_FILES):
        with contextlib.suppress(OSError):
            Path(str(path) + suffix).unlink()


def compact_file(
    path: Path, run_id: str, claim: Mapping[str, Any], alive: Callable[[int], bool]
) -> Compacted:
    """Compact the run file at ``path`` (see the module note). ``claim`` is what is written to
    ``meta.writer`` while it is done; ``alive`` says whether a process id is still running."""
    temp = path.with_name(path.name + SUFFIX)
    _remove_with_side_files(temp)  # what an earlier attempt that was cut short left behind
    before = file_size(path)
    source = RunFile.open(path)
    try:
        source.claim(claim, alive)
    except BaseException:
        source.close()
        raise
    swapped = False
    try:
        source.vacuum_into(temp)
        _check_copy(source, temp)
        source.settle()
        source.close()  # the claim stays in the old file, which is about to be replaced
        _swap(temp, path)
        swapped = True
    finally:
        if not swapped:
            _release(source, path)
            _remove_with_side_files(temp)
    return Compacted(run_id, before, file_size(path))


def _check_copy(source: RunFile, temp: Path) -> None:
    copy = RunFile.open(temp)
    try:
        problem = copy.integrity()
        if problem != "ok":
            raise RunError(f"The compacted copy failed its check: {problem}")
        if copy.table_counts() != source.table_counts():
            raise RunError("The compacted copy does not hold the same rows as the run.")
        copy.set_meta(writer=None)
        copy.settle()  # folds the WAL into the file, which syncs it
    finally:
        copy.close()
    for suffix in ("-wal", "-journal"):
        side = Path(str(temp) + suffix)
        if side.exists() and side.stat().st_size:
            raise RunError("The compacted copy could not be folded into one file.")


def _swap(temp: Path, path: Path) -> None:
    wal = Path(str(path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        # Closing the original emptied its WAL unless another program is reading it.
        raise RunError("Another program has the run open; try again when it has stopped.")
    for suffix in SIDE_FILES:  # empty leftovers of the old file must not meet the new one
        try:
            Path(str(path) + suffix).unlink(missing_ok=True)
            Path(str(temp) + suffix).unlink(missing_ok=True)
        except OSError as error:
            raise RunError(f"The run is in use by another program: {error}") from error
    try:
        os.replace(temp, path)
    except OSError as error:
        raise RunError(f"The compacted file could not be put in place: {error}") from error


def _release(source: RunFile, path: Path) -> None:
    """After a failure: take the claim off the original, reopening it if it was already closed."""
    with contextlib.suppress(RunError, OSError):
        if source.closed:
            source = RunFile.open(path)
        try:
            source.set_meta(writer=None)
        finally:
            source.close()


__all__ = ["Compacted", "compact_file", "file_size"]

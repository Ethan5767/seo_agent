#!/usr/bin/env python3
"""Write a file so a reader never sees it half-written.

Every arrow in this pipeline is a JSON file with a schema. `findings.json` is
what `plan` reads; `worklist.json` is what `remediate` reads; `changelog.json` is
what `acceptance_check` and the handoff gate read; `gate-baseline.json` is what
decides whether a client's PR is red. All of them were written with a plain
`Path.write_text`, which is:

    open(path, "w")     # the file is now ZERO BYTES on disk
    write(...)          # ... and only now does it have content
    close()

There is a window between those two lines. Anything that ends the process inside
it - Ctrl-C on a long measure, an OOM kill, a runner timing out mid-step, a full
disk - leaves a truncated or empty file **that the next stage will read**. And it
reads as a valid absence rather than as damage: an empty `findings.json` is a
site with no findings, so the ratchet files every real finding as RESOLVED and
the next cycle's worklist is empty. A truncated one raises a JSONDecodeError from
somewhere unrelated. A half-written `gate-baseline.json` runs the whole fleet's
gates bare.

The window is small and this has probably never happened. It costs four lines to
make it impossible, and the artifact whose integrity the entire ratchet rests on
is not the place to keep a race.

`os.replace` is atomic on POSIX and on Windows (unlike `os.rename`), so a reader
sees either the whole old file or the whole new one, never a partial. The temp
file is created in the SAME directory because a rename across filesystems is not
atomic - and `/tmp` is very often a different filesystem.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

__all__ = ["write_atomic", "write_json_atomic"]


def write_atomic(path, data: str, *, encoding: str = "utf-8", fsync: bool = True) -> Path:
    """Replace `path` with `data`, atomically. Returns the path.

    `fsync=False` skips the durability flush and keeps only the atomicity. That
    is the right trade for something regenerable and written in a hot loop; it is
    NOT the right trade for a cycle artifact, so it is not the default.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # delete=False because we are going to rename it, not drop it. The prefix
    # makes an orphan left by a hard kill obviously ours and obviously junk.
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(data)
            if fsync:
                fh.flush()
                os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        # Leave nothing behind on any failure, including KeyboardInterrupt -
        # which is precisely the interruption this function exists for, and is
        # not an Exception.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    if fsync:
        # The rename itself needs flushing too, or a power loss can leave the
        # directory entry pointing at the old inode with the new data already
        # durable. Not supported everywhere; a failure here is not a write
        # failure, so it is swallowed rather than raised.
        try:
            dir_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

    return path


def write_json_atomic(path, doc, *, indent: int = 2, sort_keys: bool = True) -> Path:
    """The pipeline's artifact convention: pretty, sorted, one trailing newline.

    Serialised BEFORE the file is touched. A document that cannot be encoded -
    a stray `set`, a `Path`, a NaN under `allow_nan=False` - must fail with the
    previous artifact still intact, not after it has been replaced.
    """
    text = json.dumps(doc, indent=indent, sort_keys=sort_keys) + "\n"
    return write_atomic(path, text)

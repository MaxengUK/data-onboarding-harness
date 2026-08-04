"""Local filesystem implementation of `StoragePath` (CLAUDE.md §4.2.2).

**This module is the one place in the kernel permitted to touch `pathlib` and
`os` for Bronze addressing.** §0 forbids that everywhere else; the prohibition is
about callers assuming a mounted disk, and it is discharged by confining the
assumption to an implementation that is explicitly one backend among several.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

from kernel.storage.base import ObjectExistsError, StoragePath


class LocalPath(StoragePath):
    """A location on the local filesystem."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        """The underlying `Path`.

        Exposed for tests that need to corrupt bytes on disk or inspect
        permission bits — i.e. to attack the store from outside its API, which is
        exactly what the §4.2.5 layer 3 test has to do. Not for kernel callers.
        """
        return self._path

    @property
    def uri(self) -> str:
        return self._path.absolute().as_uri()

    def __truediv__(self, name: str) -> LocalPath:
        return LocalPath(self._path / name)

    def __repr__(self) -> str:
        return f"LocalPath({str(self._path)!r})"

    def exists(self) -> bool:
        return self._path.exists()

    def write_bytes(self, data: bytes) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # "xb" is O_CREAT|O_EXCL: the location is claimed atomically, so two
            # writers racing on one partition id cannot both win. Preferred over
            # write-temp-then-rename, which would leave a check-then-act window
            # on exactly the invariant §4.2.4 depends on.
            #
            # The cost is that a crash mid-write can leave a partial object. That
            # is acceptable here and only here: `write_partition` returns the
            # `PartitionRef` after the write completes, so a partial object was
            # never named in a run manifest and no reader can reach it. It is
            # orphaned bytes, not corrupt data.
            with open(self._path, "xb") as handle:
                handle.write(data)
        except FileExistsError as exc:
            raise ObjectExistsError(
                f"refusing to overwrite an existing object at {self.uri}"
            ) from exc

    def read_bytes(self) -> bytes:
        return self._path.read_bytes()

    def make_read_only(self) -> bool:
        try:
            mode = self._path.stat().st_mode
            self._path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        except OSError:
            return False
        return not os.access(self._path, os.W_OK)

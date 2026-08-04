"""The path abstraction Bronze is addressed through (CLAUDE.md §4.2.2, §0).

§0 forbids addressing Bronze with `os.path`, `pathlib.Path`, or a bare `open()`,
so this layer has to exist before Bronze can be written at all. §4.2.2 says why:
`bronze.location` is a path abstraction, not a `Path` constant, and local FS, S3
and Azure Blob are equally valid targets with none of them the default that the
others are exceptions to.

**This surface is deliberately narrow, and deliberately not general-purpose.**
It carries exactly what `kernel/bronze` uses today and nothing else. Absent by
decision, not by oversight: `size()` (write knows `len(data)`, verify has already
read the bytes), `list()`/`glob()` (nothing enumerates partitions yet), `stat()`,
`copy()`, and any form of `delete()` — the last one by §0 rather than by economy.

The second implementation will probably change this interface, and that is the
expected outcome rather than a failure. An S3 backend needs multipart upload for
anything large, which is a different write shape than `write_bytes`; designing
for it now would mean designing a general storage layer against one real caller
and one imagined one. The narrow version is cheaper to change than a wide one.

**Known limit — whole-object I/O.** `write_bytes`/`read_bytes` materialise the
whole object in memory. See `kernel/bronze` for why this is the right trade today
and what it costs.
"""

from kernel.storage.base import StoragePath, UnsupportedLocationScheme
from kernel.storage.local import LocalPath
from kernel.storage.resolve import resolve_location

__all__ = [
    "LocalPath",
    "StoragePath",
    "UnsupportedLocationScheme",
    "resolve_location",
]

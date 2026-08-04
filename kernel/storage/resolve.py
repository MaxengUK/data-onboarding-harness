"""Location URI -> `StoragePath` (CLAUDE.md §4.2.2)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from kernel.storage.base import StoragePath, UnsupportedLocationScheme
from kernel.storage.local import LocalPath

#: Schemes §4.2.2 admits as Bronze locations but this build cannot address yet.
#: Listed rather than lumped in with unknown input so the failure names the gap:
#: an unimplemented backend is a different problem from a typo, and preflight
#: has to be able to tell a client which one they have.
RECOGNISED_UNIMPLEMENTED = {
    "s3": "S3",
    "s3a": "S3",
    "az": "Azure Blob",
    "abfs": "Azure Blob",
    "abfss": "Azure Blob",
    "gs": "Google Cloud Storage",
}


def resolve_location(uri: str) -> StoragePath:
    """Resolve a `bronze.location` value to a `StoragePath`.

    Accepts `file://` URIs and bare local paths (including Windows drive paths,
    which `urlparse` reads as a one-letter scheme).
    """
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()

    if scheme in RECOGNISED_UNIMPLEMENTED:
        raise UnsupportedLocationScheme(
            f"{RECOGNISED_UNIMPLEMENTED[scheme]} ({scheme}://) is a valid Bronze "
            f"location under CLAUDE.md §4.2.2 but is not implemented in this "
            f"build; only local paths and file:// are addressable today"
        )

    if scheme == "file":
        # netloc carries the host in file://host/path; empty and "localhost" are
        # the only ones that mean the local machine.
        if parsed.netloc not in ("", "localhost"):
            raise UnsupportedLocationScheme(
                f"remote file:// host {parsed.netloc!r} is not addressable; "
                f"use a local path"
            )
        path = unquote(parsed.path)
        # file:///C:/x parses to /C:/x — strip the leading slash before a drive.
        if len(path) > 2 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return LocalPath(Path(path))

    if len(scheme) <= 1:  # "" for a POSIX path, "c" for C:\...
        return LocalPath(Path(uri))

    raise UnsupportedLocationScheme(
        f"unrecognised storage scheme {scheme!r} in location {uri!r}"
    )

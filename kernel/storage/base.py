"""The abstract path type and its errors (CLAUDE.md §4.2.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageError(Exception):
    """Base for storage-layer failures."""


class UnsupportedLocationScheme(StorageError):
    """A location URI names a backend this build cannot address.

    Distinct from "malformed URI": the scheme is recognised and admissible under
    §4.2.2, there is simply no implementation of it in this build. Preflight will
    surface this as a blocker with the scheme named, which is why the message has
    to say which scheme and not merely that resolution failed.
    """


class ObjectExistsError(StorageError):
    """A write was attempted against a location that already holds an object.

    The storage layer refuses rather than overwrites. Bronze depends on this for
    §4.2.4 partition identity, but the refusal belongs here: a path abstraction
    whose `write_bytes` can destroy data is the wrong primitive to build an
    immutable store on, regardless of who is calling it.
    """


class StoragePath(ABC):
    """One addressable location in a storage backend.

    Path-like rather than key-based (`§4.2.2`: "an object-store-capable path
    type"), so composition reads the same whether the backend is a filesystem or
    a bucket, and no caller does OS path arithmetic.

    Implementations must be immutable: `__truediv__` returns a new instance and
    never mutates the receiver.
    """

    @property
    @abstractmethod
    def uri(self) -> str:
        """The location as a URI. Carried into `PartitionRef` and error messages."""

    @abstractmethod
    def __truediv__(self, name: str) -> StoragePath:
        """Return the child location `name` under this one."""

    @abstractmethod
    def exists(self) -> bool:
        """True if an object is present at this location."""

    @abstractmethod
    def write_bytes(self, data: bytes) -> None:
        """Write `data` here, creating any containers the backend needs.

        Raises `ObjectExistsError` if an object is already present. There is no
        `overwrite` parameter and there must never be one (§0, §4.2.5 layer 1).

        This is not promised to be atomic. §4.2.3 scopes the atomic-swap
        requirement to publication targets, not to Bronze; an implementation may
        write atomically where that is cheap, but callers may not rely on it.
        """

    @abstractmethod
    def read_bytes(self) -> bytes:
        """Return the object's bytes."""

    @abstractmethod
    def make_read_only(self) -> bool:
        """Best-effort: mark this location read-only. Returns whether it took.

        §4.2.5 layer 2, and the spec is explicit that this is "a speed bump, not
        a wall": root overrides it, container bind mounts and overlay filesystems
        handle permission bits inconsistently, and object stores may have no
        equivalent at all. It catches an accidental `rm` and a careless script.

        So this returns a bool instead of raising, and **nothing may branch on it
        for correctness**. A caller that treats `False` as a failure has promoted
        layer 2 into a control, which is precisely the mistake §4.2.5 warns
        against. Log it and carry on; layer 3 is the enforcement.
        """

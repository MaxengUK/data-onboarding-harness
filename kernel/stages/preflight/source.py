"""Reading the bound source, once, before anything else runs (§6.2.1, §6.2.2).

Preflight is the only stage permitted to touch a source besides `ingest` — §0
forbids it *after* `ingest`, and preflight runs before. It reads the source once
and hands facts to the checks, so twenty-nine checks cannot become twenty-nine
reads of a client's production extract.

**What this build supports is narrow, and the narrowness is reported rather than
worked around.** One file-bound source, one object. A database binding, a second
source, or a second object leaves the probe unsupported, and every check that
needed it reports `UNAVAILABLE` — never `NOT_APPLICABLE`, because those
manifests do have a source that *should* be checked.

**Memory.** The object is read whole, which inherits the single-node ceiling
already documented for Bronze: a dataset that does not fit in memory does not fit
this build anywhere, and preflight is not the place to pretend otherwise. A
`read_prefix(n)` member on `StoragePath` is what the first remote backend or the
first genuinely large extract will force; nothing needs it yet, so `kernel/storage`
is unchanged by this stage.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from kernel.storage import UnsupportedLocationScheme, resolve_location
from schemas.manifest import Manifest, SourceConfig

#: Delimiters worth trying when a manifest does not declare one. §6's `ingest`
#: rule — a sniffed value must be recorded and confirmed, never used silently —
#: applies here too, so the chosen delimiter goes into the check detail.
CANDIDATE_DELIMITERS = (",", ";", "\t", "|")

ENV_PREFIX = "env:"


class ConnectionRefError(Exception):
    """A `connection_ref` this build cannot resolve, or must not accept."""


@dataclass(frozen=True)
class SourceProbe:
    """What preflight could learn about the bound source.

    Every field is optional because every one of them can fail to be
    established, and a check that finds `None` must say `unavailable` rather
    than invent a verdict. `unsupported` is separate from `read_error` on
    purpose: "this build cannot read that kind of source" and "that source could
    not be read" produce the same status but very different advice.
    """

    unsupported: str | None = None
    location_uri: str | None = None
    read_error: str | None = None
    encoding_error: str | None = None
    delimiter: str | None = None
    columns: tuple[str, ...] | None = None
    row_count: int | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def usable(self) -> bool:
        return self.unsupported is None and self.read_error is None


def resolve_connection_ref(ref: str, environment: dict[str, str]) -> str:
    """`env:NAME` → the environment variable's value.

    Only the `env:` form is accepted. §7.1 says a connection_ref is "never a
    literal credential", and the way that rule gets broken is not malice but
    convenience during a demo — so a literal is refused here rather than
    linted somewhere else.
    """
    if not ref.startswith(ENV_PREFIX):
        raise ConnectionRefError(
            f"connection_ref must be of the form env:NAME; {ref!r} looks like a "
            f"literal, and a manifest is not a place to keep one (§7.1)"
        )

    name = ref[len(ENV_PREFIX) :]
    if not name:
        raise ConnectionRefError("connection_ref names no environment variable")
    if name not in environment:
        raise ConnectionRefError(f"environment variable {name} is not set")

    return environment[name]


def _sniff_delimiter(header_line: str) -> str:
    """The candidate producing the most fields. Recorded, never silent."""
    return max(CANDIDATE_DELIMITERS, key=lambda candidate: header_line.count(candidate))


def probe_source(manifest: Manifest, environment: dict[str, str]) -> SourceProbe:
    """Read the bound source once and return what could be established."""
    if len(manifest.sources) != 1:
        return SourceProbe(
            unsupported=(
                f"this build probes exactly one source; the manifest declares "
                f"{len(manifest.sources)}"
            )
        )

    source = manifest.sources[0]
    if source.binding.kind != "file":
        return SourceProbe(
            unsupported=(
                f"binding.kind={source.binding.kind!r} needs a source adapter, "
                f"and kernel/adapters/ has none in this build"
            )
        )
    if len(source.binding.objects) != 1:
        return SourceProbe(
            unsupported=(
                f"this build probes exactly one object; the binding declares "
                f"{len(source.binding.objects)}"
            )
        )

    return _probe_file(source, environment)


def _probe_file(source: SourceConfig, environment: dict[str, str]) -> SourceProbe:
    try:
        root = resolve_connection_ref(source.binding.connection_ref, environment)
        location = resolve_location(root) / source.binding.objects[0]
    except (ConnectionRefError, UnsupportedLocationScheme) as exc:
        return SourceProbe(read_error=str(exc))

    if not location.exists():
        return SourceProbe(location_uri=location.uri, read_error="no object at this location")

    raw = location.read_bytes()

    try:
        # errors="strict" over the whole object rather than a sample: decoding
        # is not a value read, so §6.2.2's sampling limit does not apply to it,
        # and bad bytes late in a file are exactly what a sample would miss.
        text = raw.decode(source.encoding)
    except UnicodeDecodeError as exc:
        return SourceProbe(
            location_uri=location.uri,
            # The offending bytes are deliberately not carried. A byte offset
            # locates the problem; the bytes themselves are source content.
            encoding_error=(
                f"byte offset {exc.start} is not valid {source.encoding} "
                f"({exc.reason})"
            ),
        )

    if not text.strip():
        return SourceProbe(location_uri=location.uri, columns=(), row_count=0)

    delimiter = _sniff_delimiter(text.splitlines()[0])
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    header, *body = rows

    return SourceProbe(
        location_uri=location.uri,
        delimiter=delimiter,
        columns=tuple(name.strip() for name in header),
        row_count=len(body),
    )

"""Audit store failures (CLAUDE.md §4.2.6).

Deliberately parallel to `kernel/bronze/errors.py` rather than shared with it.
§4.2.6 puts the two stores under the same discipline, but they are different
stores: a message that says "partition" when a segment was tampered with sends
the reader to the wrong place, and at the moment either of these is raised the
reader is trying to work out which store lied to them.
"""


class AuditError(Exception):
    """Base for audit store failures."""


class SegmentExistsError(AuditError):
    """A write named a segment that already exists.

    The audit store's equivalent of `PartitionExistsError`, and it carries more
    weight here than the symmetry suggests. A Bronze partition id is minted fresh
    per write, so a collision is nearly always a caller bug. A segment id is
    *derived* — run id, Bronze partition, and the ordinal range — so a collision
    is the normal signal that this run already wrote this segment. Replaying a
    run under its original run id therefore refuses rather than rewrites, which
    is correct: a replay produces a new run id and is compared against the
    original by bytes.
    """


class AuditIntegrityError(AuditError):
    """A segment's bytes no longer hash to the value recorded at write time.

    §4.2.5 layer 3, applied to the audit store by §4.2.6. Not recoverable, not
    downgradable, no acknowledgement path (§0: blockers are not overridable).

    Worth being precise about what this failing means, because it is not the same
    as a Bronze integrity failure. A modified Bronze partition means the run is
    about to process data that is not what arrived. A modified audit segment
    means the *account* of what was done to data that arrived is not what was
    written — P8's "the client can always tell what happened to a record" has
    already failed, and the only thing left to do is say so loudly.
    """

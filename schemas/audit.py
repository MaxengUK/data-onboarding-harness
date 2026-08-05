"""The in-boundary audit record (CLAUDE.md §12, §8).

**This is not the evidence artifact and never leaves the client boundary.**

The spec used one word, "evidence", for two artifacts with opposite egress
rules, and that collision is what made §8 and §12 look contradictory:

- §12 requires every applied transform to record its *pre-image hash* per
  record, so a client can be told what happened to a given row. Those hashes
  are of PII-typed fields by construction.
- §8 denies exactly that — a hash of a PII-typed field — in what crosses to
  MAXENG.

Both are right about their own artifact. `AuditRecord` is the §12 one: per
record, pre-image hashed, inside the boundary, read by the client. `EvidenceArtifact`
in `schemas/evidence.py` is the §8 one: aggregate, no row locators, exportable.

`IN_BOUNDARY_ONLY` is load-bearing, not documentation: the egress gate refuses
any structure carrying it, so wiring an audit record into an evidence artifact
fails the run rather than leaking. Deliberately *not* an `EgressModel`.

Stubbed pending BUILD-PLAN item 10 (`normalize`). The type and its boundary are
fixed now so that stage has somewhere to write; the fields will grow.

**Every field here is per-record.** What is constant across a segment — the run
id, the Bronze partition — lives on `SegmentRef` in `kernel/audit/segment.py`,
not on each record. That is not only deduplication: a record that stamps its own
run id makes the segment's bytes a function of *which run wrote them* rather than
of *what was written*, and two runs over identical input then produce different
bytes for identical facts. With run identity held one level up, they do not, and
a replay's audit store can be diffed against the original byte for byte.

**And no timestamp.** The obvious `occurred_at` was removed rather than kept,
because a per-record wall-clock read is a per-record source of nondeterminism in
a store whose whole integrity story is a content hash. Time belongs to the run,
and the run manifest (§12) records it. P8 is unharmed: a record is reached
through the segment that names its run, so "when did this happen" is answered one
indirection away, and answered *once* rather than restated a million times with
microsecond noise that no reader wants and no replay can reproduce.
"""

from typing import ClassVar

from pydantic import BaseModel, Field


class AuditRecord(BaseModel):
    """One attributable mutation, per P8: one rule id, one transform name.

    Holds the pre-image hash so a value can be verified against the Bronze
    partition that still holds it (§4.2). The hash proves which value it was;
    Bronze produces it.
    """

    #: Read by kernel.gates.egress_gate off the *class*, so it must stay a
    #: ClassVar — as a Pydantic field it would vanish from the class namespace
    #: and the gate would silently stop recognising this type. Removing it makes
    #: the record exportable, which is the failure this module exists to prevent.
    IN_BOUNDARY_ONLY: ClassVar[bool] = True

    # Segment assignment is a pure function of this (§4.2.6), which is what
    # keeps segment boundaries independent of worker completion order. That is
    # why the field exists; what it *is* is in the description.
    row_ordinal: int = Field(
        ge=0,
        description="Position of the source row in its Bronze partition.",
    )
    record_key: str
    column_name: str
    rule_id: str
    transform_name: str
    pre_image_hash: str
    post_image_hash: str

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
"""

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel


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

    run_id: str
    batch_id: str
    bronze_partition: str
    record_key: str
    column_name: str
    rule_id: str
    transform_name: str
    pre_image_hash: str
    post_image_hash: str
    occurred_at: datetime

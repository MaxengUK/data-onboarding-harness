"""Bronze failures (CLAUDE.md §4.2.4, §4.2.5)."""


class BronzeError(Exception):
    """Base for Bronze store failures."""


class PartitionExistsError(BronzeError):
    """A write named a partition id that already exists.

    §4.2.4: re-ingesting the same source is always a new partition, never an
    overwrite. There is no flag, manifest key, or operational circumstance that
    turns this into an update — a re-run after failure, a corrected extract, a
    backfill, and a scheduled batch that happened to read unchanged rows all
    produce distinct partitions.
    """


class BronzeIntegrityError(BronzeError):
    """A partition's bytes no longer hash to the value recorded at write time.

    §4.2.5 layer 3, and the actual enforcement of the immutability claim. Bronze
    is client-owned, so modification cannot be *prevented*; what this makes
    impossible is operating on modified Bronze without knowing.

    Not recoverable and not downgradable. There is no acknowledgement path and no
    flag that turns it into a warning (§0: blockers are not overridable). A run
    that sees this fails.
    """

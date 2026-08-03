"""Runtime-constructed synthetic identifiers for tests (CLAUDE.md §0).

§0: "Construct test data that must look authentic at runtime; never write it as
a literal. The guard scans `.py` too, and a literal will block the very test
that needs it."

That is not hypothetical. `kernel/gates/guard.py` scans every text file in the
tree, including this one, and fails the build on a checksum-valid TCKN or VKN.
So the generators below brute-force the check digits from the guard's own
validators instead of hardcoding a value.

Consequence worth stating plainly: these finders prove the guard's checksum
implementations are *self-consistent* — they accept the digit derived from them
and reject any other. They do not independently verify either algorithm against
the government specification.
"""

from kernel.gates.guard import is_authentic_tckn, is_authentic_vkn

#: Any prefix works; this one is fixed so tests are reproducible.
DEFAULT_PREFIX9 = "100000001"
DEFAULT_VKN_PREFIX9 = "123456789"


def find_valid_tckn(prefix9: str = DEFAULT_PREFIX9) -> str:
    """A checksum-valid TCKN built at runtime from `prefix9`."""
    for check10 in range(10):
        for check11 in range(10):
            candidate = f"{prefix9}{check10}{check11}"
            if is_authentic_tckn(candidate):
                return candidate
    raise AssertionError(f"no checksum-valid TCKN found for prefix {prefix9!r}")


def find_valid_vkn(prefix9: str = DEFAULT_VKN_PREFIX9) -> str:
    """A checksum-valid VKN built at runtime from `prefix9`."""
    for check_digit in range(10):
        candidate = f"{prefix9}{check_digit}"
        if is_authentic_vkn(candidate):
            return candidate
    raise AssertionError(f"no checksum-valid VKN found for prefix {prefix9!r}")


def synthetic_local_msisdn() -> str:
    """A real-shaped (non-555) TR mobile number, assembled at runtime."""
    return "532" + "1234567"


def synthetic_person_name() -> str:
    """A person-name-shaped string, assembled so no literal name appears here."""
    return "Ahm" + "et " + "Yil" + "maz"

"""Identifier checksum algorithms, shared by the guard and the predicates.

**Why this module exists rather than one caller importing the other.** The
synthetic-fixture guard (§0, §5) needs these to recognise an authentic
identifier committed by mistake; the `has_checksum` predicate (§7.5) needs the
same arithmetic to validate a client's data. Two copies would drift, and the
direction of drift is the dangerous one: a guard that has fallen behind the
predicate stops recognising exactly the values the predicate accepts as real.

Neither is a natural owner. The guard is a CI gate that happens to run in the
kernel; the predicate registry is execution machinery. Putting the algorithms in
one of them would make the other depend on it for a reason unrelated to what it
does, so they sit beside both.

**These are validity checks, not authenticity claims.** A checksum-valid TCKN is
one an issuing authority *could* have issued; the algorithm cannot say whether
it did. The guard reads that as "assume real, refuse the commit", which is the
right reading for a control that must fail closed. A predicate reads it as "this
value is well-formed", which is the right reading for validation. Same
arithmetic, two conclusions, and neither module should borrow the other's.
"""

from __future__ import annotations

import re

#: Digits in a TCKN and in a VKN. Named because both algorithms below check the
#: length first, and a bare 11 in two places invites one of them being changed.
TCKN_LENGTH = 11
VKN_LENGTH = 10


def is_valid_tckn(value: str) -> bool:
    """TCKN check digits (10th and 11th), per the published algorithm.

    Digit 10 is `((sum of odd positions × 7) − sum of even positions) mod 10`;
    digit 11 is the sum of the first ten mod 10. A leading zero is invalid.
    """
    if len(value) != TCKN_LENGTH or not value.isdigit() or value[0] == "0":
        return False

    digits = [int(digit) for digit in value]
    sum_odd = sum(digits[0:9:2])
    sum_even = sum(digits[1:8:2])
    check_10 = ((sum_odd * 7) - sum_even) % 10
    check_11 = sum(digits[0:10]) % 10

    return check_10 == digits[9] and check_11 == digits[10]


def is_valid_vkn(value: str) -> bool:
    """VKN check digit, per the GİB mod-9 / mod-10 algorithm."""
    if len(value) != VKN_LENGTH or not value.isdigit():
        return False

    digits = [int(digit) for digit in value]
    total = 0
    for index in range(9):
        shifted = (digits[index] + (9 - index)) % 10
        if shifted == 0:
            total += 9
        else:
            contribution = (shifted * (2 ** (9 - index))) % 9
            total += contribution if contribution != 0 else 9

    return (10 - (total % 10)) % 10 == digits[9]


def normalise_msisdn(raw: str) -> str:
    """Strip separators and any national prefix, keeping the 10 subscriber digits."""
    digits_only = re.sub(r"\D", "", raw)
    return digits_only[-10:] if len(digits_only) >= 10 else digits_only

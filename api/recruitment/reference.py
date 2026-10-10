"""A reference and a check code for an application, so a candidate without an account can check progress.

Kept deliberately parallel to ``letters.checking`` rather than importing it: that module is scoped to
letters in its own docstring and its own model (``LetterCheck``), and the two concerns (a letter's
authenticity; an application's status) are not the same thing even though the shape of the solution is.
"""

import re
import secrets

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford's: no I, L, O or U, so nothing is misread
CODE_LENGTH = 12  # 60 bits, as letters.checking uses for the same purpose
REFERENCE_LENGTH = 8
READ_AS = str.maketrans("OIL", "011")


def new_reference() -> str:
    """A short reference, printed to the candidate with their check code. Not a secret by itself."""
    raw = "".join(secrets.choice(ALPHABET) for _ in range(REFERENCE_LENGTH))
    return f"GSA-APP-{raw[:4]}-{raw[4:]}"


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    return "-".join(raw[i : i + 4] for i in range(0, CODE_LENGTH, 4))


def plain(code: str) -> str:
    """A code as it may be typed: any case, with spaces or dashes, O for 0 and I or L for 1."""
    return re.sub(r"[\s-]", "", code.upper()).translate(READ_AS)

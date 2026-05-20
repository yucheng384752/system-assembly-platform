import re
import unicodedata
from collections.abc import Iterable
from datetime import date, datetime


class NormalizationError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def normalize_lot_no(val: str) -> int:
    """
    Normalize lot number string to integer.
    Removes non-digit characters.
    e.g. "1234567-01" -> 123456701
    """
    if not val:
        raise NormalizationError("E_LOT_EMPTY", "Lot number is empty")

    # Remove all non-digit characters
    digits = re.sub(r"\D", "", str(val))

    if not digits:
        raise NormalizationError("E_LOT_FORMAT", f"Invalid lot number format: {val}")

    try:
        return int(digits)
    except ValueError:
        raise NormalizationError("E_LOT_FORMAT", f"Invalid lot number format: {val}")


def normalize_date(val: str | int | date | datetime) -> date:
    """
    Normalize date to date object.
    Supports:
    - "YYYY-MM-DD"
    - "YYYYMMDD"
    - "YYYMMDD" (ROC year, e.g. 1120101 -> 2023-01-01)
    - int (20230101 or 1120101)
    """
    if val is None:
        raise NormalizationError("E_DATE_EMPTY", "Date is empty")

    if isinstance(val, (date, datetime)):
        if isinstance(val, datetime):
            return val.date()
        return val

    s_val = str(val).strip()

    # Try YYYY-MM-DD
    try:
        return datetime.strptime(s_val, "%Y-%m-%d").date()
    except ValueError:
        pass

    # Try YYYYMMDD or YYYMMDD
    # Remove non-digits
    digits = re.sub(r"\D", "", s_val)

    if len(digits) == 8:
        # YYYYMMDD
        try:
            return datetime.strptime(digits, "%Y%m%d").date()
        except ValueError:
            raise NormalizationError("E_DATE_FORMAT", f"Invalid date format: {val}")

    elif len(digits) == 7:
        # YYYMMDD (ROC)
        try:
            roc_year = int(digits[:3])
            month = int(digits[3:5])
            day = int(digits[5:])

            ad_year = roc_year + 1911
            return date(ad_year, month, day)
        except ValueError:
            raise NormalizationError("E_DATE_FORMAT", f"Invalid date format: {val}")

    raise NormalizationError("E_DATE_FORMAT", f"Invalid date format: {val}")


def normalize_date_to_int(val: str | int | date | datetime) -> int:
    """
    Normalize date to YYYYMMDD integer.
    """
    d = normalize_date(val)
    return int(d.strftime("%Y%m%d"))


_DEFAULT_SEARCH_SEPARATORS = {
    " ",
    "\t",
    "\n",
    "\r",
    "_",
    "-",
    "‐",  # U+2010
    "‑",  # U+2011
    "–",  # U+2013
    "—",  # U+2014
    "－",  # U+FF0D (fullwidth hyphen-minus)
    "　",  # U+3000 (ideographic space)
}


def normalize_search_term(
    val: object | None, *, remove_separators: Iterable[str] = _DEFAULT_SEARCH_SEPARATORS
) -> str | None:
    """Normalize a free-form search term into a canonical string.

    Goals:
    - Case-insensitive matching (via casefold)
    - Full/half width normalization (via NFKC)
    - Tolerate common separators (spaces, underscores, hyphens)

    Examples:
    - "PE32" == "PE 32" == "pe-32" == "ＰＥ３２" -> "pe32"
    """
    if val is None:
        return None

    s = str(val)
    if not s:
        return None

    s = unicodedata.normalize("NFKC", s).strip()
    if not s:
        return None

    s = s.casefold()
    if remove_separators:
        for ch in remove_separators:
            s = s.replace(ch, "")

    s = s.strip()
    return s or None


def to_fullwidth_ascii(val: str) -> str:
    """Convert ASCII letters/digits/punct into fullwidth equivalents.

    This is mainly used to generate query variants for datasets that store
    fullwidth characters.
    """
    if not val:
        return ""

    out_chars: list[str] = []
    for ch in val:
        code = ord(ch)
        if ch == " ":
            out_chars.append("　")
        elif 0x21 <= code <= 0x7E:
            # Fullwidth forms are ASCII + 0xFEE0
            out_chars.append(chr(code + 0xFEE0))
        else:
            out_chars.append(ch)
    return "".join(out_chars)


def normalize_search_term_variants(val: object | None) -> list[str]:
    """Return normalized search term variants for matching.

    Includes the NFKC/casefold canonical form and a fullwidth ASCII form to
    cover datasets stored in fullwidth.
    """
    base = normalize_search_term(val)
    if not base:
        return []
    # Ensure uniqueness while preserving order.
    variants = [base]

    # Fullwidth lower/upper variants help match datasets stored in fullwidth.
    # NOTE: SQLite's lower()/upper() are ASCII-only by default, so we include
    # both cases to remain portable across SQLite/PostgreSQL.
    fw_lower = to_fullwidth_ascii(base)
    fw_upper = to_fullwidth_ascii(base.upper())

    for v in [fw_lower, fw_upper]:
        if v and v not in variants:
            variants.append(v)

    return variants

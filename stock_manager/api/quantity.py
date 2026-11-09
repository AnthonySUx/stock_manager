"""Recipe quantity parsing and unit comparison (#47).

Recipe quantities come as text: "2个", "500克", "1.5 kg", or a bare "2" with a
separate unit. Stock units are free text chosen per item. We only compare
units (with a few spelling aliases); there is deliberately no conversion
table, so 500 g never turns into 0.5 kg and 500 g never matches "3 个".
"""
import re
from typing import Optional

# Spelling aliases only. Different units stay different (g != kg).
_UNIT_ALIASES = {
    "克": "g", "g": "g", "gram": "g", "grams": "g",
    "千克": "kg", "公斤": "kg", "kg": "kg",
    "毫升": "ml", "ml": "ml",
    "升": "l", "l": "l",
    "个": "pcs", "pcs": "pcs", "pc": "pcs", "piece": "pcs", "pieces": "pcs",
}

# A decimal number, then an optional unit: starts with a letter (CJK counts),
# no digits. So "1/2" and "2-3个" are not read as 1 or 2.
_QUANTITY_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([^\W\d_][^\d]*)?$")


def normalize_unit(unit: Optional[str]) -> str:
    """Canonical spelling of a unit; "" when there is none."""
    key = (unit or "").strip().lower()
    return _UNIT_ALIASES.get(key, key)


def parse_quantity(
    quantity: Optional[str], unit: Optional[str] = None
) -> tuple[Optional[float], Optional[str]]:
    """Split a recipe quantity into (number, unit).

    The unit comes from the text ("500克") or from `unit`. If both are given
    and disagree, the unit is unknown (None). Text we cannot read as a
    single decimal number ("适量", "1/2", "2-3") gives (None, None).
    """
    match = _QUANTITY_RE.match((quantity or "").strip())
    if match is None:
        return None, None
    number = float(match.group(1))
    text_unit = (match.group(2) or "").strip()
    given_unit = (unit or "").strip()
    if text_unit and given_unit and normalize_unit(text_unit) != normalize_unit(given_unit):
        return number, None
    return number, (text_unit or given_unit or None)


def same_unit(a: Optional[str], b: Optional[str]) -> bool:
    """True when both units are present and mean the same spelling."""
    na, nb = normalize_unit(a), normalize_unit(b)
    return bool(na) and na == nb

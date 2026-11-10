"""Case-insensitive "contains" filters for keyword search (#49).

A keyword is matched literally: `%` and `_` are ordinary characters, not
LIKE wildcards, so searching "50%" does not match every title with "50".
"""
from sqlalchemy import func

# "/" instead of the usual backslash: backslashes need extra quoting in
# MySQL string literals, "/" behaves the same on MySQL and SQLite.
_ESCAPE = "/"


def escape_like(text: str) -> str:
    """Escape LIKE wildcards (and the escape character itself) in `text`."""
    return (
        text.replace(_ESCAPE, _ESCAPE * 2)
        .replace("%", _ESCAPE + "%")
        .replace("_", _ESCAPE + "_")
    )


def contains_ci(column, keyword: str):
    """SQL condition: lower(column) contains lower(keyword), literally."""
    return func.lower(column).like(f"%{escape_like(keyword.lower())}%", escape=_ESCAPE)

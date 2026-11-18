"""Locale and household timezone (#65).

- Locale decides the language of AI-generated text. Resolution order:
  explicit request field → `default_locale` setting (when the household set
  one) → `Accept-Language` header → zh-CN.
  The setting comes before the header on purpose: iOS sends the device
  language with every request, so a header-first order would make the
  household setting impossible to apply.
- Timezone decides what "today" is. The whole household shares
  `default_timezone`; when it is not set, the server's local date is used.
"""
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

SUPPORTED_LOCALES = ("zh-CN", "en", "ja")
DEFAULT_LOCALE = "zh-CN"

# Language names used in AI prompts.
LANGUAGE_NAMES = {
    "zh-CN": "Simplified Chinese",
    "en": "English",
    "ja": "Japanese",
}


def normalize_locale(tag: Optional[str]) -> Optional[str]:
    """Map a BCP-47 tag to a supported locale, or None.

    "zh", "zh-Hans", "zh_CN", "zh-Hans-CN" → zh-CN; "en-US" → en; "ja-JP" → ja.
    Traditional Chinese (zh-Hant, zh-TW, zh-HK) is not supported.
    """
    text = (tag or "").strip().replace("_", "-").lower()
    if not text:
        return None
    parts = text.split("-")
    language = parts[0]
    if language == "zh":
        rest = set(parts[1:])
        if rest & {"hant", "tw", "hk", "mo"}:
            return None
        return "zh-CN"
    if language in ("en", "ja"):
        return language
    return None


def _accept_language_tags(header: Optional[str]) -> list[str]:
    """Tags from an Accept-Language header, highest q first."""
    weighted = []
    for index, part in enumerate((header or "").split(",")):
        fields = part.strip().split(";")
        tag = fields[0].strip()
        if not tag or tag == "*":
            continue
        q = 1.0
        for field in fields[1:]:
            name, _, value = field.strip().partition("=")
            if name.strip() == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
        if q > 0:
            weighted.append((-q, index, tag))
    return [tag for _, _, tag in sorted(weighted)]


def resolve_locale(
    explicit: Optional[str],
    accept_language: Optional[str],
    setting: Optional[str],
) -> tuple[str, list[dict]]:
    """Return (locale, warnings).

    An explicit but unsupported locale falls back and adds `locale_fallback`.
    An unsupported header is ignored silently: it is the device language,
    not a choice the user made in this app.
    """
    warnings: list[dict] = []
    if explicit is not None and explicit.strip():
        locale = normalize_locale(explicit)
        if locale:
            return locale, warnings
        warnings.append({"code": "locale_fallback", "params": {"requested": explicit.strip()[:35]}})
    locale = normalize_locale(setting)
    if locale:
        return locale, warnings
    for tag in _accept_language_tags(accept_language):
        locale = normalize_locale(tag)
        if locale:
            return locale, warnings
    return DEFAULT_LOCALE, warnings


def validate_timezone(name: str) -> str:
    """Return the IANA name if it exists, else raise ValueError."""
    text = (name or "").strip()
    if not text:
        raise ValueError("timezone must not be empty")
    try:
        ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone: {text}") from exc
    return text


def _setting_value(db: Session, key: str) -> Optional[str]:
    from stock_manager.api.models import Setting

    row = db.query(Setting).filter(Setting.key == key).first()
    return row.value if row is not None else None


def household_locale(db: Session) -> Optional[str]:
    """The `default_locale` setting, or None when it is not set (or invalid)."""
    return normalize_locale(_setting_value(db, "default_locale"))


def today(db: Session) -> date:
    """Today's date in the household timezone (#65).

    Without a valid `default_timezone` setting this is the server's local
    date, as before.
    """
    name = _setting_value(db, "default_timezone")
    if name:
        try:
            return datetime.now(ZoneInfo(name)).date()
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return date.today()

"""Store-scoped receipt alias history and its deterministic reuse policy."""

import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, selectinload

from stock_manager.api.models import Item, ReceiptAliasName, ReceiptItemAlias, utcnow
from stock_manager.api.receipt_schemas import ReceiptSpecificity

_GENERIC_LABELS = {
    "蔬菜", "水果", "生鲜", "散装", "称重", "杂货", "produce", "vegetable", "vegetables",
    "fruit", "fruits", "bulk", "bulk item", "weighted item", "grocery", "misc",
}
_SPECIFIC_LABELS = ("specific_product", "specific_receipt_label")
_AMOUNT = r"\d+(?:[.,]\d+)?"
_TRAILING_RECEIPT_FIELD = re.compile(
    rf"\s+(?:[¥$€£]\s*{_AMOUNT}|{_AMOUNT}\s*(?:円|元|[¥$€£]|pcs?|個|个|件)|"
    rf"(?:x|×)\s*{_AMOUNT}|{_AMOUNT}\s*[x×]|\d+[.,]\d{{2}})$",
)
AliasKey = tuple[str, str]


def normalize_store(name: str | None) -> str:
    text = unicodedata.normalize("NFKC", name or "").lower()
    return "".join(char for char in text if not char.isspace() and unicodedata.category(char)[0] != "P")


def normalize_raw_name(name: str) -> str:
    text = " ".join(unicodedata.normalize("NFKC", name).lower().split())
    # Require a price or quantity marker to preserve numeric product names and sizes.
    while (match := _TRAILING_RECEIPT_FIELD.search(text)) is not None:
        text = text[:match.start()]
    label, _, amount = text.rpartition(" ")
    if label in _GENERIC_LABELS and amount.isdecimal():
        return label
    return text


def alias_key(store: str | None, raw_name: str) -> AliasKey | None:
    store_key = normalize_store(store)
    raw_key = normalize_raw_name(raw_name)
    if not raw_key or len(store_key) > 255 or len(raw_key) > 255:
        return None
    return store_key, raw_key


def receipt_specificity(normalized: str, specificity: ReceiptSpecificity | None) -> ReceiptSpecificity:
    return "generic_category" if normalized in _GENERIC_LABELS else (specificity or "unknown")


def may_auto_apply(specificity: str, count: int, distinct: int) -> bool:
    return specificity in _SPECIFIC_LABELS and count >= 3 and distinct == 1


@dataclass(frozen=True)
class AliasHistory:
    confirmed_name: str
    category_id: int | None
    quantity_unit: str
    specificity: str
    mode: str
    confirmed_count: int
    distinct_names: int
    names: tuple[tuple[str, int], ...]


def lookup_receipt_aliases(db: Session, keys: set[AliasKey]) -> dict[AliasKey, AliasHistory]:
    """Load a read-only snapshot suitable for use outside the DB worker."""
    if not keys:
        return {}
    aliases = db.scalars(
        select(ReceiptItemAlias)
        .where(tuple_(ReceiptItemAlias.store_key, ReceiptItemAlias.raw_name_normalized).in_(keys))
        .options(selectinload(ReceiptItemAlias.names))
    )
    return {
        (alias.store_key, alias.raw_name_normalized): AliasHistory(
            confirmed_name=alias.confirmed_item_name,
            category_id=alias.confirmed_category_id,
            quantity_unit=alias.confirmed_quantity_unit,
            specificity=alias.specificity,
            mode=alias.alias_mode,
            confirmed_count=alias.confirmed_count,
            distinct_names=alias.distinct_confirmed_names_count,
            names=tuple(sorted(
                ((row.confirmed_item_name, row.count) for row in alias.names),
                key=lambda name: (-name[1], name[0]),
            )[:5]),
        )
        for alias in aliases
    }


def _upsert(db: Session, table, key: tuple[str, ...], values: dict, updates: dict) -> None:
    if db.get_bind().dialect.name == "sqlite":
        statement = sqlite_insert(table).values(**values).on_conflict_do_update(index_elements=key, set_=updates)
    else:
        statement = mysql_insert(table).values(**values).on_duplicate_key_update(**updates)
    db.execute(statement)


def learn_receipt_alias(
    db: Session, key: AliasKey, raw_name: str, store_name: str | None,
    specificity: ReceiptSpecificity | None, item: Item,
) -> None:
    """Increment history while holding the parent row's write lock until confirm commits."""
    aliases = ReceiptItemAlias.__table__
    names = ReceiptAliasName.__table__
    store_key, normalized = key
    specificity = receipt_specificity(normalized, specificity)
    now = utcnow()
    values = {
        "store_name": store_name,
        "raw_name_original": raw_name,
        "confirmed_item_name": item.name,
        "confirmed_category_id": item.category_id,
        "confirmed_quantity_unit": item.quantity_unit,
        "confirmed_location": item.location,
        "specificity": specificity,
        "last_confirmed_at": now,
        "updated_at": now,
    }
    _upsert(db, aliases, ("store_key", "raw_name_normalized"), {
        **values, "store_key": store_key, "raw_name_normalized": normalized, "confirmed_count": 1,
    }, {**values, "confirmed_count": aliases.c.confirmed_count + 1})
    # Locking reads see current committed history even under MySQL REPEATABLE READ.
    alias_id, confirmed_count, mode = db.execute(
        select(aliases.c.id, aliases.c.confirmed_count, aliases.c.alias_mode)
        .where(aliases.c.store_key == store_key, aliases.c.raw_name_normalized == normalized)
        .with_for_update()
    ).one()
    _upsert(db, names, ("alias_id", "confirmed_item_name"), {
        "alias_id": alias_id, "confirmed_item_name": item.name, "count": 1,
    }, {"count": names.c.count + 1})
    distinct = len(db.scalars(
        select(names.c.confirmed_item_name).where(names.c.alias_id == alias_id).with_for_update()
    ).all())
    if mode != "blocked":
        mode = "auto" if may_auto_apply(specificity, confirmed_count, distinct) else "suggest"
    db.execute(aliases.update().where(aliases.c.id == alias_id).values(
        distinct_confirmed_names_count=distinct, alias_mode=mode,
    ))

"""Test data helpers: separate payloads for API and service/model layers."""

from datetime import date, timedelta


def make_item_create_payload(**overrides):
    """Generate a valid payload for POST /api/items.

    Note: current_expiration_date is included because ItemCreate requires it,
    but the router will recalculate it — do not rely on it as a client-controlled field.
    """
    today = date.today()
    future = today + timedelta(days=7)

    payload = {
        "name": "牛奶",
        # category_id should be provided via overrides from seeded categories
    "owner": "me",
        "owner": "me",
        "purchase_date": today.isoformat(),
        "quantity_value": 2,
        "quantity_unit": "瓶",
        "location": "冰箱",
        "unopened_expiration_date": future.isoformat(),
        "opened_expiration_date": None,
        "opened_date": None,
        "current_expiration_date": future.isoformat(),
        "status": "active",
        "notes": None,
    }
    payload.update(overrides)
    return payload


def make_item_model_data(**overrides):
    """Generate a complete data dict matching the Item model for service tests."""
    today = date.today()
    future = today + timedelta(days=7)

    data = {
        "name": "牛奶",
        # category_id should be provided via overrides from seeded categories
    "owner": "me",
        "owner": "me",
        "purchase_date": today.isoformat(),
        "quantity_value": 2,
        "quantity_unit": "瓶",
        "location": "冰箱",
        "unopened_expiration_date": future.isoformat(),
        "opened_expiration_date": None,
        "opened_date": None,
        "current_expiration_date": future.isoformat(),
        "status": "active",
        "notes": None,
    }
    data.update(overrides)
    return data


def make_restock_create_payload(**overrides):
    """Generate a valid payload for POST /api/restock."""
    payload = {
        "name": "鸡蛋",
        "category_id": None,
        "quantity_value": 12,
        "quantity_unit": "个",
        "notes": "早餐用",
    }
    payload.update(overrides)
    return payload


def make_restock_model_data(**overrides):
    """Generate a complete data dict matching the RestockItem model for service tests."""
    data = {
        "name": "鸡蛋",
        "category_id": None,
        "quantity_value": 12,
        "quantity_unit": "个",
        "source_item_id": None,
        "status": "pending",
        "notes": "早餐用",
    }
    data.update(overrides)
    return data

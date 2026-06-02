"""SQLAlchemy ORM models for Stock Manager."""

from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    owner = Column(String(100), nullable=False)
    purchase_date = Column(String(10), nullable=False)
    quantity_value = Column(Float, nullable=False)
    quantity_unit = Column(String(50), nullable=False)
    location = Column(String(100), nullable=False)
    unopened_expiration_date = Column(String(10), nullable=False)
    opened_expiration_date = Column(String(10), nullable=True)
    opened_date = Column(String(10), nullable=True)
    current_expiration_date = Column(String(10), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default="active",
    )
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=func.now(),
    )


class RestockItem(Base):
    __tablename__ = "restock_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100), nullable=True)
    quantity_value = Column(Float, nullable=True)
    quantity_unit = Column(String(50), nullable=True)
    source_item_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    status = Column(
        String(20),
        nullable=False,
        default="pending",
    )
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    done_at = Column(DateTime, nullable=True)

    # Relationship
    source_item = relationship("Item", backref="restock_items")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(255), nullable=False)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
        onupdate=func.now(),
    )

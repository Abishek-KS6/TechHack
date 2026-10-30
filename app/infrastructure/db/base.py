import uuid
from datetime import datetime
from sqlalchemy import text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    SQLAlchemy 2.0 Declarative Base for BrandShield AI.
    All models inherit from this base class.
    """
    pass


class UUIDPrimaryKeyMixin:
    """Provides a cryptographically strong UUID primary key."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        sort_order=-100,
        doc="Universally unique identifier primary key."
    )


class TimestampMixin:
    """Provides timezone-aware creation and modification timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        nullable=False,
        doc="Timestamp representing record creation."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        onupdate=text("clock_timestamp()"),
        nullable=False,
        doc="Timestamp representing last record mutation."
    )

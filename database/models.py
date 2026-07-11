from datetime import datetime, time, timezone
from typing import List, Optional
from sqlalchemy import ForeignKey, String, Boolean, Integer, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    discord_username: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    timezone_set: Mapped[bool] = mapped_column(Boolean, default=True)
    summary_time: Mapped[time] = mapped_column(default=time(22, 0))
    preferred_language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    sections: Mapped[List["Section"]] = relationship(
        "Section", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    items: Mapped[List["Item"]] = relationship(
        "Item", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    memories: Mapped[List["Memory"]] = relationship(
        "Memory", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    messages: Mapped[List["Message"]] = relationship(
        "Message", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uix_user_section_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    slug: Mapped[str] = mapped_column(String(128))
    section_type: Mapped[str] = mapped_column(String(32), default="custom")  # system | custom
    schema: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    view_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True, default=dict)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="sections")
    items: Mapped[List["Item"]] = relationship(
        "Item", back_populates="section", cascade="all, delete-orphan", lazy="selectin"
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), index=True)
    title: Mapped[str] = mapped_column(String(512))
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="todo")  # todo | done | archived | in_progress | cancelled
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1-5
    tags: Mapped[List[str]] = mapped_column(JSONB, default=list)
    custom_fields: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="items")
    section: Mapped["Section"] = relationship("Section", back_populates="items")
    reminders: Mapped[List["Reminder"]] = relationship(
        "Reminder", back_populates="item", cascade="all, delete-orphan", lazy="selectin"
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    item: Mapped["Item"] = relationship("Item", back_populates="reminders")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32), default="preference")
    importance: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="memories")
    source_item: Mapped[Optional["Item"]] = relationship("Item")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="user")  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text)
    raw_type: Mapped[str] = mapped_column(String(32), default="text")  # text | voice | image
    tool_calls: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["User"] = relationship("User", back_populates="messages")

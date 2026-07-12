from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateItemInput(BaseModel):
    section_name: str = Field(description="Name of the section (e.g. 'Schedule', 'Tasks', 'Idea Hub'). Must already exist; use create_section if you need a new one.")
    title: str
    content: str | None = None
    start_time: str | None = Field(
        default=None,
        description="ISO 8601 datetime in the user's timezone (e.g. '2024-06-10T15:00:00+08:00'). If provided, a default 15-minute reminder is created automatically.",
    )
    end_time: str | None = Field(default=None, description="ISO 8601 datetime in the user's timezone.")
    due_date: str | None = Field(default=None, description="ISO 8601 datetime in the user's timezone.")
    status: Literal["todo", "done", "archived", "in_progress", "cancelled"] | None = Field(default=None, description="Defaults to 'todo'.")
    priority: int | None = Field(default=None, ge=1, le=5, description="Priority from 1 (lowest) to 5 (highest). Defaults to 3.")
    tags: list[str] | None = Field(default=None, description="List of tags.")
    metadata: dict[str, Any] | None = Field(default=None, description="Custom JSON metadata.")
    reminder_message: str | None = Field(default=None, description="Custom reminder text.")


class UpdateItemInput(BaseModel):
    item_id: int
    title: str | None = None
    content: str | None = None
    section_name: str | None = Field(default=None, description="Move the item to this section.")
    start_time: str | None = None
    end_time: str | None = None
    due_date: str | None = None
    status: Literal["todo", "done", "archived", "in_progress", "cancelled"] | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateItemInput":
        fields = ["title", "content", "section_name", "start_time", "end_time", "due_date", "status", "priority", "tags", "metadata"]
        if all(getattr(self, f) is None for f in fields):
            raise ValueError("At least one field to update must be provided.")
        return self


class ItemIdInput(BaseModel):
    item_id: int


class SearchItemsInput(BaseModel):
    query: str | None = Field(default=None, description="Free-text search query.")
    section_name: str | None = None
    status: Literal["todo", "done", "archived", "in_progress", "cancelled"] | None = None
    time_range: dict[str, str] | None = Field(
        default=None,
        description="Object with 'start' and 'end' ISO 8601 datetimes.",
    )
    tags: list[str] | None = None
    limit: int = Field(default=20, ge=1, le=100)


class CreateSectionInput(BaseModel):
    name: str
    section_schema: dict[str, Any] | None = Field(default=None, description="Optional JSON schema for this section.")
    view_config: dict[str, Any] | None = Field(default=None, description="Optional view configuration.")


class SectionIdInput(BaseModel):
    section_id: int


class UpdateSectionInput(BaseModel):
    section_id: int
    name: str | None = None
    section_schema: dict[str, Any] | None = Field(default=None, description="Optional JSON schema for this section.")
    view_config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UpdateSectionInput":
        if self.name is None and self.section_schema is None and self.view_config is None:
            raise ValueError("At least one field to update must be provided.")
        return self


class SetReminderInput(BaseModel):
    item_id: int
    remind_at: str | None = Field(
        default=None,
        description="ISO 8601 datetime in the user's timezone. If omitted, defaults to 15 minutes before the item's start_time.",
    )
    message: str | None = Field(default=None, description="Custom reminder message.")


class ReminderIdInput(BaseModel):
    reminder_id: int


class ListRemindersInput(BaseModel):
    item_id: int | None = Field(default=None, description="Optionally filter reminders for a specific item.")


class OptionalDateInput(BaseModel):
    date: str | None = Field(default=None, description="ISO 8601 date in the user's timezone (e.g. '2024-06-10'). Defaults to today.")

    @field_validator("date", mode="before")
    @classmethod
    def allow_date_only(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Allow the LLM to pass a date-only string by appending midnight.
        if len(v) == 10:
            return f"{v}T00:00:00"
        return v


class OptionalWeekStartInput(BaseModel):
    week_start: str | None = Field(default=None, description="ISO 8601 date for Monday in the user's timezone. Defaults to current week.")

    @field_validator("week_start", mode="before")
    @classmethod
    def allow_date_only(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if len(v) == 10:
            return f"{v}T00:00:00"
        return v


class SendMessageInput(BaseModel):
    text: str


class AskUserInput(BaseModel):
    question: str


class SaveMemoryInput(BaseModel):
    content: str = Field(description="The memory to store.")
    category: Literal["preference", "fact", "goal", "routine", "conversation_style"] = "preference"
    importance: int = Field(default=3, ge=1, le=5)


class SearchMemoriesInput(BaseModel):
    query: str | None = Field(default=None, description="Free-text search query.")
    limit: int = Field(default=10, ge=1, le=50)


class MemoryIdInput(BaseModel):
    memory_id: int


class ReasoningInput(BaseModel):
    plan: str = Field(description="Describe the plan or reasoning for the next steps. No side effects.")


class EmptyInput(BaseModel):
    pass

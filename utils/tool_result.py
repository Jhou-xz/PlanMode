from typing import Any


class ToolResult:
    """Standardized envelope for tool execution results."""

    def __init__(self, ok: bool, data: dict[str, Any] | None = None, error_message: str | None = None) -> None:
        self.ok = ok
        self.data = data or {}
        self.error_message = error_message

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"success": self.ok, **self.data}
        if self.error_message is not None:
            result["error"] = self.error_message
        return result

    @classmethod
    def success(cls, **kwargs: Any) -> "ToolResult":
        return cls(ok=True, data=kwargs)

    @classmethod
    def error(cls, message: str, **kwargs: Any) -> "ToolResult":
        return cls(ok=False, error_message=message, data=kwargs)

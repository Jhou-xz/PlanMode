from sqlalchemy.ext.asyncio import AsyncSession

from services.tools.schemas import ReasoningInput
from utils.tool_result import ToolResult


async def reasoning(session: AsyncSession, user, input: ReasoningInput) -> ToolResult:
    """No-op tool that lets the model think out loud without side effects."""
    return ToolResult.success(plan=input.plan)

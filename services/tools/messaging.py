from sqlalchemy.ext.asyncio import AsyncSession

from services.tools.schemas import AskUserInput, SendMessageInput
from utils.tool_result import ToolResult


async def send_message(session: AsyncSession, user, input: SendMessageInput) -> ToolResult:
    return ToolResult.success(final_response=input.text, type="send_message")


async def ask_user(session: AsyncSession, user, input: AskUserInput) -> ToolResult:
    return ToolResult.success(final_response=input.question, type="ask_user")

from sqlalchemy.ext.asyncio import AsyncSession


async def send_message(session: AsyncSession, user, **kwargs) -> dict:
    return {"final_response": kwargs.get("text", "Got it."), "type": "send_message"}


async def ask_user(session: AsyncSession, user, **kwargs) -> dict:
    return {"final_response": kwargs.get("question", "Could you clarify?"), "type": "ask_user"}

from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from services.memory import search_memories as search_memories_crud
from services.tools.schemas import MemoryIdInput, SaveMemoryInput, SearchMemoriesInput
from utils.tool_result import ToolResult


async def save_memory(session: AsyncSession, user, input: SaveMemoryInput) -> ToolResult:
    memory = await crud.create_memory(
        session=session,
        user_id=user.id,
        content=input.content,
        category=input.category,
        importance=input.importance,
    )
    return ToolResult.success(
        memory_id=memory.id,
        content=memory.content,
        category=memory.category,
        importance=memory.importance,
    )


async def search_memories(session: AsyncSession, user, input: SearchMemoriesInput) -> ToolResult:
    memories = await search_memories_crud(session, user.id, query=input.query, limit=input.limit)
    return ToolResult.success(
        count=len(memories),
        memories=[
            {
                "id": m.id,
                "content": m.content,
                "category": m.category,
                "importance": m.importance,
            }
            for m in memories
        ],
    )


async def delete_memory(session: AsyncSession, user, input: MemoryIdInput) -> ToolResult:
    memory = await crud.get_memory(session, input.memory_id)
    if memory is None:
        return ToolResult.error(f"Memory {input.memory_id} not found")
    if memory.user_id != user.id:
        return ToolResult.error("Memory does not belong to this user")
    return ToolResult.error(
        "This will permanently delete the memory. Ask the user to confirm before proceeding.",
        needs_confirmation=True,
        memory_id=input.memory_id,
        content=memory.content,
    )


async def confirm_delete_memory(session: AsyncSession, user, input: MemoryIdInput) -> ToolResult:
    memory = await crud.get_memory(session, input.memory_id)
    if memory is None or memory.user_id != user.id:
        return ToolResult.error(f"Memory {input.memory_id} not found")
    await session.delete(memory)
    await session.commit()
    return ToolResult.success(message=f"Memory {input.memory_id} deleted")

from sqlalchemy.ext.asyncio import AsyncSession
from database import crud


async def create_section(session: AsyncSession, user, **kwargs) -> dict:
    name = kwargs.get("name")
    if not name:
        return {"error": "name is required"}
    section = await crud.create_section(
        session=session,
        user_id=user.id,
        name=name,
        schema=kwargs.get("schema"),
        view_config=kwargs.get("view_config"),
    )
    return {
        "success": True,
        "section_id": section.id,
        "name": section.name,
        "slug": section.slug,
    }

from sqlalchemy.ext.asyncio import AsyncSession

from database import crud
from services.tools.schemas import CreateSectionInput, EmptyInput, SectionIdInput, UpdateSectionInput
from utils.tool_result import ToolResult


async def create_section(session: AsyncSession, user, input: CreateSectionInput) -> ToolResult:
    section = await crud.create_section(
        session=session,
        user_id=user.id,
        name=input.name,
        schema=input.section_schema,
        view_config=input.view_config,
    )
    return ToolResult.success(
        section_id=section.id,
        name=section.name,
        slug=section.slug,
    )


async def list_sections(session: AsyncSession, user, input: EmptyInput) -> ToolResult:
    sections = await crud.list_sections(session, user.id)
    return ToolResult.success(
        count=len(sections),
        sections=[
            {
                "id": s.id,
                "name": s.name,
                "slug": s.slug,
                "section_type": s.section_type,
            }
            for s in sections
        ],
    )


async def update_section(session: AsyncSession, user, input: UpdateSectionInput) -> ToolResult:
    fields: dict = {}
    if input.name is not None:
        fields["name"] = input.name
    if input.section_schema is not None:
        fields["schema"] = input.section_schema
    if input.view_config is not None:
        fields["view_config"] = input.view_config

    if not fields:
        return ToolResult.error("No fields provided to update")

    updated = await crud.update_section(session, input.section_id, **fields)
    if updated is None:
        return ToolResult.error(f"Section {input.section_id} not found")
    return ToolResult.success(
        section_id=updated.id,
        name=updated.name,
        slug=updated.slug,
    )


async def delete_section(session: AsyncSession, user, input: SectionIdInput) -> ToolResult:
    section = await crud.get_section(session, input.section_id)
    if section is None:
        return ToolResult.error(f"Section {input.section_id} not found")
    if section.section_type == "system":
        return ToolResult.error(f"Cannot delete system section '{section.name}'")
    return ToolResult.error(
        "This will permanently delete the section and all its items. Ask the user to confirm before proceeding.",
        needs_confirmation=True,
        section_id=input.section_id,
        name=section.name,
    )


async def confirm_delete_section(session: AsyncSession, user, input: SectionIdInput) -> ToolResult:
    success = await crud.delete_section(session, input.section_id)
    if not success:
        return ToolResult.error(f"Section {input.section_id} not found")
    return ToolResult.success(message=f"Section {input.section_id} deleted")

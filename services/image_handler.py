import base64
from io import BytesIO
from typing import List
import aiohttp
import discord

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False


async def download_attachment(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()


def bytes_to_b64_image(data: bytes, mime: str = "image/png") -> str:
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


async def build_image_content(message: discord.Message) -> List[str]:
    """Return base64 data URIs for image attachments in the message."""
    images = []
    for attachment in message.attachments:
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            continue
        data = await download_attachment(attachment.url)
        b64 = bytes_to_b64_image(data, mime=attachment.content_type)
        images.append(b64)
    return images


def ocr_image(data: bytes) -> str:
    if not OCR_AVAILABLE:
        return ""
    img = Image.open(BytesIO(data))
    return pytesseract.image_to_string(img).strip()

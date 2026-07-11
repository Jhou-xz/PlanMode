import os
import pytest
from services.intent_parser import parse_intent


@pytest.mark.skipif(
    os.environ.get("DEEPSEEK_API_KEY", "").startswith("dummy_") or not os.environ.get("DEEPSEEK_API_KEY"),
    reason="requires a real DeepSeek API key",
)
@pytest.mark.asyncio
async def test_parse_reminder():
    result = await parse_intent(
        "Remind me to call David tomorrow at 4pm",
        timezone="Asia/Shanghai",
        memories=[],
    )
    assert result["intent"] == "reminder"
    assert "reminder" in result["entities"]
    assert result["language"] == "en"

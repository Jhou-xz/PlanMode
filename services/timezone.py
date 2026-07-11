from zoneinfo import ZoneInfo, available_timezones
from difflib import get_close_matches


COMMON_ALIASES = {
    "shanghai": "Asia/Shanghai",
    "beijing": "Asia/Shanghai",
    "china": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "taipei": "Asia/Taipei",
    "tokyo": "Asia/Tokyo",
    "japan": "Asia/Tokyo",
    "seoul": "Asia/Seoul",
    "korea": "Asia/Seoul",
    "singapore": "Asia/Singapore",
    "new york": "America/New_York",
    "nyc": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "la": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "sf": "America/Los_Angeles",
    "chicago": "America/Chicago",
    "london": "Europe/London",
    "uk": "Europe/London",
    "paris": "Europe/Paris",
    "france": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "germany": "Europe/Berlin",
    "moscow": "Europe/Moscow",
    "russia": "Europe/Moscow",
    "sydney": "Australia/Sydney",
    "melbourne": "Australia/Melbourne",
    "utc": "UTC",
    "gmt": "UTC",
    "est": "America/New_York",
    "cst": "America/Chicago",
    "mst": "America/Denver",
    "pst": "America/Los_Angeles",
    "jst": "Asia/Tokyo",
    "cst china": "Asia/Shanghai",
}


async def resolve_timezone(text: str, llm_parse_fn=None) -> str | None:
    """
    Resolve a natural-language timezone description to an IANA timezone.
    Returns None if unresolvable.
    """
    text = text.strip().strip("`'")  # Remove markdown/code quotes

    # 1. Direct ZoneInfo match
    try:
        ZoneInfo(text)
        return text
    except Exception:
        pass

    # 2. Common aliases
    normalized = text.lower().replace(",", " ").strip()
    if normalized in COMMON_ALIASES:
        return COMMON_ALIASES[normalized]

    # 3. Fuzzy match against all IANA timezones
    matches = get_close_matches(text, available_timezones(), n=1, cutoff=0.85)
    if matches:
        return matches[0]

    # 4. LLM fallback (if provided)
    if llm_parse_fn:
        parsed = await llm_parse_fn(text)
        if parsed and parsed != "UNKNOWN":
            try:
                ZoneInfo(parsed)
                return parsed
            except Exception:
                pass

    return None


def build_timezone_prompt(user_text: str) -> list:
    return [
        {
            "role": "system",
            "content": (
                "You are a timezone resolver. The user is telling you where they are or what timezone they are in. "
                "Return ONLY the IANA timezone string (e.g. Asia/Shanghai, America/New_York, Europe/Berlin). "
                "If you cannot determine it, return exactly UNKNOWN."
            ),
        },
        {"role": "user", "content": f'Where I am: "{user_text}"'},
    ]

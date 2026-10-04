import re


def normalize_admission_no(value) -> str:
    """
    Make admission numbers comparable.

    Trims, uppercases and removes spaces around slashes, so that
    ' abc/123/2020 ' and 'ABC / 123 / 2020' both become 'ABC/123/2020'.
    Used on upload AND on student lookup, so both sides always match.
    """
    if value is None:
        return ""
    value = str(value).strip().upper()
    value = re.sub(r"\s*/\s*", "/", value)
    value = re.sub(r"\s+", " ", value)
    return value

import re


def normalize_admission_no(value) -> str:
    """
    Make admission numbers comparable.

    Removes all whitespace and uppercases. Also fixes the classic Excel
    problem where 11300 arrives as 11300.0 (float) when a list is uploaded.
    Used on upload AND on student lookup, so both sides always match.
    """
    if value is None:
        return ""
    value = re.sub(r"\s+", "", str(value)).upper()
    if re.fullmatch(r"\d+\.0+", value):
        value = value.split(".")[0]
    return value
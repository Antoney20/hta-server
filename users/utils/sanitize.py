import re


def sanitize_email(value: str) -> str:
    """
    Sanitize email input safely.

    - trims whitespace
    - converts to lowercase
    - removes control/invisible characters
    - limits length to 100 chars
    """

    if not value:
        return ""

    # ensure string
    value = str(value)

    # remove leading/trailing whitespace
    value = value.strip().lower()

    # remove control characters 
    value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)

    # collapse internal spaces (rare but safe)
    value = re.sub(r'\s+', '', value)

    # enforce max length
    value = value[:50]

    return value



def sanitize_text(value: str, max_length: int = 100) -> str:
    """
    Sanitize general text input.

    - converts to string
    - trims whitespace
    - removes control characters
    - normalizes spaces
    - enforces max length
    """

    if not value:
        return ""

    # ensure string
    value = str(value)

    # strip leading/trailing whitespace
    value = value.strip()

    # remove control / invisible characters
    value = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', value)

    # normalize multiple spaces
    value = re.sub(r'\s+', ' ', value)

    # enforce max length
    value = value[:max_length]

    return value
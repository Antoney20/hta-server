import re
from django.utils.html import strip_tags

# common patterns
BLOCK_PATTERNS = [
    r"\{\{.*?\}\}",
    r"__import__",
    r"exec\(",
    r"system\(",
    r"popen\(",
    r"\.\./",
    r"<script.*?>.*?</script>",
]

compiled = [re.compile(p, re.IGNORECASE) for p in BLOCK_PATTERNS]


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")

def sanitize_text(value: str):
    if not value:
        return value

    value = strip_tags(value)

    for pattern in compiled:
        value = pattern.sub("", value)

    value = re.sub(r"\s+", " ", value).strip()

    return value


def contains_attack(value: str) -> bool:
    if not isinstance(value, str):
        return False

    lowered = value.lower()
    return any(p.search(lowered) for p in compiled)
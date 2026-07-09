import json
from .context import Context


def _serialize(content) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, indent=2)


def render(context: Context) -> str:
    """
    Compose system framing + task instruction + sources + output contract into a
    single string the provider sends. Structured, labelled, deterministic.
    """
    parts: list[str] = [context.system_context(), ""]

    parts.append("# TASK")
    parts.append(context.instruction.strip())
    parts.append("")

    if context.sources:
        parts.append("# CONTEXT")
        for src in context.sources:
            parts.append(f"## {src.label}")
            parts.append(_serialize(src.content))
            parts.append("")

    if context.output_contract.strip():
        parts.append("# REQUIRED OUTPUT FORMAT")
        parts.append(
            "Return ONLY valid JSON in exactly this shape, with no other text:"
        )
        parts.append(context.output_contract.strip())

    return "\n".join(parts)
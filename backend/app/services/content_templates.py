import html
import re


PLACEHOLDER = re.compile(r"{{\s*([A-Za-z][A-Za-z0-9_.-]*)\s*}}")
VALID_CONTENT_TYPES = {"text/plain", "text/html"}
VALID_CATEGORIES = {"clinical", "document", "email", "sms"}


def validate_template(subject: str | None, content: str, content_type: str, category: str, allowed_variables: list[str]) -> list[str]:
    if content_type not in VALID_CONTENT_TYPES:
        raise ValueError("Unsupported template content type")
    if category not in VALID_CATEGORIES:
        raise ValueError("Unsupported template category")
    allowed = sorted(set(allowed_variables))
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", item) for item in allowed):
        raise ValueError("Template variable names are invalid")
    used = set(PLACEHOLDER.findall((subject or "") + "\n" + content))
    unknown = sorted(used - set(allowed))
    if unknown:
        raise ValueError(f"Template uses undeclared variables: {', '.join(unknown)}")
    return allowed


def render_template(subject: str | None, content: str, content_type: str, allowed_variables: list[str], variables: dict[str, object]) -> tuple[str | None, str]:
    unknown = sorted(set(variables) - set(allowed_variables))
    if unknown:
        raise ValueError(f"Unexpected variables: {', '.join(unknown)}")
    missing = sorted(set(PLACEHOLDER.findall((subject or "") + "\n" + content)) - set(variables))
    if missing:
        raise ValueError(f"Missing variables: {', '.join(missing)}")

    def replace(match: re.Match[str]) -> str:
        value = str(variables[match.group(1)])
        return html.escape(value) if content_type == "text/html" else value

    return PLACEHOLDER.sub(replace, subject) if subject else None, PLACEHOLDER.sub(replace, content)

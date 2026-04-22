import re
import unicodedata

def slugify(text: str) -> str:
    if not text:
        return "untitled"
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    kebab = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return kebab or "untitled"

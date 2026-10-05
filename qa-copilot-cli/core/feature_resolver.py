import json
import re
from functools import lru_cache

from .config import FEATURE_ALIASES_PATH

_DEFAULT_ALIASES = {
    "notes": ["notes", "note"],
    "archive-content-type": [
        "archive-content-type",
        "archived-content-type",
        "archived_content_type",
        "archive content type",
        "archived content type",
    ],
}


def normalize_feature_key(value: str) -> str:
    value = (value or "").strip().lower().replace("_", "-").replace(" ", "-")
    return re.sub(r"-+", "-", value)


@lru_cache(maxsize=1)
def load_feature_aliases() -> dict[str, list[str]]:
    try:
        raw = json.loads(FEATURE_ALIASES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = _DEFAULT_ALIASES
    if not isinstance(raw, dict):
        raw = _DEFAULT_ALIASES

    out: dict[str, list[str]] = {}
    for key, aliases in raw.items():
        canon = normalize_feature_key(key)
        values = aliases if isinstance(aliases, list) else [str(aliases)]
        normalised = [normalize_feature_key(v) for v in values if str(v).strip()]
        out[canon] = sorted(set([canon] + normalised))
    return out or _DEFAULT_ALIASES


def canonical_feature_key(value: str) -> str:
    """Map an indexed alias value back to its canonical key."""
    normalised = normalize_feature_key(value)
    for canonical, aliases in load_feature_aliases().items():
        if normalised == canonical or normalised in aliases:
            return canonical
    return normalised


def resolve_feature_key(summary: str, feature_prefix: str = "", extra_text: str = "") -> str:
    """Return the first canonical feature whose alias appears as a whole word/phrase."""
    # Punctuation becomes a delimiter so "Notes: add checklist" still matches "notes".
    text = re.sub(r"[^a-z0-9]+", "-", f"{summary} {feature_prefix} {extra_text}".lower())
    for canon, words in load_feature_aliases().items():
        for token in words:
            token = re.sub(r"[^a-z0-9]+", "-", token).strip("-")
            if token and re.search(rf"(^|-)({re.escape(token)})(-|$)", text):
                return canon
    return ""

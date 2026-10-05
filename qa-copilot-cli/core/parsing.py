"""Jira content parsing, ported from custom-agent-ui/pages/1_Test_Case_Generator.py."""
import re

FEATURE_PREFIXES = {
    "notes": "TC-NOTES",
    "archive": "TC-ARCHIVE-CONTENT-TYPE",
    "content": "TC-CONTENT",
    "initiative": "TC-INIT",
    "campaign": "TC-INIT",
    "idea": "TC-IDEA",
    "gallery": "TC-GALLERY",
    "member": "TC-MEMBERS",
    "setting": "TC-SETTINGS",
    "calendar": "TC-CALENDAR",
    "search": "TC-SEARCH",
    "dashboard": "TC-DASH",
    "notification": "TC-NOTIF",
    "napa": "TC-DASH",
}

_BUG_KEYWORDS = ("bug", "fix", "defect", "regression", "broken", "error", "fail")
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{100,}={0,2}")
_BULLET_PREFIX = re.compile(r"^[-*•]\s+|^\d+\.\s+")


def adf_to_markdown(node) -> str:
    """Convert Atlassian Document Format JSON to Markdown, keeping headings and lists."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "\n".join(adf_to_markdown(n) for n in node)
    if not isinstance(node, dict):
        return str(node)
    ntype = node.get("type", "")
    content = node.get("content") or []
    if ntype == "text":
        return node.get("text", "")
    if ntype == "doc":
        parts = [adf_to_markdown(c) for c in content]
        return "\n".join(p for p in parts if p.strip())
    if ntype == "paragraph":
        return "".join(adf_to_markdown(c) for c in content)
    if ntype == "heading":
        level = node.get("attrs", {}).get("level", 2)
        return "#" * level + " " + "".join(adf_to_markdown(c) for c in content)
    if ntype == "bulletList":
        return "\n".join(adf_to_markdown(c) for c in content)
    if ntype == "orderedList":
        lines = []
        for i, c in enumerate(content, 1):
            lines.append(f"{i}. {adf_to_markdown(c).lstrip('- ').strip()}")
        return "\n".join(lines)
    if ntype == "listItem":
        return "- " + "\n".join(adf_to_markdown(c) for c in content).strip()
    if ntype == "hardBreak":
        return "\n"
    if ntype == "rule":
        return "---"
    if ntype == "codeBlock":
        return "```\n" + "".join(adf_to_markdown(c) for c in content) + "\n```"
    if ntype == "blockquote":
        return "> " + "\n".join(adf_to_markdown(c) for c in content)
    if content:
        return "".join(adf_to_markdown(c) for c in content)
    return node.get("text", "")


def extract_acceptance_criteria(content: str) -> list[str]:
    """Extract AC items, carrying group labels onto sub-bullets and one item per Gherkin scenario."""
    ac: list[str] = []
    in_ac = False
    stop_named = re.compile(
        r"^#{1,4}\s+(definition of done|notes?|out of scope|assumptions?|dependencies|steps to reproduce)",
        re.IGNORECASE,
    )
    stop_unnumbered = re.compile(
        r"^(definition of done|notes?:|out of scope|assumptions?|dependencies|steps to reproduce)",
        re.IGNORECASE,
    )
    md_heading = re.compile(r"^#{1,4}\s+(.+)")
    colon_header = re.compile(r"^[^-*•\d].*:\s*$")
    bullet_start = re.compile(r"^[-*•]|^\d+\.")
    strip_bullet = re.compile(r"^[-*•]\s*|^\d+\.\s+")
    gherkin = re.compile(r"^(Given|When|Then|And|But)\b", re.IGNORECASE)
    sentence_end = re.compile(r"[.?!]\s*$")

    lines = [ln.strip() for ln in content.splitlines()]
    current_group = ""
    gherkin_buf: list[str] = []

    def with_group(text: str) -> str:
        return f"{current_group}: {text}" if current_group else text

    def flush_gherkin() -> None:
        if gherkin_buf:
            ac.append(with_group(" / ".join(gherkin_buf)))
            gherkin_buf.clear()

    i = 0
    while i < len(lines):
        s = lines[i]
        i += 1
        if not s:
            continue
        if re.search(r"acceptance criteria", s, re.IGNORECASE):
            in_ac = True
            current_group = ""
            continue
        if not in_ac:
            continue
        if stop_named.match(s) or stop_unnumbered.match(s):
            break
        m = md_heading.match(s)
        if m:
            current_group = m.group(1).strip()
            continue
        if gherkin.match(s):
            if re.match(r"^Given\b", s, re.IGNORECASE):
                flush_gherkin()
            gherkin_buf.append(s)
            continue
        if re.match(r"^-{2,}$", s):
            continue
        if bullet_start.match(s):
            clean = strip_bullet.sub("", s).strip()
            if clean:
                ac.append(with_group(clean))
            continue
        if colon_header.match(s):
            current_group = s.rstrip(":").strip()
            continue
        next_s = next((lines[j] for j in range(i, len(lines)) if lines[j]), "")
        is_short_label = (
            len(s.split()) <= 6
            and not sentence_end.search(s)
            and bullet_start.match(next_s)
        )
        if is_short_label:
            current_group = s
        else:
            ac.append(with_group(s))

    flush_gherkin()
    return ac


def extract_steps_to_reproduce(content: str) -> list[str]:
    steps: list[str] = []
    in_steps = False
    stop_sections = re.compile(
        r"^(#{1,4}\s|acceptance criteria|definition of done|notes?:|out of scope)",
        re.IGNORECASE,
    )
    for line in content.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.search(r"steps to reproduce", s, re.IGNORECASE):
            in_steps = True
            continue
        if in_steps:
            if stop_sections.match(s):
                break
            clean = _BULLET_PREFIX.sub("", s).strip()
            if clean:
                steps.append(clean)
    return steps


def extract_section(content: str, heading: str) -> str:
    """Return the body of a '## <heading>' section, stopping at the next Markdown heading."""
    out: list[str] = []
    inside = False
    start = re.compile(rf"^#{{1,4}}\s+{re.escape(heading)}\b", re.IGNORECASE)
    stop = re.compile(r"^#{1,4}\s")
    for line in content.splitlines():
        s = line.strip()
        if start.match(s):
            inside = True
            continue
        if inside:
            if stop.match(s):
                break
            out.append(line)
    return "\n".join(out).strip()


def strip_base64(text: str) -> str:
    return _BASE64_BLOB.sub("[image-removed]", text or "")


def detect_feature_prefix(summary: str) -> str:
    s = (summary or "").lower()
    for kw, prefix in FEATURE_PREFIXES.items():
        if kw in s:
            return prefix
    return "TC-FEATURE"


def detect_ticket_type(issuetype: str, summary: str) -> str:
    if issuetype:
        return "Bug" if issuetype.strip().lower() == "bug" else "Story"
    return "Bug" if any(kw in (summary or "").lower() for kw in _BUG_KEYWORDS) else "Story"


def normalize_ticket(
    story_key: str,
    summary: str,
    description: str,
    ac_list: list[str],
    str_list: list[str],
    comments: str,
    ticket_type: str,
    feature_key: str,
) -> dict:
    """Canonical ticket: AC → requirements; else STR; else description lines (context only otherwise)."""
    if ac_list:
        primary_source, requirements = "ac", list(ac_list)
    elif str_list:
        primary_source, requirements = "str", list(str_list)
    elif description.strip():
        primary_source = "description"
        requirements = [
            _BULLET_PREFIX.sub("", ln.strip()).strip()
            for ln in description.splitlines()
            if len(_BULLET_PREFIX.sub("", ln.strip()).strip()) > 15
        ]
    else:
        primary_source, requirements = "none", []

    return {
        "ticket_key": story_key,
        "ticket_type": ticket_type,
        "summary": summary,
        "feature_key": feature_key,
        "primary_source": primary_source,
        "requirements": requirements,
        "steps_to_reproduce": list(str_list),
        "description_notes": strip_base64(description).strip()[:3000],
        "comments": (comments or "").strip(),
    }

"""Feature-scoped retrieval over the existing FAISS index, without any Streamlit dependency."""
import re
from functools import lru_cache

from . import config
from .feature_resolver import canonical_feature_key, resolve_feature_key

_JIRA_KEY_RE = re.compile(r"(?<![A-Z0-9_])[A-Z][A-Z0-9_]+-\d+(?![A-Z0-9_-])", re.IGNORECASE)


class RetrievalError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def load_vectorstore():
    if not (config.FAISS_INDEX_DIR / "index.faiss").exists():
        raise RetrievalError(
            f"FAISS index not found at {config.FAISS_INDEX_DIR}. Run rag/ingest_all.py first."
        )
    from langchain_community.vectorstores import FAISS
    from langchain_huggingface import HuggingFaceEmbeddings

    embeddings = HuggingFaceEmbeddings(model_name=config.EMBEDDING_MODEL)
    # Safe only because the index is produced locally by rag/ingest_all.py.
    return FAISS.load_local(
        str(config.FAISS_INDEX_DIR), embeddings, allow_dangerous_deserialization=True
    )


def _path_text(meta: dict) -> str:
    rel = str(meta.get("relative_source_path", ""))
    src = str(meta.get("source", ""))
    return f"{src} {rel}".lower().replace("\\", "/")


def search(query: str, top_k: int = 10, max_candidates: int = 60) -> list[dict]:
    vs = load_vectorstore()
    k = min(max(top_k, 1), max_candidates)
    results, seen = [], set()
    for d in vs.similarity_search(query, k=k):
        item = {"content": d.page_content, **(d.metadata or {})}
        identity = item.get("id") or item["content"]
        if identity in seen:
            continue
        seen.add(identity)
        results.append(item)
    return results

def _normalise_repo_path(value: str) -> str:
    return str(value or "").strip().replace("\\", "/").lstrip("./").lower()


def get_indexed_cypress_chunks(
    repo_root,
    paths: list[str],
    query: str,
    chunks_per_path: int = 3,
    max_chars_per_chunk: int = 900,
) -> dict:
    """Return only FAISS chunks whose indexed repo path exactly matches a requested Cypress file."""
    vs = load_vectorstore()
    root = str(repo_root).replace("\\", "/").rstrip("/").lower()
    expected = {_normalise_repo_path(path): path.replace("\\", "/") for path in paths}
    grouped: dict[str, list[dict]] = {path: [] for path in expected.values()}
    query_terms = {t for t in re.split(r"\W+", query.lower()) if len(t) > 2}

    for doc in vs.docstore._dict.values():
        meta = getattr(doc, "metadata", None) or {}
        raw_source = str(meta.get("source", "") or "")
        raw_repo = str(meta.get("repo_path", "") or meta.get("relative_source_path", "") or "")
        source_norm = raw_source.replace("\\", "/").lower()
        repo_norm = _normalise_repo_path(raw_repo)

        matched_path = None
        if repo_norm in expected:
            matched_path = expected[repo_norm]
        elif source_norm.startswith(root + "/"):
            relative = source_norm[len(root) + 1:]
            if relative in expected:
                matched_path = expected[relative]
        if not matched_path:
            continue

        content = getattr(doc, "page_content", "") or ""
        doc_id = str(meta.get("id", ""))
        content_terms = {t for t in re.split(r"\W+", content.lower()) if len(t) > 2}
        score = len(query_terms & content_terms)
        suffix = re.search(r"(?:chunk|_)(\d+)$", doc_id)
        order = int(suffix.group(1)) if suffix else 0
        grouped[matched_path].append({
            "id": doc_id,
            "path": matched_path,
            "type": str(meta.get("type", "")),
            "content": content,
            "score": score,
            "order": order,
        })

    chunks, missing_paths = [], []
    for path in expected.values():
        candidates = grouped[path]
        if not candidates:
            missing_paths.append(path)
            continue
        candidates.sort(key=lambda item: (-item["score"], item["order"], item["id"]))
        first_chunk = min(candidates, key=lambda item: (item["order"], item["id"]))
        chosen = [first_chunk]
        chosen_ids = {first_chunk["id"]}
        chosen.extend(
            item for item in candidates
            if item["id"] not in chosen_ids
        )
        seen_content = set()
        count = 0
        for item in chosen:
            dedupe = item["content"].strip()
            if dedupe in seen_content:
                continue
            seen_content.add(dedupe)
            chunks.append({
                "id": item["id"],
                "path": path,
                "type": item["type"],
                "snippet": item["content"][:max_chars_per_chunk],
                "relevance_score": item["score"],
            })
            count += 1
            if count >= chunks_per_path:
                break
    return {"chunks": chunks, "missing_paths": missing_paths}


def get_indexed_cypress_file_chunks(
    repo_root,
    path: str,
    exclude_chunk_ids: list[str] | tuple[str, ...] = (),
    limit: int = 2,
    max_chars_per_chunk: int = 850,
) -> dict:
    """Return the next indexed chunks for one exact Cypress repository path."""
    vs = load_vectorstore()
    root = str(repo_root).replace("\\", "/").rstrip("/").lower()
    expected = _normalise_repo_path(path)
    excluded = set(exclude_chunk_ids)
    candidates, seen = [], set()

    for doc in vs.docstore._dict.values():
        meta = getattr(doc, "metadata", None) or {}
        raw_source = str(meta.get("source", "") or "")
        raw_repo = str(meta.get("repo_path", "") or meta.get("relative_source_path", "") or "")
        source_norm = raw_source.replace("\\", "/").lower()
        repo_norm = _normalise_repo_path(raw_repo)
        if repo_norm != expected and not (
            source_norm.startswith(root + "/")
            and _normalise_repo_path(source_norm[len(root) + 1:]) == expected
        ):
            continue

        content = getattr(doc, "page_content", "") or ""
        doc_id = str(meta.get("id", ""))
        identity = doc_id or content
        if identity in seen:
            continue
        seen.add(identity)
        suffix = re.search(r"(?:chunk|_)(\d+)$", doc_id)
        order = int(suffix.group(1)) if suffix else 0
        candidates.append((order, doc_id, content, meta))

    candidates.sort(key=lambda item: (item[0], item[1]))
    remaining = [item for item in candidates if item[1] not in excluded]
    page_size = min(max(int(limit), 1), 2)
    chunks = [
        {
            "id": doc_id,
            "path": path.replace("\\", "/"),
            "type": str(meta.get("type", "")),
            "snippet": content[:max_chars_per_chunk],
            "relevance_score": 0,
        }
        for _, doc_id, content, meta in remaining[:page_size]
    ]
    return {
        "chunks": chunks,
        "total_chunks": len(candidates),
        "remaining_chunks": len(remaining),
    }

def search_filtered(
    query: str,
    top_k: int = 6,
    feature_key: str = "",
    doc_domain: str = "",
    path_contains: str = "",
    source_eq: str = "",
    max_candidates: int = 60,
    offset: int = 0,
    max_retries: int = 2,
) -> list[dict]:
    """Search a wider candidate pool, then keep only metadata matches.

    This uses a bounded retry policy instead of paging forever: the first pass stays tight, a
    single broader re-search happens if the first filtered results are too shallow, and the function
    stops once it has either enough relevant matches or it has exhausted its retry budget.
    """
    def _collect(pool_size: int) -> list[dict]:
        if source_eq:
            vs = load_vectorstore()
            fetch_k = max(1000, pool_size * 20)
            docs = vs.similarity_search(
                query,
                k=pool_size,
                filter={"source": source_eq},
                fetch_k=fetch_k,
            )
            candidates, seen = [], set()
            for d in docs:
                item = {"content": d.page_content, **(d.metadata or {})}
                identity = item.get("id") or item["content"]
                if identity not in seen:
                    seen.add(identity)
                    candidates.append(item)
        else:
            candidates = search(query, top_k=pool_size, max_candidates=pool_size)

        feature_l = canonical_feature_key(feature_key) if feature_key else ""
        domain_l, path_l, source_l = doc_domain.lower(), path_contains.lower(), source_eq.lower()
        out = []
        for doc in candidates:
            doc_feature = canonical_feature_key(str(doc.get("feature_key", "")))
            if feature_l and doc_feature != feature_l:
                continue
            if domain_l and str(doc.get("doc_domain", "")).lower() != domain_l:
                continue
            if source_l and str(doc.get("source", "")).lower() != source_l:
                continue
            if path_l and path_l not in _path_text(doc):
                continue
            out.append(doc)
        return out

    pool_sizes = [max_candidates]
    for retry in range(1, max_retries + 1):
        pool_sizes.append(min(180 * retry, max_candidates * (retry + 1)))

    matches = []
    for pool_size in pool_sizes[: max_retries + 1]:
        matches = _collect(pool_size)
        if len(matches) >= max(0, offset) + max(1, top_k):
            break

    start = max(0, offset)
    end = start + max(1, top_k)
    return matches[start:end]


def _docstore_feature_chunks(
    feature_key: str,
    doc_domain: str,
    path_contains: str,
    max_items: int,
    query_hint: str,
    offset: int = 0,
) -> list[dict]:
    """Deterministic fallback when semantic top-k misses feature-scoped docs."""
    vs = load_vectorstore()
    tokens = {t for t in re.split(r"\W+", query_hint.lower()) if len(t) > 3}
    feature_l = canonical_feature_key(feature_key)
    domain_l, path_l = doc_domain.lower(), path_contains.lower()
    scored = []
    for d in vs.docstore._dict.values():
        meta = getattr(d, "metadata", None) or {}
        if canonical_feature_key(str(meta.get("feature_key", ""))) != feature_l:
            continue
        if domain_l and str(meta.get("doc_domain", "")).lower() != domain_l:
            continue
        if path_l and path_l not in _path_text(meta):
            continue
        content = getattr(d, "page_content", "") or ""
        content_l = content.lower()
        score = sum(1 for t in tokens if t in content_l)
        score += 2 if feature_l in content_l else 0
        score += 1 if meta.get("heading") else 0
        scored.append((score, {"content": content, **meta}))
    scored.sort(key=lambda x: x[0], reverse=True)
    start = max(0, offset)
    return [doc for _, doc in scored[start:start + max_items]]


def _compact(docs: list[dict], max_items: int, max_chars: int) -> list[dict]:
    out = []
    for doc in docs[:max_items]:
        content = (doc.get("content") or "").strip()
        if not content:
            continue
        out.append({
            "id": str(doc.get("id", "")),
            "path": str(doc.get("relative_source_path") or doc.get("source") or doc.get("id", "unknown")),
            "heading": doc.get("heading", ""),
            "snippet": content[:max_chars],
        })
    return out


def get_product_knowledge(
    feature_key: str, summary: str, extra_text: str = "", top_k: int = 6, offset: int = 0
) -> list[dict]:
    """Same-feature product docs only; returns [] rather than borrowing from other features."""
    if not feature_key:
        return []
    query = f"{summary} {feature_key} {extra_text[:500]} product knowledge"
    start = max(0, offset)
    end = start + max(1, top_k)
    docs = search_filtered(
        query, top_k=end, feature_key=feature_key,
        doc_domain="product_knowledge", path_contains="product_knowledge",
    )
    if not docs:
        docs = _docstore_feature_chunks(
            feature_key, "product_knowledge", "product_knowledge", end,
            f"{summary} {extra_text[:300]}",
        )
    return _compact(docs[start:end], top_k, 700)


def get_automation_feature_context(
    feature_key: str, summary: str, extra_text: str = "", top_k: int = 5, offset: int = 0
) -> list[dict]:
    """Return automation/repository conventions scoped to the resolved feature."""
    if not feature_key:
        return []
    query = f"{summary} {feature_key} {extra_text[:500]} automation framework patterns"
    start = max(0, offset)
    end = start + max(1, top_k)
    docs = search_filtered(
        query,
        top_k=end,
        feature_key=feature_key,
        doc_domain="automation_feature_context",
        path_contains="automation/feature-context",
    )
    if not docs:
        docs = _docstore_feature_chunks(
            feature_key,
            "automation_feature_context",
            "automation/feature-context",
            end,
            f"{summary} {extra_text[:300]}",
        )
    return _compact(docs[start:end], top_k, 700)


def get_qa_guidance(
    summary: str, extra_text: str = "", top_k: int = 6, offset: int = 0
) -> list[dict]:
    """Retrieve shared QA strategy and automation guidelines from the repository docs."""
    query = f"{summary} {extra_text[:400]} QA test design strategy automation guidelines"
    candidates = search(query, top_k=max(40, offset + top_k))
    paths = ("qa/testing-strategy.md", "qa/automation-guidelines.md", "automation/automation-guidelines.md")
    matches = [
        doc for doc in candidates
        if str(doc.get("doc_domain", "")).lower() == "docs_general"
        and any(path in _path_text(doc) for path in paths)
    ]
    if not matches:
        vs = load_vectorstore()
        tokens = {t for t in re.split(r"\W+", query.lower()) if len(t) > 3}
        scored = []
        for d in vs.docstore._dict.values():
            meta = getattr(d, "metadata", None) or {}
            if str(meta.get("doc_domain", "")).lower() != "docs_general":
                continue
            if not any(path in _path_text(meta) for path in paths):
                continue
            content = getattr(d, "page_content", "") or ""
            score = sum(1 for token in tokens if token in content.lower())
            scored.append((score, {"content": content, **meta}))
        scored.sort(key=lambda item: item[0], reverse=True)
        matches = [doc for _, doc in scored]
    docs = matches[max(0, offset):max(0, offset) + max(1, top_k)]
    return _compact(docs, top_k, 700)


def get_role_context(summary: str, feature_prefix: str) -> str:
    """Universal role rules + object-level access rules + one matching feature section from role-permissions.md."""
    docs = search(f"role permissions {feature_prefix} {summary}", top_k=30)
    universal = access_level = feature = None
    seen: set[str] = set()
    summary_words = {w.lower() for w in re.split(r"\W+", summary) if len(w) > 3}
    prefix_words = {w.lower() for w in re.split(r"\W+", feature_prefix) if w}

    for doc in docs:
        if "role-permissions" not in str(doc.get("source", "")).lower():
            continue
        doc_id = str(doc.get("id", ""))
        if doc_id in seen:
            continue
        seen.add(doc_id)
        content = (doc.get("content") or "").strip()
        heading = str(doc.get("heading", content[:60])).lower()
        if "universal" in heading:
            universal = universal or content[:700]
        elif "object-level" in heading or "manage access" in heading or "owner access" in heading:
            access_level = access_level or content[:700]
        elif not feature:
            words = set(re.split(r"\W+", f"{heading} {content[:600]}".lower()))
            if prefix_words & words or summary_words & words:
                feature = content[:400]

    return "\n\n".join(p for p in (universal, access_level, feature) if p)


def _clean_testrail_text(content: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", content)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"(?m)^(Preconditions|Expected Result):\s*None\s*$", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _extract_jira_refs(value) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        text = " ".join(str(item) for item in value)
    else:
        text = str(value or "")
    return {match.group(0).upper() for match in _JIRA_KEY_RE.finditer(text)}


def _contains_jira_key(text: str, story_key: str) -> bool:
    key = re.escape(story_key.strip())
    return bool(key and re.search(
        rf"(?<![A-Z0-9_]){key}(?![A-Z0-9_-])",
        text or "",
        re.IGNORECASE,
    ))


@lru_cache(maxsize=1)
def _all_testrail_case_chunks() -> dict[str, list[dict]]:
    """Index local TestRail chunks once so candidate cases can be reconstructed completely."""
    grouped: dict[str, dict[int, dict]] = {}
    for d in load_vectorstore().docstore._dict.values():
        meta = getattr(d, "metadata", None) or {}
        if str(meta.get("source", "")).lower() != "testrail":
            continue
        doc_id = str(meta.get("id", ""))
        match = re.search(r"testrail_(\d+)(?:_chunk(\d+))?$", doc_id)
        if not match:
            continue
        case_id = f"C{match.group(1)}"
        chunk_number = int(match.group(2) or 0)
        grouped.setdefault(case_id, {})[chunk_number] = {
            "id": doc_id,
            "content": getattr(d, "page_content", "") or "",
            "jira_refs": _extract_jira_refs(meta.get("jira_refs")),
        }
    return {
        case_id: [chunks[n] for n in sorted(chunks)]
        for case_id, chunks in grouped.items()
    }


def get_existing_testrail_cases(
    story_key: str, summary: str, feature_key: str = "", top_k: int = 15, offset: int = 0
) -> list[dict]:
    """Return nearest indexed TestRail cases and prefer cases explicitly linked to this Jira story."""
    docs = search_filtered(
        f"{story_key} {summary}", top_k=max(1, offset) + top_k,
        source_eq="testrail", max_candidates=100,
    )
    ranked_case_ids = []
    seen_case_ids = set()
    for doc in docs:
        match = re.search(r"testrail_(\d+)", str(doc.get("id", "")))
        if not match:
            continue
        case_id = f"C{match.group(1)}"
        if case_id not in seen_case_ids:
            ranked_case_ids.append(case_id)
            seen_case_ids.add(case_id)

    all_chunks = _all_testrail_case_chunks()
    story_key_l = story_key.upper()
    semantic_rank = {case_id: rank for rank, case_id in enumerate(ranked_case_ids)}
    linked_case_ids = []
    for case_id, chunks in all_chunks.items():
        if any(
            story_key_l in chunk.get("jira_refs", set())
            or _contains_jira_key(chunk["content"], story_key)
            for chunk in chunks
        ):
            linked_case_ids.append(case_id)
    linked_case_ids.sort(
        key=lambda case_id: (semantic_rank.get(case_id, float("inf")), int(case_id[1:]))
    )
    linked_case_set = set(linked_case_ids)
    ordered_case_ids = linked_case_ids + [
        case_id for case_id in ranked_case_ids if case_id not in linked_case_set
    ]

    header_prefixes = (
        "TestRail Case:", "Suite:", "Priority:", "Title:",
        "Preconditions:", "Steps:", "Expected Result:", "Section:",
    )
    cases = []
    for case_id in ordered_case_ids:
        chunks = [_clean_testrail_text(chunk["content"]) for chunk in all_chunks.get(case_id, [])]
        if not chunks:
            continue
        seen: set[str] = set()
        lines = []
        for line in "\n\n".join(chunks).splitlines():
            key = line.strip()
            if key and key in seen and key.startswith(header_prefixes):
                continue
            seen.add(key)
            lines.append(line)
        merged = "\n".join(lines).strip()[:1500]
        title = re.search(r"Title:\s*(.+)", merged)
        title = title.group(1).strip()[:160] if title else ""
        jira_linked = any(
            story_key_l in chunk.get("jira_refs", set())
            or _contains_jira_key(chunk["content"], story_key)
            for chunk in all_chunks.get(case_id, [])
        )
        case_feature = resolve_feature_key(title, extra_text=merged)
        if feature_key and case_feature != feature_key and not jira_linked:
            continue
        cases.append({
            "id": case_id,
            "title": title,
            "content": merged,
            "jira_linked": jira_linked,
            "_semantic_rank": semantic_rank.get(case_id, float("inf")),
        })
    cases.sort(key=lambda case: (
        not case["jira_linked"],
        case["_semantic_rank"],
        int(case["id"][1:]),
    ))
    start = max(0, offset)
    page = cases[start:start + max(1, top_k)]
    for case in page:
        case.pop("_semantic_rank", None)
    return page

from __future__ import annotations


def split_description_chunks(description: str, max_chars: int) -> list[str]:
    if max_chars <= 0 or len(description) <= max_chars:
        return [description]

    chunks: list[str] = []
    start = 0
    length = len(description)
    while start < length:
        end = min(start + max_chars, length)
        if end < length:
            search_from = start + int(max_chars * 0.7)
            newline = description.rfind("\n", search_from, end)
            if newline > start:
                end = newline + 1
        chunk = description[start:end]
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks or [description]


def _article_key(article: object) -> str | None:
    if article is None:
        return None
    text = str(article).strip()
    if not text:
        return None
    return text.casefold()


def merge_parsed_items(chunks: list[list[dict]]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for items in chunks:
        for item in items:
            key = _article_key(item.get("article"))
            if key is None:
                continue
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    if merged:
        return merged
    return [{}]

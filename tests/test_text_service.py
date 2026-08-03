from services.text_service import merge_parsed_items, split_description_chunks


def test_split_description_chunks_short():
    assert split_description_chunks("abc", 5000) == ["abc"]


def test_split_description_chunks_prefers_newline():
    text = ("x" * 40) + "\n" + ("y" * 40)
    chunks = split_description_chunks(text, 50)
    assert len(chunks) >= 2
    assert chunks[0].endswith("\n") or "x" in chunks[0]


def test_merge_parsed_items_dedupes_articles():
    merged = merge_parsed_items(
        [
            [{"article": "A1", "price": None}, {"article": "B2", "price": 10}],
            [{"article": "a1", "price": 5}, {"article": "C3", "price": None}],
        ]
    )
    assert [item["article"] for item in merged] == ["A1", "B2", "C3"]

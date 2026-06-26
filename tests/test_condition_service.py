from services.condition_service import extract_condition_markers, merge_condition


def test_extract_condition_markers_demontazh():
    assert extract_condition_markers("После демонтажа линии") == ["демонтаж"]


def test_extract_condition_markers_smontirovany():
    assert extract_condition_markers("Были смонтированы на объекте") == ["были смонтированы"]
    assert extract_condition_markers("смонтированы ранее") == ["были смонтированы"]


def test_extract_condition_markers_not_in_work():
    assert extract_condition_markers("В работе не было") == ["в работе не было"]
    assert extract_condition_markers("не было в работе") == ["в работе не было"]


def test_extract_condition_markers_multiple():
    text = "После демонтажа, были смонтированы, в работе не было"
    assert extract_condition_markers(text) == [
        "демонтаж",
        "были смонтированы",
        "в работе не было",
    ]


def test_extract_condition_markers_empty():
    assert extract_condition_markers("") == []
    assert extract_condition_markers("   ") == []


def test_merge_condition_with_base_and_markers():
    assert merge_condition("бу", ["демонтаж"]) == "бу, демонтаж"


def test_merge_condition_markers_only():
    assert merge_condition(None, ["демонтаж", "в работе не было"]) == "демонтаж, в работе не было"


def test_merge_condition_base_only():
    assert merge_condition("новое", []) == "новое"


def test_merge_condition_empty():
    assert merge_condition(None, []) is None


def test_merge_condition_no_duplicates():
    assert merge_condition("бу, демонтаж", ["демонтаж"]) == "бу, демонтаж"

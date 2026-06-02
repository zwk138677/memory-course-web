from src.memory_course_web.distractors import fallback_distractors_for_blank
from src.memory_course_web.generation import DeepSeekConfig, generate_blank_distractors
from src.memory_course_web.rendering import build_word_bank, fill_interaction_html, fill_sheet_html, image_group_html, knowledge_html, word_bank_html
from src.memory_course_web.validation import validate_distractor_list, validate_finished_course_payload


def sample_payload():
    return {
        "title": "测试课程",
        "knowledge_paragraphs": [
            "alpha beta gamma",
            "delta epsilon",
        ],
        "blanks": [
            {"id": "b001", "answer": "alpha", "paragraph_index": 0, "start": 0, "end": 5, "distractors": [], "distractor_source": ""},
            {"id": "b002", "answer": "beta", "paragraph_index": 0, "start": 6, "end": 10, "distractors": [], "distractor_source": ""},
        ],
        "quick_practice": [
            {"category": "基础辨析", "stem": "alpha 对应哪个选项？", "correct": "A", "wrong": ["B", "C", "D"]}
        ],
    }


def test_validate_distractor_list_rejects_answer_duplicate():
    try:
        validate_distractor_list("A", ["B", "A", "C"], "测试")
    except Exception as exc:
        assert "互不相同" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_code_fallback_generates_three_distinct_distractors():
    payload = validate_finished_course_payload(sample_payload())
    distractors = fallback_distractors_for_blank(payload["blanks"][0], payload)

    assert len(distractors) == 3
    assert len(set(distractors + [payload["blanks"][0]["answer"]])) == 4
    assert not any(item.startswith("干扰项") for item in distractors)


def test_code_fallback_does_not_expose_placeholder_when_pool_is_sparse():
    payload = validate_finished_course_payload(
        {
            "title": "empty",
            "knowledge_paragraphs": ["A"],
            "blanks": [
                {"id": "b001", "answer": "A", "paragraph_index": 0, "start": 0, "end": 1, "distractors": [], "distractor_source": ""}
            ],
            "quick_practice": [{"category": "基础辨析", "stem": "A 是什么？", "correct": "A", "wrong": ["B", "C", "D"]}],
        }
    )

    distractors = fallback_distractors_for_blank(payload["blanks"][0], payload)

    assert len(distractors) == 3
    assert not any(item.startswith("干扰项") for item in distractors)


def test_no_api_key_uses_one_code_fallback_for_each_blank():
    payload = generate_blank_distractors(sample_payload(), DeepSeekConfig(api_key=""))

    assert {blank["distractor_source"] for blank in payload["blanks"]} == {"代码兜底"}
    assert all(len(blank["distractors"]) == 1 for blank in payload["blanks"])
    answer_keys = {blank["answer"].casefold() for blank in payload["blanks"]}
    distractor_keys = {blank["distractors"][0].casefold() for blank in payload["blanks"]}
    assert not answer_keys & distractor_keys
    assert len(distractor_keys) == len(payload["blanks"])
    assert not any(item.startswith("干扰项") for item in distractor_keys)


def test_word_bank_replaces_existing_placeholder_distractor():
    blanks = [
        {
            "id": "b001",
            "answer": "圆心角",
            "paragraph_index": 0,
            "start": 0,
            "end": 3,
            "distractors": ["干扰项23"],
            "distractor_source": "代码兜底",
        }
    ]

    word_bank = build_word_bank(blanks, "placeholder")
    distractors = [item["text"] for item in word_bank if not item["is_answer"]]

    assert len(distractors) == 1
    assert distractors[0] != "干扰项23"
    assert not distractors[0].startswith("干扰项")


def test_rendering_uses_character_positions_for_repeated_answers():
    payload = {
        "knowledge_paragraphs": ["A B A"],
        "blanks": [{"id": "b001", "answer": "A", "paragraph_index": 0, "start": 4, "end": 5}],
    }

    html = knowledge_html(payload["knowledge_paragraphs"], payload["blanks"])

    assert "A B <span" in html


def test_rendering_keeps_paragraph_images():
    html = knowledge_html(
        [""],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "diagram.svg",
                "mime_type": "image/svg+xml",
                "data_uri": "data:image/svg+xml;base64,PHN2Zy8+",
                "renderable": True,
            }
        ],
    )

    assert "course-image" in html
    assert "diagram.svg" in image_group_html(
        [{"filename": "diagram.svg", "mime_type": "image/svg+xml", "data_uri": "", "renderable": False}]
    )


def test_rendering_inserts_inline_formula_without_placeholder():
    html = knowledge_html(
        ["a=)"],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "formula.png",
                "mime_type": "image/png",
                "data_uri": "data:image/png;base64,AA==",
                "renderable": True,
                "inline": True,
                "char_index": 2,
                "kind": "formula",
            }
        ],
    )

    assert 'class="inline-formula"' in html
    assert "course-image-placeholder" not in html
    assert "a=<img" in html


def test_rendering_inserts_inline_formula_text_without_image():
    html = knowledge_html(
        ["圆周角=）"],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "",
                "mime_type": "text/plain",
                "data_uri": "",
                "renderable": True,
                "inline": True,
                "char_index": 4,
                "kind": "formula_text",
                "formula_text": "1/2圆心角",
            }
        ],
    )

    assert 'class="inline-formula-text"' in html
    assert 'class="inline-formula-frac"' in html
    assert "vertical-align:middle" in html
    assert "translateY(-0.06em)" in html
    assert "vertical-align:-0.28em" not in html
    assert 'class="frac-top"' in html
    assert ">1</span>" in html
    assert 'class="frac-bottom"' in html
    assert ">2</span>" in html
    assert "圆心角" in html
    assert 'class="inline-formula"' not in html
    assert "course-image-placeholder" not in html


def test_rendering_splits_literal_text_fraction():
    html = knowledge_html(["圆周角=1/2圆心角"], [])

    assert 'class="inline-formula-frac"' in html
    assert 'class="frac-top"' in html
    assert ">1</span>" in html
    assert 'class="frac-bottom"' in html
    assert ">2</span>" in html
    assert "圆心角" in html
    assert "1/2圆心角" not in html


def test_rendering_keeps_non_fraction_formula_text_plain():
    html = knowledge_html(
        ["angle="],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "",
                "mime_type": "text/plain",
                "data_uri": "",
                "renderable": True,
                "inline": True,
                "char_index": 6,
                "kind": "formula_text",
                "formula_text": "90°",
            }
        ],
    )

    assert 'class="inline-formula-text"' in html
    assert 'class="inline-formula-frac"' not in html
    assert "90°" in html
    assert 'class="inline-formula"' not in html


def test_rendering_does_not_split_complex_fraction_text():
    html = knowledge_html(
        ["x="],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "",
                "mime_type": "text/plain",
                "data_uri": "",
                "renderable": True,
                "inline": True,
                "char_index": 2,
                "kind": "formula_text",
                "formula_text": "a/b/c",
            }
        ],
    )

    assert 'class="inline-formula-text"' in html
    assert 'class="inline-formula-frac"' not in html
    assert "a/b/c" in html


def test_rendering_does_not_split_complex_literal_fraction_text():
    html = knowledge_html(["x=a/b/c"], [])

    assert 'class="inline-formula-frac"' not in html
    assert "a/b/c" in html


def test_word_bank_uses_one_to_one_distractor_ratio():
    blanks = [
        {"id": "b001", "answer": "alpha", "distractors": ["delta"]},
        {"id": "b002", "answer": "beta", "distractors": ["eta"]},
    ]

    word_bank = build_word_bank(blanks, "sample")

    answer_count = sum(1 for item in word_bank if item["is_answer"])
    distractor_count = len(word_bank) - answer_count
    assert answer_count == 2
    assert distractor_count == 2
    assert {item["number"] for item in word_bank} == {1, 2, 3, 4}
    assert "word-bank-item" in word_bank_html(word_bank)


def test_word_bank_counts_repeated_answers_by_blank():
    blanks = []
    for index in range(11):
        answer = "same" if index < 2 else f"answer-{index}"
        blanks.append(
            {
                "id": f"b{index + 1:03d}",
                "answer": answer,
                "distractors": [f"wrong-{index}"],
            }
        )

    word_bank = build_word_bank(blanks, "repeated")

    assert len(word_bank) == 22
    assert sum(1 for item in word_bank if item["is_answer"]) == 11
    assert sum(1 for item in word_bank if not item["is_answer"]) == 11
    assert sum(1 for item in word_bank if item["text"] == "same" and item["is_answer"]) == 2


def test_fill_sheet_hides_all_answers_at_once():
    html = fill_sheet_html(
        ["alpha and beta"],
        [
            {"id": "b001", "answer": "alpha", "paragraph_index": 0, "start": 0, "end": 5},
            {"id": "b002", "answer": "beta", "paragraph_index": 0, "start": 10, "end": 14},
        ],
    )

    assert "<p>alpha" not in html
    assert "and beta" not in html
    assert html.count("word-blank") >= 2


def test_fill_interaction_html_contains_drag_click_and_check_controls():
    blanks = [{"id": "b001", "answer": "alpha", "paragraph_index": 0, "start": 0, "end": 5, "distractors": ["delta"]}]
    word_bank = build_word_bank(blanks, "interactive")

    html = fill_interaction_html(["alpha"], blanks, [], word_bank)

    assert 'draggable="true"' in html
    assert 'data-blank-id="b001"' in html
    assert 'addEventListener("drop"' in html
    assert "提交检查" in html
    assert "重做" in html
    assert "共 " not in html
    assert "word-bank-title" in html
    assert "fill-sheet" in html

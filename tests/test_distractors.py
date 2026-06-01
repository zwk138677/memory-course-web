from src.memory_course_web.distractors import fallback_distractors_for_blank
from src.memory_course_web.generation import DeepSeekConfig, generate_blank_distractors
from src.memory_course_web.rendering import image_group_html, knowledge_html
from src.memory_course_web.validation import validate_distractor_list, validate_finished_course_payload


def sample_payload():
    return {
        "title": "测试课程",
        "knowledge_paragraphs": [
            "全等三角形的对应边相等，对应角相等。",
            "全等三角形的周长相等、面积相等。",
        ],
        "blanks": [
            {"id": "b001", "answer": "对应边相等", "paragraph_index": 0, "start": 6, "end": 11, "distractors": [], "distractor_source": ""},
            {"id": "b002", "answer": "周长相等", "paragraph_index": 1, "start": 6, "end": 10, "distractors": [], "distractor_source": ""},
        ],
        "quick_practice": [
            {"category": "基础辨析", "stem": "全等三角形的对应边有什么关系？", "correct": "相等", "wrong": ["平行", "互补", "垂直"]}
        ],
    }


def test_validate_distractor_list_rejects_answer_duplicate():
    try:
        validate_distractor_list("相等", ["平行", "相等", "垂直"], "测试")
    except Exception as exc:
        assert "互不相同" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_code_fallback_generates_three_distinct_distractors():
    payload = validate_finished_course_payload(sample_payload())
    distractors = fallback_distractors_for_blank(payload["blanks"][0], payload)

    assert len(distractors) == 3
    assert len(set(distractors + [payload["blanks"][0]["answer"]])) == 4


def test_no_api_key_uses_code_fallback_for_all_blanks():
    payload = generate_blank_distractors(sample_payload(), DeepSeekConfig(api_key=""))

    assert {blank["distractor_source"] for blank in payload["blanks"]} == {"代码兜底"}
    assert all(len(blank["distractors"]) == 3 for blank in payload["blanks"])


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

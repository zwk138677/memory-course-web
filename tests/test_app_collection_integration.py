from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.memory_course_web.rendering import course_id


APP_PATH = Path(__file__).parents[1] / "app.py"
PARSER_SCHEMA_VERSION = "2026-08-13-multi-course-v1"


def _course(title: str) -> dict:
    return {
        "title": title,
        "knowledge_paragraphs": ["知识小题1.核心概念", "需要记住这一结论。"],
        "knowledge_text": "知识小题1.核心概念\n需要记住这一结论。",
        "knowledge_images": [],
        "blanks": [],
        "distractor_groups": [],
        "quick_practice": [],
        "source_name": "光现象合集.docx",
        "structure": "physics_reference_course",
        "_parser_schema_version": PARSER_SCHEMA_VERSION,
    }


def _button(app_test: AppTest, label: str):
    return next(button for button in app_test.button if button.label == label)


def test_collection_catalog_opens_course_and_returns_without_losing_stage():
    first = _course("一、光的直线传播")
    second = _course("二、光的反射")
    collection = {
        "source_name": "光现象合集.docx",
        "courses": [first, second],
        "_parser_schema_version": PARSER_SCHEMA_VERSION,
    }
    app_test = AppTest.from_file(APP_PATH)
    app_test.session_state["parsed_payload"] = collection
    app_test.session_state["uploaded_signature"] = "uploaded"

    app_test.run(timeout=5)

    assert not app_test.exception
    button_labels = [button.label for button in app_test.button]
    assert "开始学习" not in button_labels
    assert "继续学习" not in button_labels
    assert "一、光的直线传播" in button_labels
    assert "二、光的反射" in button_labels

    _button(app_test, "一、光的直线传播").click().run(timeout=5)
    first_cid = course_id(first)
    app_test.session_state[f"course_stage_{first_cid}"] = "fill"

    _button(app_test, "返回课程目录").click().run(timeout=5)

    assert not app_test.exception
    button_labels = [button.label for button in app_test.button]
    assert "开始学习" not in button_labels
    assert "继续学习" not in button_labels
    assert app_test.session_state[f"course_stage_{first_cid}"] == "fill"

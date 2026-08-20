from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.memory_course_web.rendering import course_id


APP_PATH = Path(__file__).parents[1] / "app.py"
PARSER_SCHEMA_VERSION = "2026-08-20-omml-v1"


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


def test_catalog_omits_knowledge_paragraph_count():
    collection = {
        "source_name": "光现象合集.docx",
        "courses": [_course("一、光的直线传播"), _course("二、光的反射")],
        "_parser_schema_version": PARSER_SCHEMA_VERSION,
    }
    app_test = AppTest.from_file(APP_PATH)
    app_test.session_state["parsed_payload"] = collection
    app_test.session_state["uploaded_signature"] = "uploaded"

    app_test.run(timeout=5)

    markdown = "\n".join(element.value for element in app_test.markdown)
    assert "知识段落" not in markdown
    assert "填空 0 · 练习 0" in markdown


def test_completed_practice_can_enter_overview_with_only_review_sections():
    course = _course("一、光的直线传播")
    course["quick_practice"] = [
        {
            "stem": f"题目{index}",
            "correct": f"正确{index}",
            "wrong": [f"错误{index}-1", f"错误{index}-2", f"错误{index}-3"],
            "category": "",
            "analysis": f"解析{index}",
            "images": [],
        }
        for index in range(1, 7)
    ]
    collection = {
        "source_name": "光现象合集.docx",
        "courses": [course],
        "_parser_schema_version": PARSER_SCHEMA_VERSION,
    }
    cid = course_id(course)
    result_items = [
        {
            "display_index": display_index,
            "original_index": original_index,
            "stem": f"题目{original_index + 1}",
            "selected": f"正确{original_index + 1}",
            "correct": f"正确{original_index + 1}",
            "is_correct": True,
            "options": [f"正确{original_index + 1}", f"错误{original_index + 1}-1"],
        }
        for display_index, original_index in enumerate([0, 1, 2, 3, 4], start=1)
    ]
    app_test = AppTest.from_file(APP_PATH)
    app_test.session_state["parsed_payload"] = collection
    app_test.session_state["course_payload"] = course
    app_test.session_state[f"course_stage_{cid}"] = "practice"
    app_test.session_state[f"practice_result_{cid}"] = {"score": 5, "items": result_items}

    app_test.run(timeout=5)

    button_labels = [button.label for button in app_test.button]
    assert "重新练习" in button_labels
    assert "进入总览" in button_labels

    _button(app_test, "进入总览").click().run(timeout=5)

    assert not app_test.exception
    assert app_test.session_state[f"course_stage_{cid}"] == "overview"
    markdown = "\n".join(element.value for element in app_test.markdown)
    assert "知识展示" in markdown
    assert "快速练习回顾" in markdown
    assert "选词填空" not in markdown
    assert "进入知识填空" not in [button.label for button in app_test.button]
    assert "返回练习结果" in [button.label for button in app_test.button]

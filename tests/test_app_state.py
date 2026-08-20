import app
from src.memory_course_web.rendering import course_id


def test_parser_schema_helpers_tag_and_reject_old_payload():
    payload = {"title": "分子动理论", "knowledge_paragraphs": [], "quick_practice": []}

    tagged = app._tag_parser_schema(payload)

    assert app._has_current_parser_schema(tagged)
    assert not app._has_current_parser_schema(payload)
    assert not app._has_current_parser_schema(None)
    assert not app._has_current_parser_schema({**tagged, "_parser_schema_version": "2026-08-13-multi-course-v1"})
    assert not app._has_current_parser_schema({**tagged, "_parser_schema_version": "2026-08-20-superscript-v1"})


def test_current_physics_payload_does_not_reparse_for_optional_question_metadata():
    current_physics_payload = {
        "_parser_schema_version": app.PARSER_SCHEMA_VERSION,
        "title": "分子动理论",
        "structure": "physics_reference_course",
        "knowledge_paragraphs": ["知识小题1.物质构成"],
        "quick_practice": [
            {
                "category": "基础辨析",
                "stem": "题目",
                "correct": "A",
                "wrong": ["B", "C", "D"],
                "source": "知识小题1",
                "analysis": "",
            }
        ],
    }

    assert not app._payload_needs_reparse(current_physics_payload)
    assert app._payload_needs_reparse(
        {**current_physics_payload, "_parser_schema_version": "2026-08-20-superscript-v1"}
    )


def test_reset_course_state_can_clear_upload_signature(monkeypatch):
    payload = {
        "title": "分子动理论",
        "knowledge_paragraphs": ["知识小题1.物质构成"],
        "quick_practice": [],
    }
    cid = course_id(payload)
    fake_state = {
        "course_payload": payload,
        "parsed_payload": payload,
        app._practice_result_key(cid): {"score": 0},
        app._practice_sample_key(cid): {"indexes": [0], "round": 1},
        app._practice_round_key(cid): 1,
        "uploaded_signature": "old",
        app.UPLOAD_NONCE_KEY: 2,
    }
    monkeypatch.setattr(app.st, "session_state", fake_state)

    app._reset_course_state(clear_upload_signature=True, reset_uploader=True)

    assert "course_payload" not in fake_state
    assert "parsed_payload" not in fake_state
    assert app._practice_result_key(cid) not in fake_state
    assert app._practice_sample_key(cid) not in fake_state
    assert app._practice_round_key(cid) not in fake_state
    assert "uploaded_signature" not in fake_state
    assert fake_state[app.UPLOAD_NONCE_KEY] == 3
    assert app._upload_widget_key() == "course_upload_3"


def test_activate_course_payload_enters_show_stage(monkeypatch):
    payload = {
        "title": "二力平衡",
        "knowledge_paragraphs": ["知识小题1.定义", "物体保持静止"],
        "blanks": [{"id": "b001", "answer": "静止", "paragraph_index": 1, "start": 4, "end": 6}],
        "distractor_groups": [
            {"id": "dg001", "paragraph_indexes": [0, 1], "distractors": ["运动"], "source": "资料自带"}
        ],
        "quick_practice": [],
    }
    cid = course_id(payload)
    fake_state = {
        app._practice_result_key(cid): {"score": 0},
        app._course_stage_key(cid): app.COURSE_STAGE_FILL,
    }
    monkeypatch.setattr(app.st, "session_state", fake_state)

    activated_cid = app._activate_course_payload(payload)

    assert activated_cid == cid
    assert fake_state["course_payload"] is payload
    assert app._practice_result_key(cid) not in fake_state
    assert fake_state[app._course_stage_key(cid)] == app.COURSE_STAGE_SHOW


def test_activate_collection_course_preserves_existing_progress(monkeypatch):
    payload = {
        "title": "光的反射",
        "knowledge_paragraphs": ["知识小题1.反射定律"],
        "blanks": [],
        "quick_practice": [],
    }
    cid = course_id(payload)
    result = {"score": 4}
    fake_state = {
        app._course_stage_key(cid): app.COURSE_STAGE_PRACTICE,
        app._practice_result_key(cid): result,
    }
    monkeypatch.setattr(app.st, "session_state", fake_state)

    app._activate_course_payload(payload, reset_progress=False)

    assert fake_state["course_payload"] is payload
    assert fake_state[app._course_stage_key(cid)] == app.COURSE_STAGE_PRACTICE
    assert fake_state[app._practice_result_key(cid)] is result


def test_return_to_course_catalog_keeps_collection_and_course_progress(monkeypatch):
    payload = {
        "title": "光的折射",
        "knowledge_paragraphs": ["知识小题1.折射规律"],
        "blanks": [],
        "quick_practice": [],
    }
    cid = course_id(payload)
    collection = {"courses": [payload], "_parser_schema_version": app.PARSER_SCHEMA_VERSION}
    fake_state = {
        "course_payload": payload,
        "parsed_payload": collection,
        app._course_stage_key(cid): app.COURSE_STAGE_FILL,
    }
    monkeypatch.setattr(app.st, "session_state", fake_state)

    app._return_to_course_catalog()

    assert "course_payload" not in fake_state
    assert fake_state["parsed_payload"] is collection
    assert fake_state[app._course_stage_key(cid)] == app.COURSE_STAGE_FILL


def test_reset_upload_clears_progress_for_every_collection_course(monkeypatch):
    first = {"title": "光的反射", "knowledge_paragraphs": [], "quick_practice": []}
    second = {"title": "光的折射", "knowledge_paragraphs": [], "quick_practice": []}
    first_cid = course_id(first)
    second_cid = course_id(second)
    fake_state = {
        "course_payload": first,
        "parsed_payload": {
            "courses": [first, second],
            "_parser_schema_version": app.PARSER_SCHEMA_VERSION,
        },
        app._course_stage_key(first_cid): app.COURSE_STAGE_SHOW,
        app._course_stage_key(second_cid): app.COURSE_STAGE_PRACTICE,
        app._practice_result_key(second_cid): {"score": 5},
        "uploaded_signature": "old",
    }
    monkeypatch.setattr(app.st, "session_state", fake_state)

    app._reset_course_state(clear_upload_signature=True)

    assert "parsed_payload" not in fake_state
    assert "uploaded_signature" not in fake_state
    assert app._course_stage_key(first_cid) not in fake_state
    assert app._course_stage_key(second_cid) not in fake_state
    assert app._practice_result_key(second_cid) not in fake_state


def test_practice_sample_is_stable_until_reset(monkeypatch):
    fake_state = {}
    calls = []
    samples = [[4, 3, 2, 1, 0], [9, 8, 7, 6, 5]]

    def fake_sample(population, count):
        calls.append((list(population), count))
        return samples[len(calls) - 1]

    monkeypatch.setattr(app.st, "session_state", fake_state)
    monkeypatch.setattr(app.random, "sample", fake_sample)

    first = app._current_practice_sample("course", 10)
    second = app._current_practice_sample("course", 10)

    assert first == second
    assert first["indexes"] == [4, 3, 2, 1, 0]
    assert first["round"] == 1
    assert len(calls) == 1

    app._reset_practice_sample("course")
    third = app._current_practice_sample("course", 10)

    assert third["indexes"] == [9, 8, 7, 6, 5]
    assert third["round"] == 2
    assert len(calls) == 2


def test_practice_sample_uses_all_questions_when_fewer_than_five(monkeypatch):
    fake_state = {}
    monkeypatch.setattr(app.st, "session_state", fake_state)
    monkeypatch.setattr(app.random, "sample", lambda population, count: list(reversed(population)))

    sample = app._current_practice_sample("short-course", 3)

    assert sample["indexes"] == [2, 1, 0]
    assert sample["round"] == 1


def test_practice_accuracy_percent():
    assert app._practice_accuracy_percent(4, 5) == 80
    assert app._practice_accuracy_percent(2, 3) == 67
    assert app._practice_accuracy_percent(0, 0) == 0


def test_ready_generation_card_css_is_removed():
    assert "course-ready-card" not in app.APP_CSS
    assert "_logo_watermark_css" not in dir(app)


def test_course_sections_use_standard_streamlit_containers():
    import inspect

    source = inspect.getsource(app._render_course)

    assert '<section class="learning-card">' not in source
    assert source.count("with st.container(border=True):") >= 3


def test_course_stage_defaults_and_validates(monkeypatch):
    fake_state = {}
    monkeypatch.setattr(app.st, "session_state", fake_state)

    assert app._current_course_stage("course") == app.COURSE_STAGE_SHOW

    app._set_course_stage("course", app.COURSE_STAGE_FILL)
    assert app._current_course_stage("course") == app.COURSE_STAGE_FILL

    app._set_course_stage("course", app.COURSE_STAGE_OVERVIEW)
    assert app._current_course_stage("course") == app.COURSE_STAGE_OVERVIEW

    fake_state[app._course_stage_key("course")] = "unknown"
    assert app._current_course_stage("course") == app.COURSE_STAGE_SHOW


def test_practice_review_items_only_use_just_completed_questions():
    payload = {
        "quick_practice": [
            {
                "stem": f"题目{index}",
                "correct": f"正确{index}",
                "wrong": [f"错误{index}-1", f"错误{index}-2", f"错误{index}-3"],
                "analysis": f"解析{index}",
                "images": [{"id": f"image-{index}"}],
            }
            for index in range(1, 7)
        ]
    }
    result = {
        "score": 4,
        "items": [
            {
                "display_index": display_index,
                "original_index": original_index,
                "stem": f"题目{original_index + 1}",
                "selected": f"正确{original_index + 1}",
                "correct": f"正确{original_index + 1}",
                "is_correct": True,
                "options": [f"错误{original_index + 1}-1", f"正确{original_index + 1}"],
            }
            for display_index, original_index in enumerate([5, 0, 3, 1, 4], start=1)
        ],
        "source_indexes": [5, 0, 3, 1, 4],
    }

    items = app._practice_review_items(payload, result)

    assert len(items) == 5
    assert [item["original_index"] for item in items] == [5, 0, 3, 1, 4]
    assert [item["stem"] for item in items] == ["题目6", "题目1", "题目4", "题目2", "题目5"]
    assert items[0]["analysis"] == "解析6"
    assert items[0]["images"] == [{"id": "image-6"}]
    assert items[0]["options"] == ["错误6-1", "正确6"]


def test_fill_component_practice_event_is_consumed_once(monkeypatch):
    fake_state = {}
    monkeypatch.setattr(app.st, "session_state", fake_state)

    result = {"action": "practice_ready", "nonce": "event-1"}

    assert app._handle_fill_component_result("course", result)
    assert fake_state[app._course_stage_key("course")] == app.COURSE_STAGE_PRACTICE

    fake_state[app._course_stage_key("course")] = app.COURSE_STAGE_FILL
    assert not app._handle_fill_component_result("course", result)
    assert fake_state[app._course_stage_key("course")] == app.COURSE_STAGE_FILL


def test_practice_component_submit_event_is_consumed_once(monkeypatch):
    fake_state = {}
    monkeypatch.setattr(app.st, "session_state", fake_state)

    result = {
        "action": "practice_submitted",
        "nonce": "practice-1",
        "score": 1,
        "items": [{"display_index": 1, "stem": r"$x$", "selected": r"$x$", "correct": r"$x$", "is_correct": True}],
        "source_indexes": [0],
    }

    assert app._handle_practice_component_result("course", result)
    assert fake_state[app._practice_result_key("course")]["score"] == 1

    fake_state[app._practice_result_key("course")]["score"] = 0
    assert not app._handle_practice_component_result("course", result)
    assert fake_state[app._practice_result_key("course")]["score"] == 0


def test_step_indicator_is_not_clickable():
    html = app._step_indicator_html(app.COURSE_STAGE_FILL)

    assert "flow-step active" in html
    assert "<button" not in html
    assert "<a " not in html


def test_four_step_indicator_can_shrink_on_mobile():
    assert "flex: 1 1 0;" in app.APP_CSS
    assert "min-width: 0;" in app.APP_CSS


def test_completed_practice_actions_stay_side_by_side_on_mobile():
    assert '[class*="st-key-practice_restart_"]' in app.APP_CSS
    assert "flex-direction: row !important;" in app.APP_CSS

import app
from src.memory_course_web.rendering import course_id


def test_parser_schema_helpers_tag_and_reject_old_payload():
    payload = {"title": "分子动理论", "knowledge_paragraphs": [], "quick_practice": []}

    tagged = app._tag_parser_schema(payload)

    assert app._has_current_parser_schema(tagged)
    assert not app._has_current_parser_schema(payload)
    assert not app._has_current_parser_schema(None)


def test_physics_payload_with_math_categories_or_missing_analysis_needs_reparse():
    old_physics_payload = {
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

    assert app._payload_needs_reparse(old_physics_payload)

    refreshed = {
        **old_physics_payload,
        "quick_practice": [
            {
                **old_physics_payload["quick_practice"][0],
                "category": "",
                "analysis": "物质由分子、原子等微粒构成。",
            }
        ],
    }
    assert not app._payload_needs_reparse(refreshed)


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

    fake_state[app._course_stage_key("course")] = "unknown"
    assert app._current_course_stage("course") == app.COURSE_STAGE_SHOW


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

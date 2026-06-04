from __future__ import annotations

import hashlib
import html
import os
from pathlib import Path
import random
import tempfile
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from src.memory_course_web.finished_course_parser import parse_finished_course
from src.memory_course_web.generation import DeepSeekConfig, generate_blank_distractors
from src.memory_course_web.rendering import build_word_bank, course_id, fill_interaction_html, image_group_html, knowledge_html, stable_options
from src.memory_course_web.validation import validate_finished_course_payload


st.set_page_config(page_title="成品背记资料学习页", layout="wide")

PARSER_SCHEMA_VERSION = "2026-06-03-physics-ui-v4"
UPLOAD_NONCE_KEY = "course_upload_nonce"
MATH_CATEGORY_LABELS = {"基础辨析", "易错辨析", "简单应用"}
PRACTICE_SAMPLE_SIZE = 5
COURSE_STAGE_SHOW = "show"
COURSE_STAGE_FILL = "fill"
COURSE_STAGE_PRACTICE = "practice"

FILL_INTERACTION_COMPONENT = components.declare_component(
    "fill_interaction_component",
    path=str((Path(__file__).parent / "src" / "memory_course_web" / "fill_component").resolve()),
)


APP_CSS = """
<style>
.stApp {
  background:
    linear-gradient(180deg, #fff6df 0%, #fffdf8 44%, #fff7e6 100%),
    repeating-linear-gradient(0deg, rgba(122, 82, 24, .032) 0, rgba(122, 82, 24, .032) 1px, transparent 1px, transparent 30px);
  color: #2f261a;
}
.main .block-container {
  max-width: 1040px;
  padding-top: 1.35rem;
  padding-bottom: 3.5rem;
}
h1, h2, h3 {
  letter-spacing: 0;
  color: #2f261a;
}
.app-shell-title {
  margin: 0 0 .35rem;
  font-size: 1.72rem;
  font-weight: 800;
  color: #3a2a13;
}
.app-shell-caption {
  color: #806a49;
  font-size: .96rem;
  margin-bottom: 1.15rem;
}
.course-ready-card,
.learning-card {
  border: 1px solid #ead7ad;
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(255, 253, 247, .98), rgba(255, 250, 239, .98));
  box-shadow: 0 14px 32px rgba(111, 78, 32, .08), inset 0 1px 0 rgba(255, 255, 255, .9);
}
.course-ready-card {
  padding: 1.08rem 1.18rem;
  margin: .85rem 0 1rem;
}
.course-ready-card h2 {
  margin: .15rem 0 .2rem;
  font-size: 1.35rem;
  line-height: 1.45;
}
.course-ready-card p {
  margin: 0;
  color: #7b674c;
}
.course-ready-card,
.practice-result-card,
div[data-testid="stVerticalBlockBorderWrapper"]:has(.section-kicker) {
  position: relative;
  overflow: hidden;
  isolation: isolate;
}
.course-ready-card > *,
.practice-result-card > *,
div[data-testid="stVerticalBlockBorderWrapper"]:has(.section-kicker) > div {
  position: relative;
  z-index: 1;
}
.course-ready-card::after,
.practice-result-card::after,
div[data-testid="stVerticalBlockBorderWrapper"]:has(.section-kicker)::after {
  content: "";
  position: absolute;
  right: 1.35rem;
  bottom: .75rem;
  width: 220px;
  height: 72px;
  background: url("/app/static/shiguang-logo.png") center / contain no-repeat;
  opacity: .075;
  filter: blur(1.2px);
  pointer-events: none;
  z-index: 0;
}
.course-title-card {
  padding: 1.05rem 1.25rem;
  margin: .65rem 0 1rem;
  border: 1px solid #ead7ad;
  border-left: 6px solid #d5961e;
  border-radius: 8px;
  background:
    linear-gradient(180deg, #fffdf8, #fff8e8);
  box-shadow: 0 14px 32px rgba(111, 78, 32, .09), inset 0 1px 0 rgba(255, 255, 255, .9);
}
.course-title-card h1 {
  margin: 0;
  font-size: 1.55rem;
  line-height: 1.45;
  font-weight: 800;
}
.learning-card {
  padding: 1.05rem 1.15rem 1.15rem;
  margin-top: .9rem;
}
.section-kicker {
  display: inline-flex;
  align-items: center;
  gap: .4rem;
  margin-bottom: .9rem;
  color: #87520a;
  font-size: .9rem;
  font-weight: 800;
}
.section-kicker::before {
  content: "";
  width: .45rem;
  height: .45rem;
  border-radius: 999px;
  background: #d89a22;
}
.stTabs [data-baseweb="tab-list"] {
  gap: .28rem;
  border-bottom: 1px solid #e7d1a1;
}
.stTabs [data-baseweb="tab"] {
  height: 2.55rem;
  padding: .18rem .9rem;
  border-radius: 8px 8px 0 0;
  color: #7b6544;
  font-weight: 700;
}
.stTabs [aria-selected="true"] {
  background: #fffaf0;
  color: #805005;
  border: 1px solid #ead7ad;
  border-bottom-color: #fffaf0;
}
.stButton > button,
.stDownloadButton > button,
button[kind="primary"] {
  border-radius: 7px;
  font-weight: 700;
  border-color: #dfc286;
}
.stButton > button[kind="primary"] {
  background: #b86f00;
  border-color: #b86f00;
}
.stButton > button[kind="primary"]:hover {
  background: #965900;
  border-color: #965900;
}
.stFileUploader section {
  border-radius: 8px;
  border-color: #e6c98f;
  background: #fffaf0;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .75);
}
.knowledge-body p {
  font-family: "Microsoft YaHei", "SimSun", sans-serif;
  font-size: 1rem;
  line-height: 2.08;
  margin: 0 0 .82rem;
  color: #2f261a;
}
.answer-mark {
  border-bottom: 1.5px solid #bd7615;
  background: #fff0bf;
  color: #4a3514;
  padding: 0 .18rem .02rem;
  border-radius: 3px 3px 0 0;
}
.course-images {
  display: flex;
  flex-wrap: wrap;
  gap: .9rem;
  margin: .6rem 0 1.1rem;
}
.course-image-wrap { margin: 0; }
.course-image {
  display: block;
  max-height: 420px;
  object-fit: contain;
  border: 1px solid #e4c78b;
  border-radius: 8px;
  background: #fffdf8;
  padding: .5rem;
  box-shadow: 0 9px 20px rgba(111, 78, 32, .075);
}
.course-image-placeholder {
  border: 1px dashed #c7a566;
  border-radius: 8px;
  background: #fffaf0;
  color: #735f43;
  padding: .75rem .9rem;
  font-size: .92rem;
}
.course-image-placeholder span {
  color: #8a7657;
  font-size: .84rem;
}
.inline-formula {
  display: inline-block;
  height: 1.45em;
  max-width: 10em;
  margin: 0 .08rem;
  vertical-align: -0.35em;
  object-fit: contain;
}
.inline-formula-text {
  display: inline;
  margin: 0 .08rem;
  font-family: "Times New Roman", "Cambria Math", serif;
  font-size: 1em;
  color: #3f2a0b;
  white-space: nowrap;
}
.inline-formula-frac {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  margin: 0 .08em;
  vertical-align: middle;
  transform: translateY(-0.06em);
  line-height: .95;
  font-size: .82em;
}
.inline-formula-frac .frac-top {
  display: block;
  border-bottom: 1px solid currentColor;
  padding: 0 .16em .035em;
}
.inline-formula-frac .frac-bottom {
  display: block;
  padding: .035em .16em 0;
}
.flow-steps {
  display: flex;
  gap: 0;
  margin: .4rem 0 1rem;
  border-bottom: 1px solid #e6c98f;
}
.flow-step {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 6.2rem;
  padding: .62rem .85rem .58rem;
  border: 1px solid #ead7ad;
  border-bottom: 0;
  background: #fff8e7;
  color: #6f5a36;
  font-weight: 700;
  user-select: none;
}
.flow-step.active {
  background: #fffdf8;
  color: #8a4e00;
  box-shadow: inset 0 -3px 0 #d5961e;
}
.course-flow-actions {
  display: flex;
  gap: .7rem;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 1rem;
}
.practice-group-title {
  display: flex;
  align-items: center;
  margin: 1.05rem 0 .68rem;
  color: #835108;
  font-size: 1.05rem;
  font-weight: 800;
}
.practice-group-title::before {
  content: "";
  width: 4px;
  height: 1.05rem;
  margin-right: .5rem;
  border-radius: 999px;
  background: #d89a22;
}
.question-stem {
  display: flex;
  gap: .65rem;
  align-items: flex-start;
  margin-bottom: .55rem;
  font-size: 1rem;
  line-height: 1.75;
  color: #2f261a;
  font-weight: 700;
}
.question-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.8rem;
  height: 1.8rem;
  margin-top: .05rem;
  border-radius: 999px;
  background: #fff0bf;
  color: #835108;
  font-size: .9rem;
  font-weight: 800;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: #e6c98f;
  border-radius: 8px;
  background: rgba(255, 253, 248, .98);
  box-shadow: 0 8px 18px rgba(111, 78, 32, .055), inset 0 1px 0 rgba(255, 255, 255, .88);
}
div[role="radiogroup"] {
  gap: .48rem;
}
div[role="radiogroup"] label {
  margin-bottom: .42rem;
  padding: .5rem .62rem;
  border: 1px solid #ead7ad;
  border-radius: 8px;
  background: #fffaf0;
  transition: border-color .15s ease, background .15s ease, box-shadow .15s ease;
}
div[role="radiogroup"] label:hover {
  border-color: #d49a2a;
  background: #fff4d8;
  box-shadow: 0 4px 12px rgba(111, 78, 32, .06);
}
.practice-result-card {
  padding: 1rem 1.12rem;
  border: 1px solid #e4c78b;
  border-radius: 8px;
  background: #fffdf8;
  box-shadow: 0 10px 22px rgba(111, 78, 32, .075);
}
.practice-result-card strong {
  color: #835108;
}
.practice-result-rate {
  display: inline-flex;
  margin-left: 1.15rem;
  padding-left: 1.15rem;
  border-left: 1px solid #e6c98f;
  color: #835108;
  font-weight: 800;
}
.wrong-item {
  padding: .75rem .85rem;
  margin: .7rem 0 0;
  border-left: 4px solid #bd4a43;
  border-radius: 7px;
  background: #fff5f3;
}
.practice-review-item {
  padding: .85rem .95rem;
  margin: .75rem 0 0;
  border: 1px solid #ead7ad;
  border-left-width: 5px;
  border-radius: 8px;
  line-height: 1.75;
  color: #2f261a;
}
.practice-review-item.is-correct {
  border-left-color: #4f9a58;
  background: #f1fbf0;
}
.practice-review-item.is-wrong {
  border-left-color: #bd4a43;
  background: #fff5f3;
}
.practice-review-status {
  display: inline-flex;
  align-items: center;
  margin: 0 0 .35rem;
  padding: .12rem .48rem;
  border-radius: 999px;
  font-size: .84rem;
  font-weight: 800;
}
.practice-review-item.is-correct .practice-review-status {
  background: #dff2df;
  color: #27652f;
}
.practice-review-item.is-wrong .practice-review-status {
  background: #ffe2dd;
  color: #8f2c26;
}
.practice-review-analysis {
  margin-top: .28rem;
  color: #5e4c31;
}
@media (max-width: 720px) {
  .main .block-container {
    padding-left: .9rem;
    padding-right: .9rem;
  }
  .course-title-card h1 {
    font-size: 1.28rem;
  }
  .learning-card {
    padding: .85rem;
  }
  .course-ready-card::after,
  .practice-result-card::after,
  div[data-testid="stVerticalBlockBorderWrapper"]:has(.section-kicker)::after {
    display: none;
  }
}
</style>
"""


def _secret_or_env(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, default)).strip()


def _deepseek_config() -> DeepSeekConfig:
    return DeepSeekConfig(
        api_key=_secret_or_env("DEEPSEEK_API_KEY"),
        base_url=_secret_or_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=_secret_or_env("DEEPSEEK_MODEL", "deepseek-v4-pro"),
    )


def _all_course_images(payload: dict[str, Any]) -> list[dict[str, Any]]:
    images = list(payload.get("knowledge_images", []))
    for question in payload.get("quick_practice", []):
        images.extend(question.get("images", []))
    return images


def _tag_parser_schema(payload: dict[str, Any]) -> dict[str, Any]:
    tagged = dict(payload)
    tagged["_parser_schema_version"] = PARSER_SCHEMA_VERSION
    return tagged


def _has_current_parser_schema(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("_parser_schema_version") == PARSER_SCHEMA_VERSION


def _is_physics_payload(payload: dict[str, Any]) -> bool:
    structure = str(payload.get("structure", ""))
    if structure.startswith("physics"):
        return True
    if any(str(text).strip().startswith("知识小题") for text in payload.get("knowledge_paragraphs", [])):
        return True
    return any(
        str(question.get("source", "")).startswith("知识小题") or str(question.get("analysis", "")).strip()
        for question in payload.get("quick_practice", [])
        if isinstance(question, dict)
    )


def _payload_needs_reparse(payload: Any) -> bool:
    if not _has_current_parser_schema(payload):
        return True
    if not isinstance(payload, dict) or not _is_physics_payload(payload):
        return False
    questions = [question for question in payload.get("quick_practice", []) if isinstance(question, dict)]
    if any(str(question.get("category", "")).strip() in MATH_CATEGORY_LABELS for question in questions):
        return True
    return bool(questions) and any(not str(question.get("analysis", "")).strip() for question in questions)


def _upload_widget_key() -> str:
    return f"course_upload_{int(st.session_state.get(UPLOAD_NONCE_KEY, 0))}"


def _practice_result_key(cid: str) -> str:
    return f"practice_result_{cid}"


def _practice_sample_key(cid: str) -> str:
    return f"practice_sample_{cid}"


def _practice_round_key(cid: str) -> str:
    return f"practice_round_{cid}"


def _course_stage_key(cid: str) -> str:
    return f"course_stage_{cid}"


def _fill_progress_key(cid: str) -> str:
    return f"fill_progress_{cid}"


def _fill_component_action_key(cid: str) -> str:
    return f"fill_component_action_{cid}"


def _set_course_stage(cid: str, stage: str) -> None:
    st.session_state[_course_stage_key(cid)] = stage


def _current_course_stage(cid: str) -> str:
    stage = str(st.session_state.get(_course_stage_key(cid), COURSE_STAGE_SHOW))
    if stage not in {COURSE_STAGE_SHOW, COURSE_STAGE_FILL, COURSE_STAGE_PRACTICE}:
        return COURSE_STAGE_SHOW
    return stage


def _clear_fill_progress(cid: str) -> None:
    st.session_state.pop(_fill_progress_key(cid), None)
    st.session_state.pop(_fill_component_action_key(cid), None)


def _handle_fill_component_result(cid: str, result: Any) -> bool:
    if not isinstance(result, dict) or result.get("action") != "practice_ready":
        return False
    nonce = str(result.get("nonce") or "")
    consumed_key = _fill_component_action_key(cid)
    consumed_nonce = str(st.session_state.get(consumed_key, ""))
    if nonce and consumed_nonce == nonce:
        return False
    st.session_state[consumed_key] = nonce or "practice_ready"
    _set_course_stage(cid, COURSE_STAGE_PRACTICE)
    return True


def _clear_practice_state(cid: str, *, clear_sample: bool = True) -> None:
    st.session_state.pop(_practice_result_key(cid), None)
    if clear_sample:
        st.session_state.pop(_practice_sample_key(cid), None)
        st.session_state.pop(_practice_round_key(cid), None)


def _create_practice_sample(cid: str, question_count: int) -> dict[str, Any]:
    sample_size = min(PRACTICE_SAMPLE_SIZE, max(0, question_count))
    indexes = random.sample(list(range(question_count)), sample_size) if sample_size else []
    round_id = int(st.session_state.get(_practice_round_key(cid), 0)) + 1
    sample = {"indexes": indexes, "round": round_id}
    st.session_state[_practice_sample_key(cid)] = sample
    st.session_state[_practice_round_key(cid)] = round_id
    return sample


def _current_practice_sample(cid: str, question_count: int) -> dict[str, Any]:
    sample = st.session_state.get(_practice_sample_key(cid))
    if isinstance(sample, dict):
        indexes = sample.get("indexes", [])
        if (
            isinstance(indexes, list)
            and len(indexes) == min(PRACTICE_SAMPLE_SIZE, max(0, question_count))
            and all(isinstance(index, int) and 0 <= index < question_count for index in indexes)
        ):
            return {"indexes": indexes, "round": int(sample.get("round", st.session_state.get(_practice_round_key(cid), 0)))}
    return _create_practice_sample(cid, question_count)


def _reset_practice_sample(cid: str) -> None:
    st.session_state.pop(_practice_sample_key(cid), None)


def _practice_accuracy_percent(score: int, total: int) -> int:
    return round(score / total * 100) if total else 0


@st.cache_data(show_spinner=False)
def _parse_from_upload(file_name: str, file_bytes: bytes, parser_schema_version: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="finished_course_upload_") as temp_dir:
        safe_name = Path(file_name).name or "course.docx"
        docx_path = Path(temp_dir) / safe_name
        docx_path.write_bytes(file_bytes)
        course = parse_finished_course(docx_path)
    payload = validate_finished_course_payload(course.to_payload())
    return {**payload, "_parser_schema_version": parser_schema_version}


def _reset_course_state(*, clear_upload_signature: bool = False, reset_uploader: bool = False) -> None:
    payload = st.session_state.get("course_payload")
    if payload:
        cid = course_id(payload)
        _clear_practice_state(cid)
        _clear_fill_progress(cid)
        st.session_state.pop(_course_stage_key(cid), None)
    st.session_state.pop("course_payload", None)
    if clear_upload_signature:
        st.session_state.pop("uploaded_signature", None)
        st.session_state.pop("parsed_payload", None)
        _parse_from_upload.clear()
    if reset_uploader:
        st.session_state[UPLOAD_NONCE_KEY] = int(st.session_state.get(UPLOAD_NONCE_KEY, 0)) + 1


def _consume_flow_action(cid: str) -> None:
    action = str(st.query_params.get("flow_action", ""))
    flow_course = str(st.query_params.get("flow_course", ""))
    if action == "practice" and flow_course == cid:
        _set_course_stage(cid, COURSE_STAGE_PRACTICE)
        for key in ("flow_action", "flow_course", "flow_nonce"):
            if key in st.query_params:
                del st.query_params[key]


def _step_indicator_html(active_stage: str) -> str:
    steps = [
        (COURSE_STAGE_SHOW, "知识展示"),
        (COURSE_STAGE_FILL, "知识填空"),
        (COURSE_STAGE_PRACTICE, "快速练习"),
    ]
    items = []
    for stage, label in steps:
        active = " active" if stage == active_stage else ""
        items.append(f'<span class="flow-step{active}">{html.escape(label)}</span>')
    return '<nav class="flow-steps" aria-label="学习流程">' + "".join(items) + "</nav>"


def _render_fill_tab(payload: dict[str, Any]) -> None:
    cid = course_id(payload)
    blanks = payload["blanks"]
    if not blanks:
        st.info("这份资料没有识别到 Word 下划线填空。")
        return

    word_bank = build_word_bank(blanks, cid, distractor_ratio=1.0)
    result = FILL_INTERACTION_COMPONENT(
        html=fill_interaction_html(
            payload["knowledge_paragraphs"],
            blanks,
            payload.get("knowledge_images", []),
            word_bank,
            course_cid=cid,
        ),
        default={},
        key=f"fill_interaction_{cid}",
    )
    if _handle_fill_component_result(cid, result):
        st.rerun()


def _render_practice_tab(payload: dict[str, Any]) -> None:
    cid = course_id(payload)
    result_key = _practice_result_key(cid)
    questions = payload["quick_practice"]
    physics_payload = _is_physics_payload(payload)

    if result_key in st.session_state:
        result = st.session_state[result_key]
        result_items = result.get("items", result.get("wrong_items", []))
        result_total = len(result_items)
        result_score = int(result.get("score", 0))
        result_accuracy = _practice_accuracy_percent(result_score, result_total)
        st.markdown(
            f'<div class="practice-result-card"><strong>快速练习得分：</strong>'
            f'{result_score} / {result_total}'
            f'<span class="practice-result-rate">正确率：{result_accuracy}%</span></div>',
            unsafe_allow_html=True,
        )
        for item in result_items:
            display_index = int(item.get("display_index", item.get("index", 0)) or 0)
            original_index = int(item.get("original_index", display_index - 1) or 0)
            source_question = questions[original_index] if 0 <= original_index < len(questions) else {}
            is_correct = bool(item.get("is_correct"))
            state_class = "is-correct" if is_correct else "is-wrong"
            status = "正确" if is_correct else "错误"
            analysis = str(item.get("analysis") or source_question.get("analysis", "")).strip()
            analysis_html = (
                f'<div class="practice-review-analysis"><strong>解析：</strong>{html.escape(analysis)}</div>'
                if analysis
                else ""
            )
            st.markdown(
                f'<div class="practice-review-item {state_class}">'
                f'<span class="practice-review-status">{status}</span><br>'
                f'<strong>第 {display_index} 题</strong><br>'
                f'{html.escape(str(item["stem"]))}<br>'
                f'你的选择：{html.escape(str(item["selected"] or "未作答"))}<br>'
                f'正确答案：{html.escape(str(item["correct"]))}'
                f'{analysis_html}'
                '</div>',
                unsafe_allow_html=True,
            )
        if st.button("重新练习", key=f"practice_restart_{cid}"):
            st.session_state.pop(result_key, None)
            _reset_practice_sample(cid)
            st.rerun()
        return

    sample = _current_practice_sample(cid, len(questions))
    sample_indexes = list(sample["indexes"])
    sample_round = int(sample["round"])
    sampled_questions = [
        (display_index, original_index, questions[original_index])
        for display_index, original_index in enumerate(sample_indexes, start=1)
    ]

    with st.form(f"practice_form_{cid}"):
        selected_answers: list[tuple[int, int, dict[str, Any], str | None]] = []
        current_category = ""
        for display_index, original_index, question in sampled_questions:
            category = str(question.get("category") or "").strip()
            if not physics_payload and category and category != current_category:
                current_category = category
                st.markdown(
                    f'<div class="practice-group-title">{html.escape(str(current_category))}</div>',
                    unsafe_allow_html=True,
                )
            with st.container(border=True):
                st.markdown(
                    '<div class="question-stem">'
                    f'<span class="question-number">{display_index}</span>'
                    f'<span>{html.escape(str(question["stem"]))}</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                if question.get("images"):
                    st.markdown(image_group_html(question["images"]), unsafe_allow_html=True)
                options = stable_options(question["correct"], question["wrong"], f"{cid}-question-{sample_round}-{original_index}")
                option_labels = {option: f"{chr(65 + option_index)}. {option}" for option_index, option in enumerate(options)}
                selected = st.radio(
                    "选择答案",
                    options,
                    index=None,
                    key=f"practice_{cid}_{sample_round}_{display_index}",
                    label_visibility="collapsed",
                    format_func=lambda value, labels=option_labels: labels.get(value, value),
                )
                selected_answers.append((display_index, original_index, question, selected))
        submitted = st.form_submit_button("提交快速练习")

    if submitted:
        result_items = []
        score = 0
        for display_index, original_index, question, selected in selected_answers:
            is_correct = selected == question["correct"]
            if is_correct:
                score += 1
            result_items.append(
                {
                    "index": display_index,
                    "display_index": display_index,
                    "original_index": original_index,
                    "stem": question["stem"],
                    "selected": selected,
                    "correct": question["correct"],
                    "analysis": question.get("analysis", ""),
                    "is_correct": is_correct,
                }
            )
        st.session_state[result_key] = {"score": score, "items": result_items, "source_indexes": sample_indexes}
        st.rerun()


def _render_course(payload: dict[str, Any]) -> None:
    cid = course_id(payload)
    _consume_flow_action(cid)
    active_stage = _current_course_stage(cid)
    st.markdown(
        f'<section class="course-title-card"><h1>{html.escape(str(payload["title"]))}</h1></section>',
        unsafe_allow_html=True,
    )
    if st.button("重新上传资料", key=f"reset_upload_{cid}"):
        _reset_course_state(clear_upload_signature=True, reset_uploader=True)
        st.rerun()
    st.markdown(_step_indicator_html(active_stage), unsafe_allow_html=True)

    if active_stage == COURSE_STAGE_SHOW:
        with st.container(border=True):
            st.markdown('<div class="section-kicker">知识展示</div>', unsafe_allow_html=True)
            st.markdown(
                knowledge_html(payload["knowledge_paragraphs"], payload["blanks"], payload.get("knowledge_images", [])),
                unsafe_allow_html=True,
            )
        if st.button("进入知识填空", type="primary", key=f"enter_fill_{cid}"):
            _set_course_stage(cid, COURSE_STAGE_FILL)
            st.rerun()
        return

    if active_stage == COURSE_STAGE_FILL:
        with st.container(border=True):
            st.markdown('<div class="section-kicker">选词填空</div>', unsafe_allow_html=True)
            _render_fill_tab(payload)
        if st.button("重新记忆", key=f"restart_memory_{cid}"):
            _clear_fill_progress(cid)
            _set_course_stage(cid, COURSE_STAGE_SHOW)
            st.rerun()
        return

    if active_stage == COURSE_STAGE_PRACTICE:
        with st.container(border=True):
            st.markdown('<div class="section-kicker">快速练习</div>', unsafe_allow_html=True)
            _render_practice_tab(payload)


def main() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)

    active_payload = st.session_state.get("course_payload")
    if active_payload is not None and _payload_needs_reparse(active_payload):
        _reset_course_state(clear_upload_signature=True, reset_uploader=True)
        st.rerun()
    if active_payload is not None:
        _render_course(active_payload)
        return

    st.markdown('<div class="app-shell-title">成品背记资料学习页</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="app-shell-caption">上传已经生成好的背记课 Word，进入知识展示、选词填空和快速练习。</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        uploaded = st.file_uploader("上传成品背记资料 Word", type=["docx"], accept_multiple_files=False, key=_upload_widget_key())
    parsed_payload = st.session_state.get("parsed_payload")
    if parsed_payload is not None and _payload_needs_reparse(parsed_payload):
        st.session_state.pop("parsed_payload", None)
        parsed_payload = None
        st.session_state.pop("uploaded_signature", None)

    if uploaded is None and parsed_payload is None:
        st.info("请先上传 `.docx` 成品背记资料。")
        return

    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        upload_signature = hashlib.sha256(uploaded.name.encode("utf-8") + file_bytes).hexdigest()
        if st.session_state.get("uploaded_signature") != upload_signature or parsed_payload is None:
            _reset_course_state()
            try:
                with st.spinner("正在识别成品背记资料结构..."):
                    parsed_payload = _parse_from_upload(uploaded.name, file_bytes, PARSER_SCHEMA_VERSION)
            except Exception as exc:
                st.error(f"无法识别这个 Word 文件：{exc}")
                return
            st.session_state["uploaded_signature"] = upload_signature
            st.session_state["parsed_payload"] = parsed_payload
            st.rerun()

    all_images = _all_course_images(parsed_payload)
    unsupported_images = [image for image in all_images if not image.get("renderable")]
    if unsupported_images:
        st.caption("部分 Word 专用格式配图会先显示为占位提示。")

    config = _deepseek_config()
    if not config.api_key:
        st.caption("未检测到 DeepSeek Key：填空干扰项会使用代码兜底生成。")
    st.markdown(
        '<section class="course-ready-card">'
        '<p>已识别课程</p>'
        f'<h2>{html.escape(str(parsed_payload["title"]))}</h2>'
        '<p>生成填空干扰项后即可开始学习。</p>'
        '</section>',
        unsafe_allow_html=True,
    )
    if st.button("生成填空干扰项并开始学习", type="primary"):
        progress_bar = st.progress(0.0)
        status_slot = st.empty()

        def _progress_update(event: dict[str, Any]) -> None:
            batches = max(1, int(event.get("batches", 1)))
            batch = max(1, int(event.get("batch", 1)))
            attempt = max(1, int(event.get("attempt", 1)))
            pending = max(0, int(event.get("pending", 0)))
            attempt_fraction = 0.0 if attempt == 1 else 0.45
            progress = min(0.98, max(0.02, ((batch - 1) + attempt_fraction) / batches))
            progress_bar.progress(progress)
            status_slot.info(f"正在生成第 {batch}/{batches} 批，第 {attempt} 次尝试，待处理 {pending} 项...")

        try:
            status_slot.info("正在准备 DeepSeek 高质量干扰项生成...")
            payload = _tag_parser_schema(generate_blank_distractors(parsed_payload, config, progress_callback=_progress_update))
            progress_bar.progress(1.0)
            status_slot.success("干扰项生成完成，正在进入学习页...")
            st.session_state["course_payload"] = payload
            generated_cid = course_id(payload)
            _clear_practice_state(generated_cid)
            _clear_fill_progress(generated_cid)
            _set_course_stage(generated_cid, COURSE_STAGE_SHOW)
            st.rerun()
        except Exception as exc:
            st.error(f"生成填空干扰项失败：{exc}")


if __name__ == "__main__":
    main()

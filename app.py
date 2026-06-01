from __future__ import annotations

import hashlib
import html
import os
from pathlib import Path
import tempfile
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from src.memory_course_web.finished_course_parser import parse_finished_course
from src.memory_course_web.generation import DeepSeekConfig, generate_blank_distractors
from src.memory_course_web.rendering import build_word_bank, course_id, fill_interaction_html, image_group_html, knowledge_html, stable_options
from src.memory_course_web.validation import validate_finished_course_payload


st.set_page_config(page_title="成品背记资料学习页", layout="wide")


APP_CSS = """
<style>
.stApp {
  background:
    linear-gradient(180deg, rgba(255, 247, 224, .92) 0%, rgba(255, 253, 247, .98) 48%, #fffaf0 100%),
    repeating-linear-gradient(0deg, rgba(139, 92, 24, .035) 0, rgba(139, 92, 24, .035) 1px, transparent 1px, transparent 32px);
  color: #2f261a;
}
.main .block-container {
  max-width: 980px;
  padding-top: 1.6rem;
  padding-bottom: 3.5rem;
}
h1, h2, h3 {
  letter-spacing: 0;
  color: #2f261a;
}
.app-shell-title {
  margin: 0 0 .35rem;
  font-size: 1.65rem;
  font-weight: 800;
  color: #3a2a13;
}
.app-shell-caption {
  color: #7b674c;
  font-size: .96rem;
  margin-bottom: 1.1rem;
}
.course-ready-card,
.learning-card {
  border: 1px solid #ead7ad;
  border-radius: 8px;
  background: rgba(255, 253, 247, .97);
  box-shadow: 0 12px 30px rgba(111, 78, 32, .09);
}
.course-ready-card {
  padding: 1rem 1.1rem;
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
.course-title-card {
  padding: 1.05rem 1.2rem;
  margin: .65rem 0 1rem;
  border: 1px solid #ead7ad;
  border-left: 5px solid #e3a72f;
  border-radius: 8px;
  background: #fffdf7;
  box-shadow: 0 12px 30px rgba(111, 78, 32, .09);
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
  margin-bottom: .85rem;
  color: #9a5b00;
  font-size: .9rem;
  font-weight: 800;
}
.section-kicker::before {
  content: "";
  width: .45rem;
  height: .45rem;
  border-radius: 999px;
  background: #f2bd45;
}
.stTabs [data-baseweb="tab-list"] {
  gap: .35rem;
  border-bottom: 1px solid #ead7ad;
}
.stTabs [data-baseweb="tab"] {
  height: 2.65rem;
  padding: .2rem .9rem;
  border-radius: 8px 8px 0 0;
  color: #7b674c;
  font-weight: 700;
}
.stTabs [aria-selected="true"] {
  background: #fffdf7;
  color: #9a5b00;
  border: 1px solid #ead7ad;
  border-bottom-color: #fffdf7;
}
.stButton > button,
.stDownloadButton > button,
button[kind="primary"] {
  border-radius: 7px;
  font-weight: 700;
}
.stButton > button[kind="primary"] {
  background: #c77700;
  border-color: #c77700;
}
.stButton > button[kind="primary"]:hover {
  background: #a86200;
  border-color: #a86200;
}
.stFileUploader section {
  border-radius: 8px;
  border-color: #ead7ad;
  background: #fffaf0;
}
.knowledge-body p {
  font-family: "Microsoft YaHei", "SimSun", sans-serif;
  font-size: 1rem;
  line-height: 2.05;
  margin: 0 0 .78rem;
  color: #2f261a;
}
.answer-mark {
  border-bottom: 1.5px solid #c77700;
  background: #fff0c2;
  color: #4a3514;
  padding: 0 .16rem;
  border-radius: 3px 3px 0 0;
}
.course-images {
  display: flex;
  flex-wrap: wrap;
  gap: .85rem;
  margin: .55rem 0 1.05rem;
}
.course-image-wrap { margin: 0; }
.course-image {
  display: block;
  max-height: 420px;
  object-fit: contain;
  border: 1px solid #ead7ad;
  border-radius: 8px;
  background: #fffdf7;
  padding: .45rem;
  box-shadow: 0 8px 20px rgba(111, 78, 32, .08);
}
.course-image-placeholder {
  border: 1px dashed #c8a76a;
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
.source-note {
  display: inline-flex;
  align-items: center;
  margin: 0 0 .8rem;
  padding: .36rem .62rem;
  border: 1px solid #efd9a4;
  border-radius: 999px;
  background: #fff8dc;
  color: #835108;
  font-size: .88rem;
  font-weight: 700;
}
.practice-group-title {
  display: flex;
  align-items: center;
  margin: 1rem 0 .65rem;
  color: #9a5b00;
  font-size: 1.05rem;
  font-weight: 800;
}
.practice-group-title::before {
  content: "";
  width: 4px;
  height: 1.05rem;
  margin-right: .5rem;
  border-radius: 999px;
  background: #f2bd45;
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
  background: #fff1c8;
  color: #9a5b00;
  font-size: .9rem;
  font-weight: 800;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-color: #ead7ad;
  border-radius: 8px;
  background: rgba(255, 253, 247, .96);
  box-shadow: 0 8px 20px rgba(111, 78, 32, .065);
}
.practice-result-card {
  padding: 1rem 1.1rem;
  border: 1px solid #ead7ad;
  border-radius: 8px;
  background: #fffdf7;
  box-shadow: 0 10px 24px rgba(111, 78, 32, .08);
}
.practice-result-card strong {
  color: #9a5b00;
}
.wrong-item {
  padding: .75rem .85rem;
  margin: .7rem 0 0;
  border-left: 4px solid #c44747;
  border-radius: 7px;
  background: #fff7f7;
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


@st.cache_data(show_spinner=False)
def _parse_from_upload(file_name: str, file_bytes: bytes) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="finished_course_upload_") as temp_dir:
        safe_name = Path(file_name).name or "course.docx"
        docx_path = Path(temp_dir) / safe_name
        docx_path.write_bytes(file_bytes)
        course = parse_finished_course(docx_path)
    return validate_finished_course_payload(course.to_payload())


def _reset_course_state() -> None:
    payload = st.session_state.get("course_payload")
    if payload:
        cid = course_id(payload)
        st.session_state.pop(f"practice_result_{cid}", None)
    st.session_state.pop("course_payload", None)


def _distractor_sources(payload: dict[str, Any]) -> list[str]:
    sources = {
        str(blank.get("distractor_source", "")).strip()
        for blank in payload.get("blanks", [])
        if str(blank.get("distractor_source", "")).strip()
    }
    if not sources:
        sources = {str(source).strip() for source in payload.get("distractor_summary", {}) if str(source).strip()}

    preferred = ["DeepSeek", "代码兜底"]
    ordered = [source for source in preferred if source in sources]
    ordered.extend(sorted(source for source in sources if source not in preferred))
    return ordered


def _render_fill_tab(payload: dict[str, Any]) -> None:
    cid = course_id(payload)
    blanks = payload["blanks"]
    if not blanks:
        st.info("这份资料没有识别到 Word 下划线填空。")
        return

    sources = _distractor_sources(payload)
    if sources:
        st.markdown(
            f'<div class="source-note">干扰项来源：{html.escape("、".join(sources))}</div>',
            unsafe_allow_html=True,
        )

    word_bank = build_word_bank(blanks, cid, distractor_ratio=1.0)
    height = max(720, min(1500, 330 + len(payload["knowledge_paragraphs"]) * 72 + len(word_bank) * 26))
    components.html(
        fill_interaction_html(
            payload["knowledge_paragraphs"],
            blanks,
            payload.get("knowledge_images", []),
            word_bank,
        ),
        height=height,
        scrolling=True,
    )


def _render_practice_tab(payload: dict[str, Any]) -> None:
    cid = course_id(payload)
    result_key = f"practice_result_{cid}"
    questions = payload["quick_practice"]

    if result_key in st.session_state:
        result = st.session_state[result_key]
        st.markdown(
            f'<div class="practice-result-card"><strong>快速练习得分：</strong>'
            f'{result["score"]} / {len(questions)}</div>',
            unsafe_allow_html=True,
        )
        for item in result["wrong_items"]:
            st.markdown(
                '<div class="wrong-item">'
                f'<strong>第 {item["index"]} 题</strong><br>'
                f'{html.escape(str(item["stem"]))}<br>'
                f'你的选择：{html.escape(str(item["selected"] or "未作答"))}<br>'
                f'正确答案：{html.escape(str(item["correct"]))}'
                '</div>',
                unsafe_allow_html=True,
            )
        if st.button("重新练习", key=f"practice_restart_{cid}"):
            st.session_state.pop(result_key, None)
            st.rerun()
        return

    with st.form(f"practice_form_{cid}"):
        selected_answers: list[tuple[int, dict[str, Any], str | None]] = []
        current_category = ""
        for index, question in enumerate(questions, start=1):
            if question["category"] != current_category:
                current_category = question["category"]
                st.markdown(
                    f'<div class="practice-group-title">{html.escape(str(current_category))}</div>',
                    unsafe_allow_html=True,
                )
            with st.container(border=True):
                st.markdown(
                    '<div class="question-stem">'
                    f'<span class="question-number">{index}</span>'
                    f'<span>{html.escape(str(question["stem"]))}</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                if question.get("images"):
                    st.markdown(image_group_html(question["images"]), unsafe_allow_html=True)
                options = stable_options(question["correct"], question["wrong"], f"{cid}-question-{index}")
                option_labels = {option: f"{chr(65 + option_index)}. {option}" for option_index, option in enumerate(options)}
                selected = st.radio(
                    "选择答案",
                    options,
                    index=None,
                    key=f"practice_{cid}_{index}",
                    label_visibility="collapsed",
                    format_func=lambda value, labels=option_labels: labels.get(value, value),
                )
                selected_answers.append((index, question, selected))
        submitted = st.form_submit_button("提交快速练习")

    if submitted:
        wrong_items = []
        score = 0
        for index, question, selected in selected_answers:
            if selected == question["correct"]:
                score += 1
            else:
                wrong_items.append(
                    {
                        "index": index,
                        "stem": question["stem"],
                        "selected": selected,
                        "correct": question["correct"],
                    }
                )
        st.session_state[result_key] = {"score": score, "wrong_items": wrong_items}
        st.rerun()


def _render_course(payload: dict[str, Any]) -> None:
    st.markdown(
        f'<section class="course-title-card"><h1>{html.escape(str(payload["title"]))}</h1></section>',
        unsafe_allow_html=True,
    )
    tab_show, tab_fill, tab_practice = st.tabs(["知识展示", "知识填空", "快速练习"])
    with tab_show:
        with st.container(border=True):
            st.markdown('<div class="section-kicker">知识展示</div>', unsafe_allow_html=True)
            st.markdown(
                knowledge_html(payload["knowledge_paragraphs"], payload["blanks"], payload.get("knowledge_images", [])),
                unsafe_allow_html=True,
            )
    with tab_fill:
        with st.container(border=True):
            st.markdown('<div class="section-kicker">选词填空</div>', unsafe_allow_html=True)
            _render_fill_tab(payload)
    with tab_practice:
        with st.container(border=True):
            st.markdown('<div class="section-kicker">快速练习</div>', unsafe_allow_html=True)
            _render_practice_tab(payload)


def main() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)

    active_payload = st.session_state.get("course_payload")
    if active_payload is not None:
        _render_course(active_payload)
        return

    st.markdown('<div class="app-shell-title">成品背记资料学习页</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="app-shell-caption">上传已经生成好的背记课 Word，进入知识展示、选词填空和快速练习。</div>',
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        uploaded = st.file_uploader("上传成品背记资料 Word", type=["docx"], accept_multiple_files=False)
    if uploaded is None:
        st.info("请先上传 `.docx` 成品背记资料。")
        return

    file_bytes = uploaded.getvalue()
    upload_signature = hashlib.sha256(uploaded.name.encode("utf-8") + file_bytes).hexdigest()
    if st.session_state.get("uploaded_signature") != upload_signature:
        st.session_state["uploaded_signature"] = upload_signature
        _reset_course_state()

    try:
        with st.spinner("正在识别成品背记资料结构..."):
            parsed_payload = _parse_from_upload(uploaded.name, file_bytes)
    except Exception as exc:
        st.error(f"无法识别这个 Word 文件：{exc}")
        return

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
        try:
            with st.spinner("正在补齐填空干扰项..."):
                payload = generate_blank_distractors(parsed_payload, config)
            st.session_state["course_payload"] = payload
            st.session_state.pop(f"practice_result_{course_id(payload)}", None)
            st.rerun()
        except Exception as exc:
            st.error(f"生成填空干扰项失败：{exc}")


if __name__ == "__main__":
    main()

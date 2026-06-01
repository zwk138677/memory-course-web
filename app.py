from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any

import streamlit as st

from src.memory_course_web.finished_course_parser import parse_finished_course
from src.memory_course_web.generation import DeepSeekConfig, generate_blank_distractors
from src.memory_course_web.rendering import blank_prompt_html, course_id, image_group_html, knowledge_html, stable_options
from src.memory_course_web.validation import validate_finished_course_payload


st.set_page_config(page_title="成品背记资料学习页", layout="wide")


APP_CSS = """
<style>
.main .block-container { max-width: 1120px; padding-top: 1.4rem; }
.knowledge-body p, .blank-prompt p {
  font-size: 1.02rem;
  line-height: 1.9;
  margin: 0 0 .85rem;
}
.answer-mark {
  border-bottom: 2px solid #2563eb;
  background: #eff6ff;
  padding: 0 .14rem;
}
.blank-slot {
  border-bottom: 2px solid #111827;
  color: transparent;
  padding: 0 .2rem;
}
.blank-prompt {
  border-left: 4px solid #2563eb;
  padding: .85rem 1rem;
  background: #f8fafc;
}
.course-images {
  display: flex;
  flex-wrap: wrap;
  gap: .75rem;
  margin: .45rem 0 1rem;
}
.course-image-wrap {
  margin: 0;
}
.course-image {
  display: block;
  max-height: 420px;
  object-fit: contain;
  border: 1px solid #dbe3ef;
  border-radius: 6px;
  background: #fff;
  padding: .35rem;
}
.course-image-placeholder {
  border: 1px dashed #94a3b8;
  border-radius: 6px;
  background: #f8fafc;
  color: #475569;
  padding: .75rem .9rem;
  font-size: .92rem;
}
.course-image-placeholder span {
  color: #64748b;
  font-size: .84rem;
}
.source-badge {
  display: inline-block;
  color: #475569;
  background: #f1f5f9;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  padding: .12rem .5rem;
  font-size: .82rem;
  margin-left: .35rem;
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


def _reset_fill_state(cid: str) -> None:
    for suffix in ("index", "answers", "waiting", "feedback"):
        st.session_state.pop(f"fill_{cid}_{suffix}", None)


def _reset_practice_state(cid: str) -> None:
    st.session_state.pop(f"practice_result_{cid}", None)


def _reset_course_state() -> None:
    payload = st.session_state.get("course_payload")
    if payload:
        cid = course_id(payload)
        _reset_fill_state(cid)
        _reset_practice_state(cid)
    st.session_state.pop("course_payload", None)


def _source_badge(source: str) -> str:
    safe = source or "未生成"
    return f'<span class="source-badge">干扰项来源：{safe}</span>'


def _render_fill_tab(payload: dict[str, Any]) -> None:
    cid = course_id(payload)
    blanks = payload["blanks"]
    if not blanks:
        st.info("这份资料没有识别到 Word 下划线填空。")
        return

    index_key = f"fill_{cid}_index"
    answers_key = f"fill_{cid}_answers"
    waiting_key = f"fill_{cid}_waiting"
    feedback_key = f"fill_{cid}_feedback"

    st.session_state.setdefault(index_key, 0)
    st.session_state.setdefault(answers_key, [])
    st.session_state.setdefault(waiting_key, False)

    completed = st.session_state[index_key] >= len(blanks)
    if completed:
        answers = st.session_state[answers_key]
        correct_count = sum(1 for item in answers if item["is_correct"])
        st.success(f"本轮填空完成：{correct_count} / {len(blanks)}")
        if st.button("重新练习填空", key=f"fill_restart_{cid}"):
            _reset_fill_state(cid)
            st.rerun()
        return

    current_index = st.session_state[index_key]
    blank = blanks[current_index]
    st.markdown(
        f"**第 {current_index + 1} / {len(blanks)} 空** "
        + _source_badge(str(blank.get("distractor_source", ""))),
        unsafe_allow_html=True,
    )
    st.markdown(
        blank_prompt_html(payload["knowledge_paragraphs"], blank, payload.get("knowledge_images", [])),
        unsafe_allow_html=True,
    )

    if st.session_state.get(waiting_key):
        feedback = st.session_state.get(feedback_key, {})
        if feedback.get("is_correct"):
            st.success("回答正确。")
        else:
            st.error(f"回答错误。正确答案：{feedback.get('correct', blank['answer'])}")
        if st.button("下一空", key=f"fill_next_{cid}"):
            st.session_state[index_key] += 1
            st.session_state[waiting_key] = False
            st.session_state.pop(feedback_key, None)
            st.rerun()
        return

    options = stable_options(blank["answer"], blank["distractors"], f"{cid}-blank-{current_index}")
    selected = st.radio("选择正确内容", options, index=None, key=f"fill_choice_{cid}_{current_index}")
    if st.button("提交本空", key=f"fill_submit_{cid}_{current_index}", disabled=selected is None):
        is_correct = selected == blank["answer"]
        feedback = {"selected": selected, "correct": blank["answer"], "is_correct": is_correct}
        st.session_state[answers_key].append(feedback)
        st.session_state[feedback_key] = feedback
        st.session_state[waiting_key] = True
        st.rerun()


def _render_practice_tab(payload: dict[str, Any]) -> None:
    cid = course_id(payload)
    result_key = f"practice_result_{cid}"
    questions = payload["quick_practice"]

    if result_key in st.session_state:
        result = st.session_state[result_key]
        st.success(f"快速练习得分：{result['score']} / {len(questions)}")
        for item in result["wrong_items"]:
            st.markdown(f"**第 {item['index']} 题** {item['stem']}")
            st.write(f"你的选择：{item['selected'] or '未作答'}")
            st.write(f"正确答案：{item['correct']}")
        if st.button("重新练习", key=f"practice_restart_{cid}"):
            _reset_practice_state(cid)
            st.rerun()
        return

    with st.form(f"practice_form_{cid}"):
        selected_answers: list[tuple[int, dict[str, Any], str | None]] = []
        current_category = ""
        for index, question in enumerate(questions, start=1):
            if question["category"] != current_category:
                current_category = question["category"]
                st.subheader(current_category)
            st.markdown(f"**{index}. {question['stem']}**")
            if question.get("images"):
                st.markdown(image_group_html(question["images"]), unsafe_allow_html=True)
            options = stable_options(question["correct"], question["wrong"], f"{cid}-question-{index}")
            selected = st.radio("选择答案", options, index=None, key=f"practice_{cid}_{index}", label_visibility="collapsed")
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
    st.header(payload["title"])
    summary = payload.get("distractor_summary", {})
    if summary:
        st.caption("；".join(f"{source}：{count} 个填空" for source, count in summary.items()))
    tab_show, tab_fill, tab_practice = st.tabs(["知识展示", "知识填空", "快速练习"])
    with tab_show:
        st.markdown(
            knowledge_html(payload["knowledge_paragraphs"], payload["blanks"], payload.get("knowledge_images", [])),
            unsafe_allow_html=True,
        )
    with tab_fill:
        _render_fill_tab(payload)
    with tab_practice:
        _render_practice_tab(payload)


def main() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.title("成品背记资料学习页")
    st.caption("上传已经生成好的背记课 Word，网页会识别知识展示、下划线填空和快速练习。")

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

    st.subheader("识别摘要")
    all_images = _all_course_images(parsed_payload)
    unsupported_images = [image for image in all_images if not image.get("renderable")]
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("标题", parsed_payload["title"])
    col2.metric("知识段落", len(parsed_payload["knowledge_paragraphs"]))
    col3.metric("填空", len(parsed_payload["blanks"]))
    col4.metric("快速练习", len(parsed_payload["quick_practice"]))
    col5.metric("配图", len(all_images))
    if unsupported_images:
        st.caption(f"已识别 {len(all_images)} 张配图，其中 {len(unsupported_images)} 张为 Word 专用格式，网页会先显示占位。")

    with st.expander("知识正文预览", expanded=False):
        st.text_area("已识别知识正文", "\n".join(parsed_payload["knowledge_paragraphs"]), height=220)

    payload = st.session_state.get("course_payload")
    if payload is None:
        config = _deepseek_config()
        if not config.api_key:
            st.caption("未检测到 DeepSeek Key：填空干扰项会使用代码兜底生成。")
        if st.button("生成填空干扰项并开始学习", type="primary"):
            try:
                with st.spinner("正在补齐填空干扰项..."):
                    payload = generate_blank_distractors(parsed_payload, config)
                st.session_state["course_payload"] = payload
                _reset_fill_state(course_id(payload))
                _reset_practice_state(course_id(payload))
                st.rerun()
            except Exception as exc:
                st.error(f"生成填空干扰项失败：{exc}")
        return

    if st.button("重新生成填空干扰项"):
        _reset_course_state()
        st.rerun()

    _render_course(payload)


if __name__ == "__main__":
    main()

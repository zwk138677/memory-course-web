"""Small HTML/rendering helpers for Streamlit pages."""

from __future__ import annotations

import hashlib
import html
import random
from typing import Any


def stable_options(correct: str, wrong: list[str], salt: str) -> list[str]:
    options = [correct, *wrong]
    seed = int(hashlib.sha256(salt.encode("utf-8")).hexdigest()[:12], 16)
    rng = random.Random(seed)
    rng.shuffle(options)
    return options


def _stable_rng(salt: str) -> random.Random:
    seed = int(hashlib.sha256(salt.encode("utf-8")).hexdigest()[:12], 16)
    return random.Random(seed)


def _clean_option_text(value: Any) -> str:
    return " ".join(str(value).split()).strip()


def _fallback_distractor_text(index: int, used: set[str], answer_keys: set[str]) -> str:
    suffix = index
    while True:
        candidate = f"干扰项{suffix}"
        key = candidate.casefold()
        if key not in used and key not in answer_keys:
            return candidate
        suffix += 1


def build_word_bank(blanks: list[dict[str, Any]], salt: str, *, distractor_ratio: float = 1.0) -> list[dict[str, Any]]:
    """Build one shuffled word-bank option list.

    Options are counted by blank, not by unique text. If two blanks share the
    same answer text, they still produce two independent correct options.
    """

    answer_keys = {_clean_option_text(blank.get("answer", "")).casefold() for blank in blanks}
    options: list[dict[str, Any]] = []
    used_distractor_keys: set[str] = set()

    for index, blank in enumerate(blanks, start=1):
        blank_id = str(blank.get("id") or f"b{index:03d}")
        answer = _clean_option_text(blank.get("answer", ""))
        options.append(
            {
                "option_id": f"answer-{blank_id}",
                "text": answer,
                "is_answer": True,
                "blank_id": blank_id,
                "source_blank_id": blank_id,
            }
        )

        distractor = ""
        for candidate in blank.get("distractors", []):
            cleaned = _clean_option_text(candidate)
            key = cleaned.casefold()
            if cleaned and key not in answer_keys and key not in used_distractor_keys:
                distractor = cleaned
                break
        if not distractor:
            distractor = _fallback_distractor_text(index, used_distractor_keys, answer_keys)
        used_distractor_keys.add(distractor.casefold())
        options.append(
            {
                "option_id": f"distractor-{blank_id}",
                "text": distractor,
                "is_answer": False,
                "blank_id": "",
                "source_blank_id": blank_id,
            }
        )

    rng = _stable_rng(f"{salt}-word-bank")
    rng.shuffle(options)
    for index, option in enumerate(options, start=1):
        option["number"] = index
    return options


def course_id(payload: dict[str, Any]) -> str:
    basis = payload.get("title", "") + "\n" + "\n".join(payload.get("knowledge_paragraphs", []))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def _spans_for_marks(paragraph: str, marks: list[dict[str, Any]]) -> list[tuple[int, int, dict[str, Any]]]:
    spans: list[tuple[int, int, dict[str, Any]]] = []
    for mark in marks:
        try:
            start = int(mark["start"])
            end = int(mark["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= start < end <= len(paragraph):
            spans.append((start, end, mark))
    spans.sort(key=lambda item: (item[0], item[1]))
    return spans


def _apply_marks(paragraph: str, marks: list[dict[str, Any]], *, blank_current: bool = False) -> str:
    safe_parts: list[str] = []
    cursor = 0
    used_until = -1
    for start, end, _mark in _spans_for_marks(paragraph, marks):
        if start < used_until:
            continue
        safe_parts.append(html.escape(paragraph[cursor:start]))
        answer = html.escape(paragraph[start:end])
        if blank_current:
            blank_width = "_" * max(6, min(20, len(answer) * 2))
            safe_parts.append(f'<span class="blank-slot">{blank_width}</span>')
        else:
            safe_parts.append(f'<span class="answer-mark">{answer}</span>')
        cursor = end
        used_until = end
    safe_parts.append(html.escape(paragraph[cursor:]))
    return "".join(safe_parts)


def _apply_blank_slots(paragraph: str, marks: list[dict[str, Any]], blank_numbers: dict[str, int]) -> str:
    safe_parts: list[str] = []
    cursor = 0
    used_until = -1
    for start, end, mark in _spans_for_marks(paragraph, marks):
        if start < used_until:
            continue
        blank_id = str(mark.get("id", ""))
        blank_number = blank_numbers.get(blank_id, len(blank_numbers) + 1)
        answer_len = max(6, min(24, (end - start) * 2))
        answer = html.escape(paragraph[start:end], quote=True)
        label = html.escape(f"第 {blank_number} 空", quote=True)
        safe_parts.append(html.escape(paragraph[cursor:start]))
        safe_parts.append(
            f'<span class="word-blank word-blank-drop" role="button" tabindex="0" '
            f'data-blank-id="{html.escape(blank_id, quote=True)}" data-answer="{answer}" title="{label}">'
            f'<span class="word-blank-number">{blank_number}</span>'
            f'<span class="word-blank-answer"></span>'
            f'<span class="word-blank-line">{"_" * answer_len}</span>'
            f"</span>"
        )
        cursor = end
        used_until = end
    safe_parts.append(html.escape(paragraph[cursor:]))
    return "".join(safe_parts)


def _image_width_style(image: dict[str, Any]) -> str:
    width = image.get("width_px")
    try:
        width_int = int(width)
    except (TypeError, ValueError):
        width_int = 0
    if width_int > 0:
        return f"width: min(100%, {min(width_int, 720)}px);"
    return "max-width: min(100%, 720px);"


def image_group_html(images: list[dict[str, Any]]) -> str:
    if not images:
        return ""

    rendered: list[str] = []
    for image in images:
        filename = html.escape(str(image.get("filename") or "Word 图片"))
        mime_type = html.escape(str(image.get("mime_type") or "未知格式"))
        alt_text = html.escape(str(image.get("alt_text") or filename))
        if image.get("renderable") and image.get("data_uri"):
            src = html.escape(str(image["data_uri"]), quote=True)
            rendered.append(
                f'<figure class="course-image-wrap">'
                f'<img class="course-image" src="{src}" alt="{alt_text}" style="{_image_width_style(image)}">'
                f"</figure>"
            )
        else:
            rendered.append(
                f'<div class="course-image-placeholder">'
                f"<strong>已识别配图</strong><br>{filename}<br><span>{mime_type} 暂不支持网页直接预览</span>"
                f"</div>"
            )
    return '<div class="course-images">' + "\n".join(rendered) + "</div>"


def _group_by_paragraph(items: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_paragraph: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        try:
            paragraph_index = int(item["paragraph_index"])
        except (KeyError, TypeError, ValueError):
            continue
        by_paragraph.setdefault(paragraph_index, []).append(item)
    return by_paragraph


def knowledge_html(
    knowledge_paragraphs: list[str],
    blanks: list[dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
) -> str:
    by_paragraph = _group_by_paragraph(blanks)
    images_by_paragraph = _group_by_paragraph(images or [])

    rendered: list[str] = []
    for index, paragraph in enumerate(knowledge_paragraphs):
        paragraph_html = _apply_marks(paragraph, by_paragraph.get(index, [])) if paragraph else ""
        image_html = image_group_html(images_by_paragraph.get(index, []))
        if paragraph_html:
            rendered.append(f"<p>{paragraph_html}</p>{image_html}")
        elif image_html:
            rendered.append(image_html)
    return '<div class="knowledge-body">' + "\n".join(rendered) + "</div>"


def fill_sheet_html(
    knowledge_paragraphs: list[str],
    blanks: list[dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
) -> str:
    by_paragraph = _group_by_paragraph(blanks)
    blank_numbers = {str(blank.get("id", "")): index for index, blank in enumerate(blanks, start=1)}
    images_by_paragraph = _group_by_paragraph(images or [])

    rendered: list[str] = []
    for index, paragraph in enumerate(knowledge_paragraphs):
        paragraph_html = _apply_blank_slots(paragraph, by_paragraph.get(index, []), blank_numbers) if paragraph else ""
        image_html = image_group_html(images_by_paragraph.get(index, []))
        if paragraph_html:
            rendered.append(f"<p>{paragraph_html}</p>{image_html}")
        elif image_html:
            rendered.append(image_html)
    return '<div class="fill-sheet">' + "\n".join(rendered) + "</div>"


def word_bank_html(word_bank: list[dict[str, Any]]) -> str:
    items = []
    for option in word_bank:
        number = int(option["number"])
        text = html.escape(str(option["text"]))
        option_id = html.escape(str(option["option_id"]), quote=True)
        source_blank_id = html.escape(str(option.get("source_blank_id", "")), quote=True)
        is_answer = "true" if option.get("is_answer") else "false"
        items.append(
            '<button class="word-bank-item" type="button" draggable="true" '
            f'data-option-id="{option_id}" data-text="{html.escape(str(option["text"]), quote=True)}" '
            f'data-source-blank-id="{source_blank_id}" data-is-answer="{is_answer}">'
            f'<span class="word-bank-number">{number}</span>'
            f'<span class="word-bank-text">{text}</span>'
            "</button>"
        )
    return '<div class="word-bank">' + "\n".join(items) + "</div>"


def fill_interaction_html(
    knowledge_paragraphs: list[str],
    blanks: list[dict[str, Any]],
    images: list[dict[str, Any]] | None,
    word_bank: list[dict[str, Any]],
) -> str:
    sheet = fill_sheet_html(knowledge_paragraphs, blanks, images)
    bank = word_bank_html(word_bank)
    return f"""
<style>
  body {{
    margin: 0;
    font-family: "Microsoft YaHei", "SimSun", Arial, sans-serif;
    color: #2f261a;
    background: transparent;
  }}
  .fill-widget {{ padding: 0 1px 18px; }}
  .fill-sheet {{
    border: 1px solid #ead7ad;
    border-left: 5px solid #e3a72f;
    border-radius: 8px;
    padding: 1rem 1.05rem .9rem;
    background: #fffdf7;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, .85);
  }}
  .fill-sheet p {{
    font-size: 1rem;
    line-height: 2.18;
    margin: 0 0 .85rem;
  }}
  .word-blank {{
    display: inline-flex;
    align-items: center;
    gap: .26rem;
    min-width: 4.6rem;
    min-height: 1.65rem;
    margin: 0 .1rem;
    padding: 0 .35rem;
    border: 1px solid #d9bc7d;
    border-bottom: 2px solid #c77700;
    border-radius: 6px 6px 4px 4px;
    background: #fffaf0;
    box-shadow: 0 1px 0 rgba(111, 78, 32, .05);
    cursor: pointer;
    white-space: nowrap;
    transition: background .15s ease, border-color .15s ease, box-shadow .15s ease;
  }}
  .word-blank:hover {{
    border-color: #c77700;
    box-shadow: 0 0 0 3px rgba(227, 167, 47, .18);
  }}
  .word-blank-number {{ color: #9a5b00; font-size: .76rem; font-weight: 800; vertical-align: super; }}
  .word-blank-answer {{ color: #2f261a; font-weight: 800; min-width: 1rem; }}
  .word-blank-line {{ color: transparent; letter-spacing: .04rem; }}
  .word-blank.filled .word-blank-line {{ display: none; }}
  .word-blank.correct {{ background: #e8f7ed; border-color: #49a36f; border-bottom-color: #278653; }}
  .word-blank.wrong {{ background: #fff0ef; border-color: #d36b62; border-bottom-color: #c44747; }}
  .word-blank.unfilled {{ background: #fff7df; border-color: #dba74c; border-bottom-color: #c3841f; }}
  .word-bank-title {{
    margin: 1.05rem 0 .55rem;
    color: #3a2a13;
    font-weight: 800;
  }}
  .word-bank {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(156px, 1fr));
    gap: .65rem .75rem;
    padding: .9rem;
    border: 1px solid #ead7ad;
    border-radius: 8px;
    background: #fffdf7;
    box-shadow: 0 8px 20px rgba(111, 78, 32, .06);
  }}
  .word-bank-item {{
    display: flex;
    align-items: center;
    gap: .5rem;
    min-height: 2.4rem;
    padding: .42rem .55rem;
    border: 1px solid #ead7ad;
    border-radius: 7px;
    background: #fffaf0;
    color: #2f261a;
    text-align: left;
    cursor: grab;
    transition: transform .12s ease, border-color .15s ease, background .15s ease, box-shadow .15s ease;
  }}
  .word-bank-item:hover {{
    transform: translateY(-1px);
    border-color: #d49a2a;
    box-shadow: 0 6px 14px rgba(111, 78, 32, .09);
  }}
  .word-bank-item.selected {{ border-color: #c77700; background: #fff1c8; box-shadow: 0 0 0 3px rgba(227, 167, 47, .2); }}
  .word-bank-item.used {{ opacity: .42; cursor: not-allowed; }}
  .word-bank-item.used:hover {{ transform: none; box-shadow: none; }}
  .word-bank-number {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.55rem;
    height: 1.55rem;
    border-radius: 999px;
    background: #fff1c8;
    color: #9a5b00;
    font-weight: 800;
    font-size: .82rem;
  }}
  .word-bank-text {{ line-height: 1.45; }}
  .fill-actions {{ display: flex; gap: .65rem; align-items: center; flex-wrap: wrap; margin-top: .95rem; }}
  .fill-actions button {{
    border: 1px solid #e1c58b;
    border-radius: 7px;
    padding: .52rem .92rem;
    background: #fffdf7;
    color: #2f261a;
    font-weight: 800;
    cursor: pointer;
  }}
  .fill-actions .primary {{ background: #c77700; border-color: #c77700; color: #fff; }}
  .fill-actions button:hover {{ border-color: #c77700; }}
  .fill-result {{ font-weight: 800; color: #3a2a13; }}
  .course-images {{ display: flex; flex-wrap: wrap; gap: .85rem; margin: .55rem 0 1.05rem; }}
  .course-image-wrap {{ margin: 0; }}
  .course-image {{
    display: block;
    max-height: 420px;
    object-fit: contain;
    border: 1px solid #ead7ad;
    border-radius: 8px;
    background: #fffdf7;
    padding: .45rem;
    box-shadow: 0 8px 20px rgba(111, 78, 32, .08);
  }}
  .course-image-placeholder {{
    border: 1px dashed #c8a76a;
    border-radius: 8px;
    background: #fffaf0;
    color: #735f43;
    padding: .75rem .9rem;
    font-size: .92rem;
  }}
  @media (max-width: 640px) {{
    .fill-sheet {{ padding: .85rem .75rem; }}
    .fill-sheet p {{ line-height: 2.05; }}
    .word-bank {{ grid-template-columns: 1fr; }}
    .word-blank {{ min-width: 4rem; }}
  }}
</style>
<div class="fill-widget">
  {sheet}
  <div class="word-bank-title">选词库</div>
  {bank}
  <div class="fill-actions">
    <button class="primary" type="button" id="checkAnswers">提交检查</button>
    <button type="button" id="resetAnswers">重做</button>
    <span class="fill-result" id="fillResult"></span>
  </div>
</div>
<script>
(() => {{
  const options = Array.from(document.querySelectorAll(".word-bank-item"));
  const blanks = Array.from(document.querySelectorAll(".word-blank-drop"));
  let selectedOptionId = null;

  function optionById(optionId) {{
    return options.find(option => option.dataset.optionId === optionId);
  }}

  function blankByOption(optionId) {{
    return blanks.find(blank => blank.dataset.optionId === optionId);
  }}

  function setSelected(optionId) {{
    selectedOptionId = optionId;
    options.forEach(option => option.classList.toggle("selected", option.dataset.optionId === optionId));
  }}

  function clearBlank(blank) {{
    const optionId = blank.dataset.optionId;
    if (optionId) {{
      const option = optionById(optionId);
      if (option) option.classList.remove("used");
    }}
    blank.dataset.optionId = "";
    blank.classList.remove("filled", "correct", "wrong", "unfilled");
    const answer = blank.querySelector(".word-blank-answer");
    if (answer) answer.textContent = "";
  }}

  function fillBlank(blank, optionId) {{
    const option = optionById(optionId);
    if (!option || option.classList.contains("used")) return;
    const oldBlank = blankByOption(optionId);
    if (oldBlank) clearBlank(oldBlank);
    clearBlank(blank);
    blank.dataset.optionId = optionId;
    blank.classList.add("filled");
    const answer = blank.querySelector(".word-blank-answer");
    if (answer) answer.textContent = option.dataset.text || "";
    option.classList.add("used");
    setSelected(null);
  }}

  options.forEach(option => {{
    option.addEventListener("click", () => {{
      if (option.classList.contains("used")) return;
      setSelected(option.dataset.optionId);
    }});
    option.addEventListener("dragstart", event => {{
      if (option.classList.contains("used")) {{
        event.preventDefault();
        return;
      }}
      event.dataTransfer.setData("text/plain", option.dataset.optionId);
      setSelected(option.dataset.optionId);
    }});
  }});

  blanks.forEach(blank => {{
    blank.addEventListener("dragover", event => event.preventDefault());
    blank.addEventListener("drop", event => {{
      event.preventDefault();
      const optionId = event.dataTransfer.getData("text/plain");
      if (optionId) fillBlank(blank, optionId);
    }});
    blank.addEventListener("click", () => {{
      if (selectedOptionId) {{
        fillBlank(blank, selectedOptionId);
      }} else if (blank.dataset.optionId) {{
        clearBlank(blank);
      }}
    }});
    blank.addEventListener("keydown", event => {{
      if (event.key === "Enter" || event.key === " ") {{
        event.preventDefault();
        blank.click();
      }}
    }});
  }});

  document.getElementById("checkAnswers").addEventListener("click", () => {{
    let score = 0;
    blanks.forEach(blank => {{
      blank.classList.remove("correct", "wrong", "unfilled");
      const filled = (blank.querySelector(".word-blank-answer")?.textContent || "").trim();
      const expected = (blank.dataset.answer || "").trim();
      if (!filled) {{
        blank.classList.add("unfilled");
      }} else if (filled === expected) {{
        blank.classList.add("correct");
        score += 1;
      }} else {{
        blank.classList.add("wrong");
      }}
    }});
    document.getElementById("fillResult").textContent = `得分：${{score}} / ${{blanks.length}}`;
  }});

  document.getElementById("resetAnswers").addEventListener("click", () => {{
    blanks.forEach(clearBlank);
    options.forEach(option => option.classList.remove("used", "selected"));
    selectedOptionId = null;
    document.getElementById("fillResult").textContent = "";
  }});
}})();
</script>
"""


def blank_prompt_html(
    knowledge_paragraphs: list[str],
    blank: dict[str, Any],
    images: list[dict[str, Any]] | None = None,
) -> str:
    paragraph_index = int(blank["paragraph_index"])
    paragraph = knowledge_paragraphs[paragraph_index]
    rendered = _apply_marks(paragraph, [blank], blank_current=True)
    paragraph_images = [image for image in images or [] if int(image.get("paragraph_index", -1)) == paragraph_index]
    return f'<div class="blank-prompt"><p>{rendered}</p>{image_group_html(paragraph_images)}</div>'

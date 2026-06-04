"""Small HTML/rendering helpers for Streamlit pages."""

from __future__ import annotations

import hashlib
import html
import random
import re
from typing import Any

from .distractors import is_placeholder_distractor, neutral_fallback_candidates

BLANK_SLOT_PLACEHOLDER = "______"
PAGE_STANDALONE_RE = re.compile(r"^\s*(?:第\s*)?([0-9]{1,2}|[一二三四五六七八九十]{1,3})(?:[.．、])?\s*$")
PAGE_PREFIX_RE = re.compile(r"^\s*(?:第\s*)?([0-9]{1,2}|[一二三四五六七八九十]{1,3})[.．、]\s+\S")
KNOWLEDGE_ITEM_PAGE_RE = re.compile(r"^\s*知识小题\s*(\d+)\s*[.．、]\s*\S")


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
    for candidate in neutral_fallback_candidates(index):
        key = candidate.casefold()
        if key not in used and key not in answer_keys:
            return candidate
    suffix = index
    while True:
        candidate = f"相关概念{suffix}"
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
            if cleaned and not is_placeholder_distractor(cleaned) and key not in answer_keys and key not in used_distractor_keys:
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
            safe_parts.append(f'<span class="blank-slot">{BLANK_SLOT_PLACEHOLDER}</span>')
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
        answer = html.escape(paragraph[start:end], quote=True)
        label = html.escape(f"第 {blank_number} 空", quote=True)
        safe_parts.append(html.escape(paragraph[cursor:start]))
        safe_parts.append(
            f'<span class="word-blank word-blank-drop" role="button" tabindex="0" '
            f'data-blank-id="{html.escape(blank_id, quote=True)}" data-answer="{answer}" title="{label}">'
            f'<span class="word-blank-number">{blank_number}</span>'
            f'<span class="word-blank-answer"></span>'
            f'<span class="word-blank-line">{BLANK_SLOT_PLACEHOLDER}</span>'
            f"</span>"
        )
        cursor = end
        used_until = end
    safe_parts.append(html.escape(paragraph[cursor:]))
    return "".join(safe_parts)


def _inline_image_html(image: dict[str, Any]) -> str:
    formula_text = str(image.get("formula_text") or "").strip()
    if formula_text:
        return _inline_formula_text_html(formula_text)
    if not image.get("renderable") or not image.get("data_uri"):
        return ""
    src = html.escape(str(image["data_uri"]), quote=True)
    alt_text = html.escape(str(image.get("alt_text") or image.get("filename") or "公式"))
    return f'<img class="inline-formula" src="{src}" alt="{alt_text}">'


def _inline_formula_text_html(formula_text: str) -> str:
    fraction_match = re.match(r"^([0-9A-Za-z]+)\s*/\s*([0-9A-Za-z]+)([^/]*)$", formula_text)
    if fraction_match:
        numerator, denominator, suffix = fraction_match.groups()
        return (
            '<span class="inline-formula-text">'
            '<span class="inline-formula-frac" '
            'style="display:inline-flex;flex-direction:column;align-items:center;justify-content:center;'
            'margin:0 .08em;vertical-align:middle;transform:translateY(-0.06em);line-height:.95;font-size:.82em;">'
            f'<span class="frac-top" style="display:block;border-bottom:1px solid currentColor;padding:0 .16em .035em;">{html.escape(numerator)}</span>'
            f'<span class="frac-bottom" style="display:block;padding:.035em .16em 0;">{html.escape(denominator)}</span>'
            "</span>"
            f"{html.escape(suffix)}"
            "</span>"
        )
    return f'<span class="inline-formula-text">{html.escape(formula_text)}</span>'


_SIMPLE_TEXT_FRACTION_RE = re.compile(r"(?<![0-9A-Za-z/])([0-9A-Za-z]+)\s*/\s*([0-9A-Za-z]+)(?![0-9A-Za-z/])")


def _plain_text_with_fractions_html(text: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in _SIMPLE_TEXT_FRACTION_RE.finditer(text):
        parts.append(html.escape(text[cursor : match.start()]))
        numerator, denominator = match.groups()
        parts.append(
            '<span class="inline-formula-text">'
            '<span class="inline-formula-frac" '
            'style="display:inline-flex;flex-direction:column;align-items:center;justify-content:center;'
            'margin:0 .08em;vertical-align:middle;transform:translateY(-0.06em);line-height:.95;font-size:.82em;">'
            f'<span class="frac-top" style="display:block;border-bottom:1px solid currentColor;padding:0 .16em .035em;">{html.escape(numerator)}</span>'
            f'<span class="frac-bottom" style="display:block;padding:.035em .16em 0;">{html.escape(denominator)}</span>'
            "</span>"
            "</span>"
        )
        cursor = match.end()
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def _inline_images_by_position(images: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    by_position: dict[int, list[dict[str, Any]]] = {}
    for image in images:
        if not image.get("inline"):
            continue
        try:
            char_index = int(image.get("char_index"))
        except (TypeError, ValueError):
            continue
        by_position.setdefault(char_index, []).append(image)
    return by_position


def _block_images(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [image for image in images if not image.get("inline")]


def _render_text_with_marks_and_inline_images(
    paragraph: str,
    marks: list[dict[str, Any]],
    inline_images: list[dict[str, Any]],
    *,
    blank_numbers: dict[str, int] | None = None,
) -> str:
    safe_parts: list[str] = []
    inline_by_position = _inline_images_by_position(inline_images)
    inline_positions = sorted(inline_by_position)

    def append_inline_at(position: int) -> None:
        for image in inline_by_position.get(position, []):
            safe_parts.append(_inline_image_html(image))

    def append_plain(start: int, end: int) -> None:
        cursor = start
        for position in inline_positions:
            if position < start or position > end:
                continue
            if position < cursor:
                continue
            safe_parts.append(_plain_text_with_fractions_html(paragraph[cursor:position]))
            append_inline_at(position)
            cursor = position
        safe_parts.append(_plain_text_with_fractions_html(paragraph[cursor:end]))

    cursor = 0
    used_until = -1
    for start, end, mark in _spans_for_marks(paragraph, marks):
        if start < used_until:
            continue
        append_plain(cursor, start)
        answer = _plain_text_with_fractions_html(paragraph[start:end])
        if blank_numbers is None:
            safe_parts.append(f'<span class="answer-mark">{answer}</span>')
        else:
            blank_id = str(mark.get("id", ""))
            blank_number = blank_numbers.get(blank_id, len(blank_numbers) + 1)
            label = html.escape(f"第 {blank_number} 空", quote=True)
            safe_parts.append(
                f'<span class="word-blank word-blank-drop" role="button" tabindex="0" '
                f'data-blank-id="{html.escape(blank_id, quote=True)}" data-answer="{html.escape(paragraph[start:end], quote=True)}" title="{label}">'
                f'<span class="word-blank-number">{blank_number}</span>'
                f'<span class="word-blank-answer"></span>'
                f'<span class="word-blank-line">{BLANK_SLOT_PLACEHOLDER}</span>'
                f"</span>"
            )
        cursor = end
        used_until = end
    append_plain(cursor, len(paragraph))
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
    images = _block_images(images)
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
        paragraph_images = images_by_paragraph.get(index, [])
        paragraph_html = (
            _render_text_with_marks_and_inline_images(paragraph, by_paragraph.get(index, []), paragraph_images)
            if paragraph
            else ""
        )
        image_html = image_group_html(paragraph_images)
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
        paragraph_images = images_by_paragraph.get(index, [])
        paragraph_html = (
            _render_text_with_marks_and_inline_images(
                paragraph,
                by_paragraph.get(index, []),
                paragraph_images,
                blank_numbers=blank_numbers,
            )
            if paragraph
            else ""
        )
        image_html = image_group_html(paragraph_images)
        if paragraph_html:
            rendered.append(f"<p>{paragraph_html}</p>{image_html}")
        elif image_html:
            rendered.append(image_html)
    return '<div class="fill-sheet">' + "\n".join(rendered) + "</div>"


def _page_label_for_paragraph(paragraph: str) -> str | None:
    stripped = str(paragraph or "").strip()
    if not stripped:
        return None
    knowledge_item = KNOWLEDGE_ITEM_PAGE_RE.match(stripped)
    if knowledge_item:
        return knowledge_item.group(1)
    standalone = PAGE_STANDALONE_RE.match(stripped)
    if standalone:
        return standalone.group(1)
    prefixed = PAGE_PREFIX_RE.match(stripped)
    if prefixed:
        return prefixed.group(1)
    return None


def _fill_page_groups(knowledge_paragraphs: list[str]) -> list[dict[str, Any]]:
    starts: list[tuple[int, str]] = []
    for index, paragraph in enumerate(knowledge_paragraphs):
        label = _page_label_for_paragraph(paragraph)
        if label:
            starts.append((index, label))

    if len(starts) <= 1:
        return [{"label": "1", "paragraph_indexes": list(range(len(knowledge_paragraphs)))}]

    if starts[0][0] > 0:
        starts[0] = (0, starts[0][1])

    pages: list[dict[str, Any]] = []
    for page_index, (start, label) in enumerate(starts):
        end = starts[page_index + 1][0] if page_index + 1 < len(starts) else len(knowledge_paragraphs)
        pages.append({"label": label, "paragraph_indexes": list(range(start, end))})
    return pages


def _fill_sheet_page_html(
    knowledge_paragraphs: list[str],
    blanks: list[dict[str, Any]],
    images: list[dict[str, Any]] | None,
    paragraph_indexes: list[int],
    blank_numbers: dict[str, int],
) -> str:
    by_paragraph = _group_by_paragraph(blanks)
    images_by_paragraph = _group_by_paragraph(images or [])

    rendered: list[str] = []
    for index in paragraph_indexes:
        if index < 0 or index >= len(knowledge_paragraphs):
            continue
        paragraph = knowledge_paragraphs[index]
        paragraph_images = images_by_paragraph.get(index, [])
        paragraph_html = (
            _render_text_with_marks_and_inline_images(
                paragraph,
                by_paragraph.get(index, []),
                paragraph_images,
                blank_numbers=blank_numbers,
            )
            if paragraph
            else ""
        )
        image_html = image_group_html(paragraph_images)
        if paragraph_html:
            rendered.append(f"<p>{paragraph_html}</p>{image_html}")
        elif image_html:
            rendered.append(image_html)
    return '<div class="fill-sheet">' + "\n".join(rendered) + "</div>"


def _renumber_word_bank(word_bank: list[dict[str, Any]]) -> list[dict[str, Any]]:
    renumbered: list[dict[str, Any]] = []
    for index, option in enumerate(word_bank, start=1):
        item = dict(option)
        item["number"] = index
        renumbered.append(item)
    return renumbered


def _page_nav_html(pages: list[dict[str, Any]]) -> str:
    if len(pages) <= 1:
        return ""
    labels = []
    for index, page in enumerate(pages):
        label = html.escape(str(page.get("label") or index + 1))
        labels.append(
            f'<span class="fill-page-number" data-page-target="{index}" aria-label="第 {label} 页">{label}</span>'
        )
    return '<nav class="fill-page-nav" aria-label="知识填空页码">' + "\n".join(labels) + "</nav>"


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
    course_cid: str = "",
) -> str:
    page_groups = _fill_page_groups(knowledge_paragraphs)
    blank_numbers = {str(blank.get("id", "")): index for index, blank in enumerate(blanks, start=1)}
    page_sections: list[str] = []
    bank_sections: list[str] = []
    for page_index, page in enumerate(page_groups):
        paragraph_indexes = page["paragraph_indexes"]
        paragraph_set = set(paragraph_indexes)
        page_blanks = [blank for blank in blanks if int(blank.get("paragraph_index", -1)) in paragraph_set]
        page_blank_ids = {str(blank.get("id", "")) for blank in page_blanks}
        page_word_bank = [option for option in word_bank if str(option.get("source_blank_id", "")) in page_blank_ids]
        active_class = " active" if page_index == 0 else ""
        page_sections.append(
            f'<section class="fill-page{active_class}" data-page-index="{page_index}">'
            + _fill_sheet_page_html(knowledge_paragraphs, page_blanks, images, paragraph_indexes, blank_numbers)
            + "</section>"
        )
        page_bank_html = word_bank_html(_renumber_word_bank(page_word_bank)) if page_word_bank else '<div class="word-bank word-bank-empty">本页暂无选词。</div>'
        bank_sections.append(
            f'<section class="word-bank-page{active_class}" data-page-index="{page_index}">{page_bank_html}</section>'
        )
    nav = _page_nav_html(page_groups)
    return f"""
<style>
  body {{
    margin: 0;
    font-family: "Microsoft YaHei", "SimSun", Arial, sans-serif;
    color: #2f261a;
    background: transparent;
  }}
  .fill-widget {{ padding: 0 1px 18px; }}
  .fill-page,
  .word-bank-page {{
    display: none;
  }}
  .fill-page.active,
  .word-bank-page.active {{
    display: block;
  }}
  .fill-sheet {{
    border: 1px solid #e6c98f;
    border-left: 6px solid #d5961e;
    border-radius: 8px;
    padding: 1.05rem 1.12rem .95rem;
    background: linear-gradient(180deg, #fffdf8, #fff8ea);
    box-shadow: 0 8px 18px rgba(111, 78, 32, .055), inset 0 1px 0 rgba(255, 255, 255, .88);
  }}
  .fill-sheet p {{
    font-size: 1rem;
    line-height: 2.16;
    margin: 0 0 .85rem;
  }}
  .word-blank {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: .26rem;
    width: 6.8rem;
    min-height: 1.65rem;
    margin: 0 .1rem;
    padding: 0 .35rem;
    border: 1px solid #d8b978;
    border-bottom: 2px solid #b86f00;
    border-radius: 6px 6px 4px 4px;
    background: #fffaf0;
    box-shadow: 0 1px 0 rgba(111, 78, 32, .05), inset 0 1px 0 rgba(255, 255, 255, .72);
    cursor: pointer;
    white-space: nowrap;
    transition: background .15s ease, border-color .15s ease, box-shadow .15s ease;
  }}
  .word-blank:hover {{
    border-color: #b86f00;
    box-shadow: 0 0 0 3px rgba(213, 150, 30, .18);
  }}
  .word-blank-number {{ color: #835108; font-size: .76rem; font-weight: 800; vertical-align: super; }}
  .word-blank-answer {{ color: #2f261a; font-weight: 800; min-width: 1rem; }}
  .word-blank-line {{ color: transparent; letter-spacing: .04rem; }}
  .word-blank.filled .word-blank-number {{ display: none; }}
  .word-blank.filled .word-blank-line {{ display: none; }}
  .word-blank.filled {{ width: auto; min-width: 6.8rem; }}
  .word-blank.correct {{ background: #e8f7ed; border-color: #49a36f; border-bottom-color: #278653; }}
  .word-blank.wrong {{ background: #fff0ef; border-color: #d36b62; border-bottom-color: #bd4a43; }}
  .word-blank.unfilled {{ background: #fff6db; border-color: #dba74c; border-bottom-color: #b86f00; }}
  .word-bank-title {{
    margin: 1.08rem 0 .58rem;
    color: #3a2a13;
    font-weight: 800;
  }}
  .fill-page-nav {{
    display: flex;
    align-items: center;
    gap: .3rem;
    margin: .9rem 0 .2rem;
    padding: .15rem 0 .2rem;
  }}
  .fill-page-number {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 2.4rem;
    border: 0;
    border-bottom: 3px solid transparent;
    padding: .5rem .56rem .45rem;
    background: transparent;
    color: #6f5a36;
    font-weight: 700;
  }}
  .fill-page-number.active {{
    color: #2f261a;
    border-bottom-color: #3a2a13;
  }}
  .word-bank {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(156px, 1fr));
    gap: .65rem .75rem;
    padding: .95rem;
    border: 1px solid #e6c98f;
    border-radius: 8px;
    background: linear-gradient(180deg, #fffdf8, #fff8ea);
    box-shadow: 0 8px 18px rgba(111, 78, 32, .055), inset 0 1px 0 rgba(255, 255, 255, .88);
  }}
  .word-bank-item {{
    display: flex;
    align-items: center;
    gap: .5rem;
    min-height: 2.4rem;
    padding: .42rem .55rem;
    border: 1px solid #e2c486;
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
    background: #fff4d8;
    box-shadow: 0 6px 14px rgba(111, 78, 32, .085);
  }}
  .word-bank-item.selected {{ border-color: #b86f00; background: #fff0bf; box-shadow: 0 0 0 3px rgba(213, 150, 30, .18); }}
  .word-bank-item.used {{ opacity: .42; cursor: not-allowed; }}
  .word-bank-item.used:hover {{ transform: none; box-shadow: none; }}
  .word-bank-number {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 1.55rem;
    height: 1.55rem;
    border-radius: 999px;
    background: #fff0bf;
    color: #835108;
    font-weight: 800;
    font-size: .82rem;
  }}
  .word-bank-text {{ line-height: 1.45; }}
  .word-bank-empty {{
    display: block;
    color: #8f7446;
    font-weight: 700;
  }}
  .fill-actions {{ display: flex; gap: .82rem; align-items: center; flex-wrap: wrap; margin-top: .95rem; }}
  .fill-actions button {{
    border: 1px solid #dfc286;
    border-radius: 7px;
    padding: .52rem .92rem;
    background: #fffdf8;
    color: #2f261a;
    font-weight: 800;
    cursor: pointer;
  }}
  .fill-actions .primary {{ background: #b86f00; border-color: #b86f00; color: #fff; }}
  .fill-actions .hidden {{ display: none; }}
  .fill-action-link {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid #b86f00;
    border-radius: 7px;
    padding: .52rem .92rem;
    background: #b86f00;
    color: #fff;
    font-weight: 800;
    text-decoration: none;
  }}
  .fill-actions button:hover {{ border-color: #b86f00; }}
  .fill-result {{ font-weight: 800; color: #3a2a13; }}
  .course-images {{ display: flex; flex-wrap: wrap; gap: .9rem; margin: .6rem 0 1.1rem; }}
  .course-image-wrap {{ margin: 0; }}
  .course-image {{
    display: block;
    max-height: 420px;
    object-fit: contain;
    border: 1px solid #e4c78b;
    border-radius: 8px;
    background: #fffdf8;
    padding: .5rem;
    box-shadow: 0 9px 20px rgba(111, 78, 32, .075);
  }}
  .course-image-placeholder {{
    border: 1px dashed #c8a76a;
    border-radius: 8px;
    background: #fffaf0;
    color: #735f43;
    padding: .75rem .9rem;
    font-size: .92rem;
  }}
  .inline-formula {{
    display: inline-block;
    height: 1.45em;
    max-width: 10em;
    margin: 0 .08rem;
    vertical-align: -0.35em;
    object-fit: contain;
  }}
  .inline-formula-text {{
    display: inline;
    margin: 0 .08rem;
    font-family: "Times New Roman", "Cambria Math", serif;
    font-size: 1em;
    color: #3f2a0b;
    white-space: nowrap;
  }}
  .inline-formula-frac {{
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    margin: 0 .08em;
    vertical-align: middle;
    transform: translateY(-0.06em);
    line-height: .95;
    font-size: .82em;
  }}
  .inline-formula-frac .frac-top {{
    display: block;
    border-bottom: 1px solid currentColor;
    padding: 0 .16em .035em;
  }}
  .inline-formula-frac .frac-bottom {{
    display: block;
    padding: .035em .16em 0;
  }}
  @media (max-width: 640px) {{
    .fill-sheet {{ padding: .85rem .75rem; }}
    .fill-sheet p {{ line-height: 2.05; }}
    .word-bank {{ grid-template-columns: 1fr; }}
    .word-blank {{ min-width: 4rem; }}
  }}
</style>
<div class="fill-widget">
  <div class="fill-pages">
    {"".join(page_sections)}
  </div>
  <div class="word-bank-title">选词库</div>
  <div class="word-bank-pages">
    {"".join(bank_sections)}
  </div>
  {nav}
  <div class="fill-actions">
    <button class="primary" type="button" id="checkAnswers">提交检查</button>
    <button class="primary hidden" type="button" id="goNextPage">下一页</button>
    <button class="primary hidden" type="button" id="enterPractice">进入快速练习</button>
    <button type="button" id="resetAnswers">重做</button>
    <span class="fill-result" id="fillResult"></span>
  </div>
</div>
<script>
(() => {{
  const options = Array.from(document.querySelectorAll(".word-bank-item"));
  const blanks = Array.from(document.querySelectorAll(".word-blank-drop"));
  const fillPages = Array.from(document.querySelectorAll(".fill-page"));
  const bankPages = Array.from(document.querySelectorAll(".word-bank-page"));
  const pageButtons = Array.from(document.querySelectorAll("[data-page-target]"));
  const resultEl = document.getElementById("fillResult");
  const checkButton = document.getElementById("checkAnswers");
  const resetButton = document.getElementById("resetAnswers");
  const nextPageButton = document.getElementById("goNextPage");
  const enterPracticeButton = document.getElementById("enterPractice");
  let currentPage = 0;
  let selectedOptionId = null;

  function requestResize() {{
    if (typeof window.requestFillResize === "function") {{
      window.requestFillResize();
    }}
  }}

  function activeBlanks() {{
    const activePage = fillPages[currentPage];
    if (!activePage) return blanks;
    return Array.from(activePage.querySelectorAll(".word-blank-drop"));
  }}

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

  function showPage(pageIndex) {{
    if (!fillPages.length) return;
    currentPage = Math.max(0, Math.min(pageIndex, fillPages.length - 1));
    fillPages.forEach((page, index) => page.classList.toggle("active", index === currentPage));
    bankPages.forEach((page, index) => page.classList.toggle("active", index === currentPage));
    pageButtons.forEach(button => {{
      const active = Number(button.dataset.pageTarget) === currentPage;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    }});
    if (checkButton) checkButton.classList.remove("hidden");
    if (nextPageButton) nextPageButton.classList.add("hidden");
    if (enterPracticeButton) enterPracticeButton.classList.add("hidden");
    setSelected(null);
    if (resultEl) resultEl.textContent = "";
    requestResize();
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

  showPage(0);

  if (nextPageButton) {{
    nextPageButton.addEventListener("click", () => showPage(currentPage + 1));
  }}

  if (enterPracticeButton) {{
    enterPracticeButton.addEventListener("click", () => {{
      if (typeof window.notifyPracticeReady === "function") {{
        window.notifyPracticeReady();
      }}
    }});
  }}

  function collectState() {{
    return {{
      pageIndex: currentPage,
      blanks: blanks.map(blank => ({{
        blankId: blank.dataset.blankId || "",
        optionId: blank.dataset.optionId || "",
        answerText: blank.querySelector(".word-blank-answer")?.textContent || "",
        classes: Array.from(blank.classList).filter(name =>
          ["filled", "correct", "wrong", "unfilled"].includes(name)
        ),
      }})),
      buttons: {{
        checkAnswers: checkButton ? checkButton.classList.contains("hidden") : false,
        goNextPage: nextPageButton ? nextPageButton.classList.contains("hidden") : true,
        enterPractice: enterPracticeButton ? enterPracticeButton.classList.contains("hidden") : true,
      }},
      resultText: resultEl ? resultEl.textContent || "" : "",
    }};
  }}

  function restoreState(state) {{
    if (!state) return;
    showPage(Number(state.pageIndex) || 0);
    options.forEach(option => option.classList.remove("used", "selected"));
    (state.blanks || []).forEach(saved => {{
      const blank = blanks.find(item => item.dataset.blankId === saved.blankId);
      if (!blank) return;
      blank.dataset.optionId = saved.optionId || "";
      blank.classList.remove("filled", "correct", "wrong", "unfilled");
      (saved.classes || []).forEach(name => blank.classList.add(name));
      const answer = blank.querySelector(".word-blank-answer");
      if (answer) answer.textContent = saved.answerText || "";
      if (saved.optionId) {{
        const option = optionById(saved.optionId);
        if (option) option.classList.add("used");
      }}
    }});
    if (checkButton && state.buttons) checkButton.classList.toggle("hidden", Boolean(state.buttons.checkAnswers));
    if (nextPageButton && state.buttons) nextPageButton.classList.toggle("hidden", Boolean(state.buttons.goNextPage));
    if (enterPracticeButton && state.buttons) enterPracticeButton.classList.toggle("hidden", Boolean(state.buttons.enterPractice));
    if (resultEl) resultEl.textContent = state.resultText || "";
    requestResize();
  }}

  window.__fillWidgetApi = {{ collectState, restoreState }};

  checkButton.addEventListener("click", () => {{
    let score = 0;
    const pageBlanks = activeBlanks();
    pageBlanks.forEach(blank => {{
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
    const total = pageBlanks.length;
    const accuracy = total ? score / total : 1;
    const percent = Math.round(accuracy * 100);
    const passed = accuracy >= 0.6;
    if (resultEl) {{
      resultEl.textContent = passed
        ? `本页正确率：${{percent}}%（${{score}}/${{total}}），已达标`
        : `本页正确率：${{percent}}%（${{score}}/${{total}}），未达标，请重做`;
    }}
    checkButton.classList.add("hidden");
    if (passed) {{
      if (currentPage >= fillPages.length - 1) {{
        if (enterPracticeButton) enterPracticeButton.classList.remove("hidden");
      }} else if (nextPageButton) {{
        nextPageButton.classList.remove("hidden");
      }}
    }}
    requestResize();
  }});

  resetButton.addEventListener("click", () => {{
    activeBlanks().forEach(clearBlank);
    options.forEach(option => option.classList.remove("selected"));
    selectedOptionId = null;
    if (checkButton) checkButton.classList.remove("hidden");
    if (nextPageButton) nextPageButton.classList.add("hidden");
    if (enterPracticeButton) enterPracticeButton.classList.add("hidden");
    if (resultEl) resultEl.textContent = "";
    requestResize();
  }});

  if (window.__fillSavedState) {{
    restoreState(window.__fillSavedState);
    window.__fillSavedState = null;
  }}
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
    paragraph_images = [image for image in images or [] if int(image.get("paragraph_index", -1)) == paragraph_index]
    rendered = _render_text_with_marks_and_inline_images(
        paragraph,
        [blank],
        paragraph_images,
        blank_numbers={str(blank.get("id", "")): 1},
    )
    return f'<div class="blank-prompt"><p>{rendered}</p>{image_group_html(paragraph_images)}</div>'

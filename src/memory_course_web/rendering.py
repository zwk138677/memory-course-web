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


def course_id(payload: dict[str, Any]) -> str:
    basis = payload.get("title", "") + "\n" + "\n".join(payload.get("knowledge_paragraphs", []))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def _apply_marks(paragraph: str, marks: list[dict[str, Any]], *, blank_current: bool = False) -> str:
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

    safe_parts: list[str] = []
    cursor = 0
    used_until = -1
    for start, end, mark in spans:
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
                f'<strong>已识别配图</strong><br>{filename}<br><span>{mime_type} 暂不支持网页直接预览</span>'
                f"</div>"
            )
    return '<div class="course-images">' + "\n".join(rendered) + "</div>"


def knowledge_html(
    knowledge_paragraphs: list[str],
    blanks: list[dict[str, Any]],
    images: list[dict[str, Any]] | None = None,
) -> str:
    by_paragraph: dict[int, list[dict[str, Any]]] = {}
    for blank in blanks:
        by_paragraph.setdefault(int(blank["paragraph_index"]), []).append(blank)
    images_by_paragraph: dict[int, list[dict[str, Any]]] = {}
    for image in images or []:
        try:
            paragraph_index = int(image["paragraph_index"])
        except (KeyError, TypeError, ValueError):
            continue
        images_by_paragraph.setdefault(paragraph_index, []).append(image)

    rendered: list[str] = []
    for index, paragraph in enumerate(knowledge_paragraphs):
        paragraph_html = _apply_marks(paragraph, by_paragraph.get(index, [])) if paragraph else ""
        image_html = image_group_html(images_by_paragraph.get(index, []))
        if paragraph_html:
            rendered.append(f"<p>{paragraph_html}</p>{image_html}")
        elif image_html:
            rendered.append(image_html)
    return '<div class="knowledge-body">' + "\n".join(rendered) + "</div>"


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

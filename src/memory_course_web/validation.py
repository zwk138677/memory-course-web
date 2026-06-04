"""Validation helpers for parsed finished-course payloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class PayloadValidationError(ValueError):
    """Raised when parsed/generated data cannot safely drive the learning UI."""


def split_paragraphs(knowledge_text: str) -> list[str]:
    return [line.strip() for line in knowledge_text.splitlines() if line.strip()]


def clean_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise PayloadValidationError(f"{field_name} 必须是字符串。")
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        raise PayloadValidationError(f"{field_name} 不能为空。")
    return cleaned


def optional_text(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise PayloadValidationError(f"{field_name} 必须是字符串。")
    return value.strip()


def _normalize_images(images: Any, field_name: str) -> list[dict[str, Any]]:
    if images is None:
        return []
    if not isinstance(images, list):
        raise PayloadValidationError(f"{field_name} 必须是数组。")

    normalized: list[dict[str, Any]] = []
    for index, image in enumerate(images, start=1):
        if not isinstance(image, dict):
            raise PayloadValidationError(f"{field_name} 第 {index} 张图片必须是对象。")
        filename = optional_text(image.get("filename"), f"{field_name} 第 {index} 张图片文件名")
        mime_type = optional_text(image.get("mime_type"), f"{field_name} 第 {index} 张图片格式")
        data_uri = optional_text(image.get("data_uri"), f"{field_name} 第 {index} 张图片数据")
        formula_text = optional_text(image.get("formula_text"), f"{field_name} formula text")
        renderable = bool((image.get("renderable") and data_uri) or formula_text)
        if renderable and not data_uri.startswith("data:image/"):
            if not formula_text:
                raise PayloadValidationError(f"{field_name} 第 {index} 张图片数据格式不正确。")
        normalized.append(
            {
                "id": optional_text(image.get("id"), f"{field_name} 第 {index} 张图片 ID") or f"img{index:03d}",
                "filename": filename,
                "mime_type": mime_type,
                "data_uri": data_uri,
                "renderable": renderable,
                "alt_text": optional_text(image.get("alt_text"), f"{field_name} 第 {index} 张图片说明"),
                "width_px": image.get("width_px"),
                "height_px": image.get("height_px"),
                "inline": bool(image.get("inline")),
                "char_index": image.get("char_index"),
                "kind": optional_text(image.get("kind"), f"{field_name} image kind"),
                "formula_text": formula_text,
            }
        )
    return normalized


def validate_distractor_list(answer: str, distractors: Any, field_name: str) -> list[str]:
    if not isinstance(distractors, list) or len(distractors) != 3:
        raise PayloadValidationError(f"{field_name} 必须包含 3 个干扰项。")
    cleaned = [clean_text(item, field_name) for item in distractors]
    keys = {answer.strip().casefold()}
    for item in cleaned:
        key = item.casefold()
        if key in keys:
            raise PayloadValidationError(f"{field_name} 的干扰项必须和答案互不相同。")
        keys.add(key)
    if len(keys) != 4:
        raise PayloadValidationError(f"{field_name} 的 3 个干扰项必须互不重复。")
    return cleaned


def validate_blank_distractor_list(answer: str, distractors: Any, field_name: str) -> list[str]:
    if not isinstance(distractors, list) or not distractors:
        raise PayloadValidationError(f"{field_name} 必须至少包含 1 个干扰项。")
    cleaned = [clean_text(item, field_name) for item in distractors]
    keys = {answer.strip().casefold()}
    for item in cleaned:
        key = item.casefold()
        if key in keys:
            raise PayloadValidationError(f"{field_name} 的干扰项必须和答案互不相同。")
        keys.add(key)
    if len(keys) != len(cleaned) + 1:
        raise PayloadValidationError(f"{field_name} 的干扰项必须互不重复。")
    return cleaned


def validate_finished_course_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PayloadValidationError("课程数据必须是对象。")

    normalized = deepcopy(payload)
    normalized["title"] = clean_text(payload.get("title", "讲义背记课"), "title")

    paragraphs = payload.get("knowledge_paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        raise PayloadValidationError("knowledge_paragraphs 必须是非空数组。")
    normalized["knowledge_paragraphs"] = [optional_text(item, "知识段落") for item in paragraphs]
    if not any(item.strip() for item in normalized["knowledge_paragraphs"]):
        raise PayloadValidationError("knowledge_paragraphs 不能全部为空。")
    normalized["knowledge_text"] = "\n".join(normalized["knowledge_paragraphs"])

    raw_knowledge_images = payload.get("knowledge_images", [])
    knowledge_images = _normalize_images(raw_knowledge_images, "知识配图")
    normalized_knowledge_images: list[dict[str, Any]] = []
    for index, image in enumerate(knowledge_images, start=1):
        try:
            paragraph_index = int(raw_knowledge_images[index - 1].get("paragraph_index"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise PayloadValidationError(f"知识配图第 {index} 张缺少有效段落位置。") from exc
        if paragraph_index < 0 or paragraph_index >= len(normalized["knowledge_paragraphs"]):
            raise PayloadValidationError(f"知识配图第 {index} 张段落位置越界。")
        if image.get("inline"):
            try:
                char_index = int(image.get("char_index"))
            except (TypeError, ValueError) as exc:
                raise PayloadValidationError(f"知识配图第 {index} 张缺少有效行内位置。") from exc
            paragraph = normalized["knowledge_paragraphs"][paragraph_index]
            if char_index < 0 or char_index > len(paragraph):
                raise PayloadValidationError(f"知识配图第 {index} 张行内位置越界。")
            image["char_index"] = char_index
        else:
            image["char_index"] = None
        image["paragraph_index"] = paragraph_index
        normalized_knowledge_images.append(image)
    normalized["knowledge_images"] = normalized_knowledge_images

    blanks = payload.get("blanks", [])
    if not isinstance(blanks, list):
        raise PayloadValidationError("blanks 必须是数组。")
    normalized_blanks: list[dict[str, Any]] = []
    seen_locations: set[tuple[int, int, int]] = set()
    for index, blank in enumerate(blanks, start=1):
        if not isinstance(blank, dict):
            raise PayloadValidationError(f"第 {index} 个填空项必须是对象。")
        answer = clean_text(blank.get("answer"), f"第 {index} 个填空答案")
        try:
            paragraph_index = int(blank.get("paragraph_index"))
            start = int(blank.get("start"))
            end = int(blank.get("end"))
        except (TypeError, ValueError) as exc:
            raise PayloadValidationError(f"第 {index} 个填空项缺少有效位置。") from exc
        if paragraph_index < 0 or paragraph_index >= len(normalized["knowledge_paragraphs"]):
            raise PayloadValidationError(f"第 {index} 个填空项段落位置越界。")
        paragraph = normalized["knowledge_paragraphs"][paragraph_index]
        if start < 0 or end <= start or end > len(paragraph):
            raise PayloadValidationError(f"第 {index} 个填空项字符范围越界。")
        if paragraph[start:end] != answer:
            raise PayloadValidationError(f"第 {index} 个填空项答案和正文位置不一致。")
        location = (paragraph_index, start, end)
        if location in seen_locations:
            raise PayloadValidationError(f"第 {index} 个填空项位置重复。")
        seen_locations.add(location)
        distractors = blank.get("distractors", [])
        source = str(blank.get("distractor_source", "")).strip()
        if distractors:
            distractors = validate_blank_distractor_list(answer, distractors, f"第 {index} 个填空干扰项")
        normalized_blanks.append(
            {
                "id": str(blank.get("id") or f"b{index:03d}"),
                "answer": answer,
                "paragraph_index": paragraph_index,
                "start": start,
                "end": end,
                "distractors": distractors,
                "distractor_source": source,
            }
        )
    normalized["blanks"] = normalized_blanks

    questions = payload.get("quick_practice")
    if not isinstance(questions, list) or not questions:
        raise PayloadValidationError("quick_practice 必须是非空数组。")
    normalized_questions: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise PayloadValidationError(f"第 {index} 道快速练习必须是对象。")
        stem = clean_text(question.get("stem"), f"第 {index} 题题干")
        correct = clean_text(question.get("correct"), f"第 {index} 题正确选项")
        wrong = validate_distractor_list(correct, question.get("wrong"), f"第 {index} 题错误选项")
        normalized_questions.append(
            {
                "category": optional_text(question.get("category"), f"第 {index} 题分类"),
                "stem": stem,
                "correct": correct,
                "wrong": wrong,
                "source": optional_text(question.get("source"), f"第 {index} 题来源"),
                "analysis": optional_text(question.get("analysis"), f"第 {index} 题解析"),
                "images": _normalize_images(question.get("images", []), f"第 {index} 题配图"),
            }
        )
    normalized["quick_practice"] = normalized_questions
    return normalized

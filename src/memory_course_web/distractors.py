"""Code fallback distractor generation for fill-in blanks."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from .validation import validate_distractor_list


GENERIC_DISTRACTORS = [
    "相反数",
    "倒数",
    "平方",
    "平方根",
    "对应边",
    "对应角",
    "定义",
    "性质",
    "条件",
    "结论",
    "增大",
    "减小",
    "不变",
    "无法确定",
    "第一象限",
    "第二象限",
    "第三象限",
    "第四象限",
]


def _unique(values: list[str], answer: str) -> list[str]:
    seen = {answer.strip().casefold()}
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value).split()).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def _candidate_score(answer: str, candidate: str) -> float:
    length_delta = abs(len(answer) - len(candidate)) / max(len(answer), len(candidate), 1)
    similarity = SequenceMatcher(None, answer, candidate).ratio()
    return similarity - length_delta * 0.25


def _variants(answer: str) -> list[str]:
    if len(answer) <= 1:
        return [f"非{answer}", f"{answer}的相反项", f"{answer}的倒数"]
    return [
        f"非{answer}",
        f"{answer}的相反数",
        f"{answer}的倒数",
        answer.replace("增大", "减小"),
        answer.replace("减小", "增大"),
        answer.replace("相等", "不相等"),
        answer.replace("对应", "公共"),
    ]


def fallback_distractors_for_blank(blank: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    answer = str(blank["answer"]).strip()
    pool: list[str] = []
    for other in payload.get("blanks", []):
        pool.append(str(other.get("answer", "")))
    for question in payload.get("quick_practice", []):
        pool.append(str(question.get("correct", "")))
        pool.extend(str(item) for item in question.get("wrong", []))
    pool.extend(_variants(answer))
    pool.extend(GENERIC_DISTRACTORS)

    candidates = _unique(pool, answer)
    candidates.sort(key=lambda item: _candidate_score(answer, item), reverse=True)
    selected = candidates[:3]
    while len(selected) < 3:
        selected.append(f"干扰项{len(selected) + 1}")
    return validate_distractor_list(answer, selected[:3], "代码兜底干扰项")


def apply_fallback_distractors(payload: dict[str, Any], *, only_missing: bool = True) -> dict[str, Any]:
    for blank in payload.get("blanks", []):
        if only_missing and blank.get("distractors") and len(blank["distractors"]) == 3:
            continue
        blank["distractors"] = fallback_distractors_for_blank(blank, payload)
        blank["distractor_source"] = "代码兜底"
    return payload

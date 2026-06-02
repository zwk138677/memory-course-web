"""Code fallback distractor generation for fill-in blanks."""

from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

from .validation import validate_distractor_list

PLACEHOLDER_DISTRACTOR_RE = re.compile(r"^\s*(?:干扰项|\?{2,}|�{2,})\s*\d+\s*$")


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

NEUTRAL_FALLBACK_DISTRACTORS = [
    "基本定义",
    "核心性质",
    "适用条件",
    "主要结论",
    "数量关系",
    "位置关系",
    "对应关系",
    "度数关系",
    "图形关系",
    "相等关系",
    "大小关系",
    "和差关系",
    "倍数关系",
    "边角关系",
    "表示方法",
    "判定方法",
    "分类标准",
    "变化规律",
    "取值范围",
    "计算方法",
    "公共元素",
    "特殊情况",
    "一般情况",
    "必要条件",
    "充分条件",
    "已知条件",
    "目标结论",
    "几何关系",
    "代数关系",
    "基本图形",
    "辅助结论",
    "常见性质",
    "易混概念",
    "相关概念",
    "对应元素",
    "单位关系",
]


def is_placeholder_distractor(value: str) -> bool:
    return bool(PLACEHOLDER_DISTRACTOR_RE.match(str(value)))


def neutral_fallback_candidates(start_index: int = 1) -> list[str]:
    if not NEUTRAL_FALLBACK_DISTRACTORS:
        return []
    start = max(0, start_index - 1) % len(NEUTRAL_FALLBACK_DISTRACTORS)
    return NEUTRAL_FALLBACK_DISTRACTORS[start:] + NEUTRAL_FALLBACK_DISTRACTORS[:start]


def _unique(values: list[str], answer: str) -> list[str]:
    seen = {answer.strip().casefold()}
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value).split()).strip()
        if not cleaned:
            continue
        if is_placeholder_distractor(cleaned):
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
    pool.extend(neutral_fallback_candidates())

    candidates = _unique(pool, answer)
    candidates.sort(key=lambda item: _candidate_score(answer, item), reverse=True)
    selected = candidates[:3]
    selected_keys = {item.casefold() for item in selected}
    for candidate in neutral_fallback_candidates():
        cleaned = " ".join(candidate.split()).strip()
        key = cleaned.casefold()
        if key != answer.casefold() and key not in selected_keys:
            selected.append(cleaned)
            selected_keys.add(key)
        if len(selected) >= 3:
            break
    return validate_distractor_list(answer, selected[:3], "代码兜底干扰项")


def apply_fallback_distractors(payload: dict[str, Any], *, only_missing: bool = True) -> dict[str, Any]:
    for blank in payload.get("blanks", []):
        if only_missing and blank.get("distractors") and len(blank["distractors"]) == 3:
            continue
        blank["distractors"] = fallback_distractors_for_blank(blank, payload)
        blank["distractor_source"] = "代码兜底"
    return payload

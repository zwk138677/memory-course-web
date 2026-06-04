"""DeepSeek generation for word-bank fill-in distractors."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import json
import time
from typing import Any, Callable

from openai import OpenAI

from .distractors import fallback_distractors_for_blank, is_placeholder_distractor, neutral_fallback_candidates
from .validation import PayloadValidationError, clean_text, validate_finished_course_payload


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    max_tokens: int = 6000
    temperature: float = 0.2
    timeout_seconds: float = 60.0
    thinking: str = "enabled"
    reasoning_effort: str = "high"


ProgressCallback = Callable[[dict[str, Any]], None]


SYSTEM_PROMPT = """你是一名严谨的初中数学教研老师。你只输出合法 JSON，不输出 Markdown。
任务：为知识填空的选词库生成干扰项。
要求：
1. 每个 id 必须返回且只返回 1 个 distractor。
2. distractor 不能等于本空 answer，也不能等于其他空的正确答案。
3. distractor 之间不能重复。
4. 干扰项应像学生常见误选词，风格贴近初中数学教材。
5. 不要改写 answer，不要生成题干，不要生成快速练习。
输出格式：{"items":[{"id":"b001","distractor":"..."}]}。"""


def _chunked(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _context_for_blank(payload: dict[str, Any], blank: dict[str, Any]) -> str:
    paragraphs = payload["knowledge_paragraphs"]
    index = int(blank["paragraph_index"])
    start = max(0, index - 1)
    end = min(len(paragraphs), index + 2)
    return "\n".join(paragraphs[start:end])


def _user_prompt(payload: dict[str, Any], blanks: list[dict[str, Any]]) -> str:
    items = [
        {
            "id": blank["id"],
            "answer": blank["answer"],
            "context": _context_for_blank(payload, blank),
        }
        for blank in blanks
    ]
    return json.dumps({"items": items}, ensure_ascii=False, indent=2)


def _parse_json(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise PayloadValidationError(f"DeepSeek 返回的内容不是合法 JSON：{exc}") from exc
    if not isinstance(parsed, dict):
        raise PayloadValidationError("DeepSeek 返回 JSON 顶层必须是对象。")
    return parsed


def _new_diagnostics(total_blanks: int, batch_size: int) -> dict[str, Any]:
    return {
        "total_blanks": total_blanks,
        "batch_size": batch_size,
        "batches": 0,
        "elapsed_seconds": 0.0,
        "failures": [],
        "failure_summary": {},
    }


def _failure_category(reason: str) -> str:
    if "空内容" in reason:
        return "空返回"
    if "缺少" in reason:
        return "缺项"
    if "无效" in reason or "占位符" in reason or "重复" in reason:
        return "无效项"
    if "JSON" in reason:
        return "格式错误"
    if "未配置" in reason:
        return "未配置"
    return "请求失败"


def _add_failure(
    diagnostics: dict[str, Any],
    *,
    batch_number: int,
    attempt: int,
    reason: str,
    count: int = 1,
) -> None:
    diagnostics["failures"].append(
        {
            "batch": batch_number,
            "attempt": attempt,
            "reason": reason,
            "count": count,
        }
    )
    category = _failure_category(reason)
    summary = diagnostics.setdefault("failure_summary", {})
    summary[category] = int(summary.get(category, 0)) + count


def _answer_keys(payload: dict[str, Any]) -> set[str]:
    return {str(blank.get("answer", "")).strip().casefold() for blank in payload.get("blanks", [])}


def _valid_single_distractor(value: Any, answer: str, answer_keys: set[str], used: set[str]) -> str | None:
    try:
        cleaned = clean_text(value, "填空干扰项")
    except Exception:
        return None
    key = cleaned.casefold()
    if is_placeholder_distractor(cleaned):
        return None
    if key == answer.strip().casefold() or key in answer_keys or key in used:
        return None
    return cleaned


def _fallback_candidate(blank: dict[str, Any], payload: dict[str, Any], answer_keys: set[str], used: set[str], index: int) -> str:
    answer = str(blank["answer"])
    for candidate in fallback_distractors_for_blank(blank, payload):
        cleaned = _valid_single_distractor(candidate, answer, answer_keys, used)
        if cleaned:
            return cleaned
    for candidate in neutral_fallback_candidates(index):
        cleaned = _valid_single_distractor(candidate, answer, answer_keys, used)
        if cleaned:
            return cleaned
    suffix = index
    while True:
        candidate = f"相关概念{suffix}"
        cleaned = _valid_single_distractor(candidate, answer, answer_keys, used)
        if cleaned:
            return cleaned
        suffix += 1


def _generate_batch(
    *,
    payload: dict[str, Any],
    blanks: list[dict[str, Any]],
    client: OpenAI,
    config: DeepSeekConfig,
) -> dict[str, str]:
    response = client.chat.completions.create(
        model=config.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(payload, blanks)},
        ],
        response_format={"type": "json_object"},
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        reasoning_effort=config.reasoning_effort,
        extra_body={"thinking": {"type": config.thinking}},
    )
    content = response.choices[0].message.content or ""
    if not content.strip():
        raise PayloadValidationError("DeepSeek 返回了空内容。")

    parsed = _parse_json(content)
    items = parsed.get("items")
    if not isinstance(items, list):
        raise PayloadValidationError("DeepSeek 返回 JSON 缺少 items 数组。")

    blank_ids = {blank["id"] for blank in blanks}
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", ""))
        if item_id not in blank_ids:
            continue
        value = item.get("distractor")
        if value is None and isinstance(item.get("distractors"), list) and item["distractors"]:
            value = item["distractors"][0]
        result[item_id] = str(value or "").strip()
    return result


def _set_blank_distractor(blank: dict[str, Any], distractor: str, source: str, used: set[str]) -> None:
    blank["distractors"] = [distractor]
    blank["distractor_source"] = source
    used.add(distractor.casefold())


def generate_blank_distractors(
    payload: dict[str, Any],
    config: DeepSeekConfig,
    *,
    batch_size: int = 8,
    max_attempts: int = 2,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Attach one globally valid word-bank distractor to each parsed blank."""

    started_at = time.perf_counter()
    result = validate_finished_course_payload(deepcopy(payload))
    blanks = result.get("blanks", [])
    diagnostics = _new_diagnostics(len(blanks), max(1, batch_size))
    if not blanks:
        result["distractor_summary"] = {}
        result["distractor_diagnostics"] = diagnostics
        return result

    answer_keys = _answer_keys(result)
    used_distractors: set[str] = set()

    if not config.api_key:
        _add_failure(
            diagnostics,
            batch_number=0,
            attempt=0,
            reason="未配置 DeepSeek Key，全部使用代码兜底。",
            count=len(blanks),
        )
        for index, blank in enumerate(blanks, start=1):
            distractor = _fallback_candidate(blank, result, answer_keys, used_distractors, index)
            _set_blank_distractor(blank, distractor, "代码兜底", used_distractors)
        result["distractor_summary"] = {"代码兜底": len(blanks)}
        diagnostics["elapsed_seconds"] = round(time.perf_counter() - started_at, 2)
        result["distractor_diagnostics"] = diagnostics
        return validate_finished_course_payload(result)

    batches = _chunked(blanks, max(1, batch_size))
    diagnostics["batches"] = len(batches)
    client = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=config.timeout_seconds)

    for batch_number, batch in enumerate(batches, start=1):
        unresolved = list(batch)
        for attempt in range(1, max(1, max_attempts) + 1):
            if not unresolved:
                break
            if progress_callback:
                progress_callback(
                    {
                        "batch": batch_number,
                        "batches": len(batches),
                        "attempt": attempt,
                        "pending": len(unresolved),
                        "total_blanks": len(blanks),
                    }
                )

            try:
                generated = _generate_batch(payload=result, blanks=unresolved, client=client, config=config)
            except Exception as exc:
                _add_failure(
                    diagnostics,
                    batch_number=batch_number,
                    attempt=attempt,
                    reason=str(exc) or type(exc).__name__,
                    count=1,
                )
                continue

            remaining: list[dict[str, Any]] = []
            missing_count = 0
            invalid_count = 0
            source = "DeepSeek" if attempt == 1 else "DeepSeek重试"
            for blank in unresolved:
                if blank["id"] not in generated:
                    missing_count += 1
                    remaining.append(blank)
                    continue
                distractor = _valid_single_distractor(
                    generated.get(blank["id"], ""),
                    str(blank["answer"]),
                    answer_keys,
                    used_distractors,
                )
                if not distractor:
                    invalid_count += 1
                    remaining.append(blank)
                    continue
                _set_blank_distractor(blank, distractor, source, used_distractors)

            if missing_count:
                _add_failure(
                    diagnostics,
                    batch_number=batch_number,
                    attempt=attempt,
                    reason=f"DeepSeek 返回缺少 {missing_count} 个填空项。",
                    count=missing_count,
                )
            if invalid_count:
                _add_failure(
                    diagnostics,
                    batch_number=batch_number,
                    attempt=attempt,
                    reason=f"DeepSeek 返回 {invalid_count} 个无效干扰项。",
                    count=invalid_count,
                )
            unresolved = remaining

        for index, blank in enumerate(unresolved, start=1):
            distractor = _fallback_candidate(blank, result, answer_keys, used_distractors, len(used_distractors) + index)
            _set_blank_distractor(blank, distractor, "代码兜底", used_distractors)
            _add_failure(
                diagnostics,
                batch_number=batch_number,
                attempt=max(1, max_attempts),
                reason="两次 DeepSeek 尝试后仍无有效结果，使用代码兜底。",
                count=1,
            )

    summary: dict[str, int] = dict(Counter(blank.get("distractor_source") or "未知" for blank in blanks))
    for blank in blanks:
        if not blank.get("distractors"):
            distractor = _fallback_candidate(blank, result, answer_keys, used_distractors, len(used_distractors) + 1)
            _set_blank_distractor(blank, distractor, "代码兜底", used_distractors)
    summary = dict(Counter(blank.get("distractor_source") or "未知" for blank in blanks))
    result["distractor_summary"] = summary
    diagnostics["elapsed_seconds"] = round(time.perf_counter() - started_at, 2)
    result["distractor_diagnostics"] = diagnostics
    return validate_finished_course_payload(result)

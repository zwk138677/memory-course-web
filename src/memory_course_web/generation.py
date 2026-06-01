"""DeepSeek generation for word-bank fill-in distractors."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any

from openai import OpenAI

from .distractors import fallback_distractors_for_blank
from .validation import PayloadValidationError, clean_text, validate_finished_course_payload


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    max_tokens: int = 6000
    temperature: float = 0.2


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


def _answer_keys(payload: dict[str, Any]) -> set[str]:
    return {str(blank.get("answer", "")).strip().casefold() for blank in payload.get("blanks", [])}


def _valid_single_distractor(value: Any, answer: str, answer_keys: set[str], used: set[str]) -> str | None:
    try:
        cleaned = clean_text(value, "填空干扰项")
    except Exception:
        return None
    key = cleaned.casefold()
    if key == answer.strip().casefold() or key in answer_keys or key in used:
        return None
    return cleaned


def _fallback_candidate(blank: dict[str, Any], payload: dict[str, Any], answer_keys: set[str], used: set[str], index: int) -> str:
    answer = str(blank["answer"])
    for candidate in fallback_distractors_for_blank(blank, payload):
        cleaned = _valid_single_distractor(candidate, answer, answer_keys, used)
        if cleaned:
            return cleaned
    suffix = index
    while True:
        candidate = f"干扰项{suffix}"
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

    missing = [blank["id"] for blank in blanks if blank["id"] not in result]
    if missing:
        raise PayloadValidationError(f"DeepSeek 返回缺少填空项：{', '.join(missing)}")
    return result


def _set_blank_distractor(blank: dict[str, Any], distractor: str, source: str, used: set[str]) -> None:
    blank["distractors"] = [distractor]
    blank["distractor_source"] = source
    used.add(distractor.casefold())


def generate_blank_distractors(
    payload: dict[str, Any],
    config: DeepSeekConfig,
    *,
    batch_size: int = 20,
) -> dict[str, Any]:
    """Attach one globally valid word-bank distractor to each parsed blank."""

    result = validate_finished_course_payload(deepcopy(payload))
    blanks = result.get("blanks", [])
    if not blanks:
        result["distractor_summary"] = {}
        return result

    answer_keys = _answer_keys(result)
    used_distractors: set[str] = set()

    if not config.api_key:
        for index, blank in enumerate(blanks, start=1):
            distractor = _fallback_candidate(blank, result, answer_keys, used_distractors, index)
            _set_blank_distractor(blank, distractor, "代码兜底", used_distractors)
        result["distractor_summary"] = {"代码兜底": len(blanks)}
        return validate_finished_course_payload(result)

    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    for batch in _chunked(blanks, max(1, batch_size)):
        try:
            generated = _generate_batch(payload=result, blanks=batch, client=client, config=config)
        except Exception:
            generated = {}

        for index, blank in enumerate(batch, start=1):
            source = "DeepSeek"
            distractor = _valid_single_distractor(
                generated.get(blank["id"], ""),
                str(blank["answer"]),
                answer_keys,
                used_distractors,
            )
            if not distractor:
                distractor = _fallback_candidate(blank, result, answer_keys, used_distractors, len(used_distractors) + index)
                source = "代码兜底"
            _set_blank_distractor(blank, distractor, source, used_distractors)

    summary: dict[str, int] = {}
    for blank in blanks:
        source = blank.get("distractor_source") or "未知"
        summary[source] = summary.get(source, 0) + 1
    result["distractor_summary"] = summary
    return validate_finished_course_payload(result)

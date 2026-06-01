"""DeepSeek generation for fill-in distractors only."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any

from openai import OpenAI

from .distractors import fallback_distractors_for_blank
from .validation import PayloadValidationError, validate_distractor_list, validate_finished_course_payload


@dataclass(frozen=True)
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    max_tokens: int = 6000
    temperature: float = 0.2


SYSTEM_PROMPT = """你是一名严谨的初中数学教研老师。你只输出合法 JSON，不输出 Markdown。
任务：为知识填空答案生成选择题干扰项。
要求：
1. 每个 id 必须返回 3 个 distractors。
2. distractors 不能等于 answer，三项之间也不能重复。
3. 干扰项应像学生常见误选，风格贴近初中数学教材。
4. 不要改写 answer，不要生成题干，不要生成快速练习。
5. 输出 JSON 格式：{"items":[{"id":"b001","distractors":["...","...","..."]}]}。
"""


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


def _generate_batch(
    *,
    payload: dict[str, Any],
    blanks: list[dict[str, Any]],
    client: OpenAI,
    config: DeepSeekConfig,
) -> dict[str, list[str]]:
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

    by_id = {blank["id"]: blank for blank in blanks}
    result: dict[str, list[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", ""))
        if item_id not in by_id:
            continue
        answer = by_id[item_id]["answer"]
        result[item_id] = validate_distractor_list(answer, item.get("distractors"), f"{item_id} 干扰项")

    missing = [blank["id"] for blank in blanks if blank["id"] not in result]
    if missing:
        raise PayloadValidationError(f"DeepSeek 返回缺少填空项：{', '.join(missing)}")
    return result


def _apply_fallback_for_blank(payload: dict[str, Any], blank: dict[str, Any]) -> None:
    blank["distractors"] = fallback_distractors_for_blank(blank, payload)
    blank["distractor_source"] = "代码兜底"


def generate_blank_distractors(
    payload: dict[str, Any],
    config: DeepSeekConfig,
    *,
    batch_size: int = 20,
) -> dict[str, Any]:
    """Attach distractors to parsed blanks.

    DeepSeek is best-effort. Missing API keys, request failures, or validation
    errors fall back to deterministic code-generated distractors.
    """

    result = validate_finished_course_payload(deepcopy(payload))
    blanks = result.get("blanks", [])
    if not blanks:
        result["distractor_summary"] = {}
        return result

    if not config.api_key:
        for blank in blanks:
            _apply_fallback_for_blank(result, blank)
        result["distractor_summary"] = {"代码兜底": len(blanks)}
        return result

    client = OpenAI(api_key=config.api_key, base_url=config.base_url)
    for batch in _chunked(blanks, max(1, batch_size)):
        try:
            generated = _generate_batch(payload=result, blanks=batch, client=client, config=config)
        except Exception:
            for blank in batch:
                _apply_fallback_for_blank(result, blank)
            continue

        for blank in batch:
            try:
                blank["distractors"] = validate_distractor_list(
                    blank["answer"],
                    generated[blank["id"]],
                    f"{blank['id']} 干扰项",
                )
                blank["distractor_source"] = "DeepSeek"
            except Exception:
                _apply_fallback_for_blank(result, blank)

    summary: dict[str, int] = {}
    for blank in blanks:
        source = blank.get("distractor_source") or "未知"
        summary[source] = summary.get(source, 0) + 1
    result["distractor_summary"] = summary
    return validate_finished_course_payload(result)

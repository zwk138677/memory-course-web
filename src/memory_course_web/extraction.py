"""DOCX knowledge-list extraction for the Streamlit app."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .vendor import extract_knowledge_lists as klist


@dataclass(frozen=True)
class ExtractedKnowledge:
    """Text-first result from a handout's conservative enhanced knowledge list."""

    title: str
    knowledge_text: str
    paragraphs: list[str]
    method: str
    selected_blocks: int
    enhanced_blocks: int
    stats: dict[str, int]


def _visible_text(blocks: list[Any]) -> str:
    lines: list[str] = []
    for block in blocks:
        text = klist.block_text(block).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _clean_text_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        compact = re.sub(r"\s+", "", line)
        if len(compact) <= 10 and re.fullmatch(r"[A-Za-z0-9OCBA鈭犫埖鈭存垨.锛庛€俔]+", compact):
            if not any(symbol in compact for symbol in ("=", "<", ">", "+", "-", "脳", "梅")):
                continue
        lines.append(line)
    return lines


def extract_knowledge_text(docx_path: Path | str, *, allow_course_fallback: bool = True) -> ExtractedKnowledge:
    """Extract and conservatively compress the handout knowledge list into text.

    The underlying selector/refiner is the same logic used by the original
    knowledge-list-extractor workflow. The web app intentionally returns text
    only for v1 so deployment does not depend on Word/LibreOffice rendering.
    """

    path = Path(docx_path)
    if path.suffix.lower() != ".docx":
        raise ValueError("只支持上传 .docx Word 文件。")
    if not path.exists():
        raise FileNotFoundError(path)

    source = klist.DocxPackage.load(path)
    start, end, method = klist.select_knowledge_range(
        source,
        allow_course_fallback=allow_course_fallback,
    )
    source_children = [child for child in list(source.body) if child.tag != klist.q_w("sectPr")]
    selected = [child for child in source_children[start:end] if child.tag != klist.q_w("sectPr")]
    enhanced, stats, _decisions = klist.refine_blocks_conservative_enhanced(selected)

    paragraphs = _clean_text_lines(_visible_text(enhanced))
    if not paragraphs:
        raise ValueError("已定位知识清单，但没有提取到可用于网页学习的文字内容。")

    return ExtractedKnowledge(
        title=path.stem,
        knowledge_text="\n".join(paragraphs),
        paragraphs=paragraphs,
        method=method,
        selected_blocks=len(selected),
        enhanced_blocks=len(enhanced),
        stats=stats,
    )

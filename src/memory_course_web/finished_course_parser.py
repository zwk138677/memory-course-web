"""Parse finished knowledge-memory course DOCX files for the web app."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import mimetypes
from pathlib import Path
from pathlib import PurePosixPath
import re
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V_NS = "urn:schemas-microsoft-com:vml"

BROWSER_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/svg+xml",
    "image/webp",
    "image/bmp",
}


def q_w(name: str) -> str:
    return f"{{{W_NS}}}{name}"


def q_r(name: str) -> str:
    return f"{{{R_NS}}}{name}"


def q_a(name: str) -> str:
    return f"{{{A_NS}}}{name}"


def q_wp(name: str) -> str:
    return f"{{{WP_NS}}}{name}"


def q_v(name: str) -> str:
    return f"{{{V_NS}}}{name}"


FIRST_PART_MARKERS = ("第一部分：《知识小题》", "第一部分：《知识点》")
SECOND_PART_MARKERS = ("第二部分：《快速练习》",)
PRACTICE_TITLE_MARKERS = ("📝 练习题", "练习题")
CATEGORY_LABELS = ("【基础辨析】", "【易错辨析】", "【简单应用】")
QUESTION_LABEL = "【题目内容】"
CORRECT_LABEL = "【正确选项】"
WRONG_RE = re.compile(r"^【错误选项\s*([123])】\s*[：:]\s*(.*)$")
QUESTION_RE = re.compile(r"^【题目内容】\s*[：:]\s*(.*)$")
CORRECT_RE = re.compile(r"^【正确选项】\s*[：:]\s*(.*)$")
QUESTION_HEADING_RE = re.compile(r"^【第[一二三四五六七八九十百\d]+题】\s*[：:]?\s*(.*)$")
LEADING_NUMBER_RE = re.compile(r"^\s*\d+\s*[．.、]\s*")


@dataclass(frozen=True)
class UnderlineSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ParagraphImage:
    id: str
    filename: str
    mime_type: str
    data_uri: str
    renderable: bool
    alt_text: str = ""
    width_px: int | None = None
    height_px: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "data_uri": self.data_uri,
            "renderable": self.renderable,
            "alt_text": self.alt_text,
            "width_px": self.width_px,
            "height_px": self.height_px,
        }


@dataclass(frozen=True)
class ParsedParagraph:
    text: str
    underline_spans: list[UnderlineSpan] = field(default_factory=list)
    images: list[ParagraphImage] = field(default_factory=list)


@dataclass(frozen=True)
class FinishedCourse:
    title: str
    knowledge_paragraphs: list[str]
    knowledge_images: list[dict[str, Any]]
    blanks: list[dict[str, Any]]
    quick_practice: list[dict[str, Any]]
    source_name: str
    structure: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "knowledge_paragraphs": self.knowledge_paragraphs,
            "knowledge_text": "\n".join(self.knowledge_paragraphs),
            "knowledge_images": self.knowledge_images,
            "blanks": self.blanks,
            "quick_practice": self.quick_practice,
            "source_name": self.source_name,
            "structure": self.structure,
        }


def _text_from_run(run: ET.Element) -> str:
    parts: list[str] = []
    for node in run.iter():
        if node.tag == q_w("t"):
            parts.append(node.text or "")
        elif node.tag == q_w("tab"):
            parts.append("\t")
        elif node.tag == q_w("br"):
            parts.append("\n")
    return "".join(parts)


def _is_underlined(run: ET.Element) -> bool:
    rpr = run.find(q_w("rPr"))
    if rpr is None:
        return False
    underline = rpr.find(q_w("u"))
    if underline is None:
        return False
    value = underline.attrib.get(q_w("val"), "single")
    return value not in {"none", "0", "false"}


def _mime_type_for_name(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    if guessed:
        return guessed
    suffix = Path(name).suffix.lower()
    if suffix == ".emf":
        return "image/x-emf"
    if suffix == ".wmf":
        return "image/wmf"
    return "application/octet-stream"


def _relationship_target_path(target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    return str(PurePosixPath("word") / PurePosixPath(target))


def _load_media_lookup(package: ZipFile) -> dict[str, dict[str, Any]]:
    rels_path = "word/_rels/document.xml.rels"
    if rels_path not in package.namelist():
        return {}

    relationships = ET.fromstring(package.read(rels_path))
    media: dict[str, dict[str, Any]] = {}
    package_names = set(package.namelist())
    for relationship in relationships:
        rel_id = relationship.attrib.get("Id", "")
        rel_type = relationship.attrib.get("Type", "")
        target = relationship.attrib.get("Target", "")
        target_mode = relationship.attrib.get("TargetMode", "")
        if not rel_id or not rel_type.endswith("/image") or not target:
            continue

        filename = Path(target).name
        mime_type = _mime_type_for_name(filename)
        renderable = mime_type in BROWSER_IMAGE_MIME_TYPES
        data_uri = ""
        if target_mode != "External":
            package_path = _relationship_target_path(target)
            if package_path in package_names and renderable:
                encoded = base64.b64encode(package.read(package_path)).decode("ascii")
                data_uri = f"data:{mime_type};base64,{encoded}"
        media[rel_id] = {
            "id": rel_id,
            "filename": filename,
            "mime_type": mime_type,
            "data_uri": data_uri,
            "renderable": bool(renderable and data_uri),
        }
    return media


def _emu_to_px(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return max(1, round(int(value) / 9525))
    except (TypeError, ValueError):
        return None


def _drawing_images(run: ET.Element, media_lookup: dict[str, dict[str, Any]]) -> list[ParagraphImage]:
    images: list[ParagraphImage] = []
    for drawing in run.iter(q_w("drawing")):
        extent = drawing.find(f".//{q_wp('extent')}")
        doc_pr = drawing.find(f".//{q_wp('docPr')}")
        width_px = _emu_to_px(extent.attrib.get("cx")) if extent is not None else None
        height_px = _emu_to_px(extent.attrib.get("cy")) if extent is not None else None
        alt_text = ""
        if doc_pr is not None:
            alt_text = doc_pr.attrib.get("descr") or doc_pr.attrib.get("title") or doc_pr.attrib.get("name", "")

        for blip in drawing.iter(q_a("blip")):
            rel_id = blip.attrib.get(q_r("embed")) or blip.attrib.get(q_r("link"))
            if not rel_id or rel_id not in media_lookup:
                continue
            media = media_lookup[rel_id]
            images.append(
                ParagraphImage(
                    id=str(media["id"]),
                    filename=str(media["filename"]),
                    mime_type=str(media["mime_type"]),
                    data_uri=str(media["data_uri"]),
                    renderable=bool(media["renderable"]),
                    alt_text=alt_text,
                    width_px=width_px,
                    height_px=height_px,
                )
            )
    return images


def _vml_images(run: ET.Element, media_lookup: dict[str, dict[str, Any]]) -> list[ParagraphImage]:
    images: list[ParagraphImage] = []
    for image_data in run.iter(q_v("imagedata")):
        rel_id = image_data.attrib.get(q_r("id")) or image_data.attrib.get(q_r("link"))
        if not rel_id or rel_id not in media_lookup:
            continue
        media = media_lookup[rel_id]
        images.append(
            ParagraphImage(
                id=str(media["id"]),
                filename=str(media["filename"]),
                mime_type=str(media["mime_type"]),
                data_uri=str(media["data_uri"]),
                renderable=bool(media["renderable"]),
                alt_text=image_data.attrib.get("title", ""),
            )
        )
    return images


def _images_from_run(run: ET.Element, media_lookup: dict[str, dict[str, Any]]) -> list[ParagraphImage]:
    return [*_drawing_images(run, media_lookup), *_vml_images(run, media_lookup)]


def _trim_span(text: str, start: int, end: int) -> UnderlineSpan | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start >= end:
        return None
    return UnderlineSpan(start=start, end=end, text=text[start:end])


def _paragraph_from_xml(paragraph: ET.Element, media_lookup: dict[str, dict[str, Any]]) -> ParsedParagraph:
    text_parts: list[str] = []
    raw_spans: list[tuple[int, int]] = []
    images: list[ParagraphImage] = []
    cursor = 0

    for run in paragraph.iter(q_w("r")):
        images.extend(_images_from_run(run, media_lookup))
        run_text = _text_from_run(run)
        if not run_text:
            continue
        start = cursor
        cursor += len(run_text)
        text_parts.append(run_text)
        if _is_underlined(run):
            if raw_spans and raw_spans[-1][1] == start:
                raw_spans[-1] = (raw_spans[-1][0], cursor)
            else:
                raw_spans.append((start, cursor))

    raw_text = "".join(text_parts)
    leading_trim = len(raw_text) - len(raw_text.lstrip())
    trailing_trim = len(raw_text.rstrip())
    text = raw_text.strip()
    spans = [
        span
        for raw_start, raw_end in raw_spans
        if (span := _trim_span(raw_text, raw_start, raw_end)) is not None
        and span.end > leading_trim
        and span.start < trailing_trim
    ]
    shifted_spans = [
        UnderlineSpan(
            start=max(0, span.start - leading_trim),
            end=min(len(text), span.end - leading_trim),
            text=text[max(0, span.start - leading_trim) : min(len(text), span.end - leading_trim)],
        )
        for span in spans
    ]
    shifted_spans = [span for span in shifted_spans if span.start < span.end and span.text.strip()]
    return ParsedParagraph(text=text, underline_spans=shifted_spans, images=images)


def _nonempty_paragraphs(docx_path: Path) -> list[ParsedParagraph]:
    with ZipFile(docx_path, "r") as package:
        media_lookup = _load_media_lookup(package)
        document = ET.fromstring(package.read("word/document.xml"))
    paragraphs: list[ParsedParagraph] = []
    for paragraph in document.iter(q_w("p")):
        parsed = _paragraph_from_xml(paragraph, media_lookup)
        if parsed.text or parsed.images:
            paragraphs.append(parsed)
    return paragraphs


def _clean_title_from_filename(path: Path) -> str:
    title = path.stem
    for suffix in ("_知识背记课程_高清兼容版", "_知识背记课程_兼容渲染版", "_知识背记课程_配图修订版", "_知识背记课程_配图模板预览版", "_知识背记课程"):
        title = title.replace(suffix, "")
    return title.strip(" _-") or path.stem


def _find_first_index(paragraphs: list[ParsedParagraph], predicate) -> int | None:
    for index, paragraph in enumerate(paragraphs):
        if predicate(paragraph.text.strip()):
            return index
    return None


def _is_question_line(text: str) -> bool:
    return text.strip().startswith(QUESTION_LABEL)


def _is_question_heading(text: str) -> bool:
    return bool(QUESTION_HEADING_RE.match(text.strip()))


def _is_category_label(text: str) -> bool:
    return text.strip() in CATEGORY_LABELS


def _is_practice_title(text: str) -> bool:
    compact = re.sub(r"\s+", "", text.strip())
    return any(re.sub(r"\s+", "", marker) == compact for marker in PRACTICE_TITLE_MARKERS)


def _is_practice_boundary(text: str) -> bool:
    stripped = text.strip()
    return (
        _is_second_marker(stripped)
        or _is_practice_title(stripped)
        or _is_category_label(stripped)
        or _is_question_heading(stripped)
        or _is_question_line(stripped)
    )


def _is_first_marker(text: str) -> bool:
    return any(marker in text for marker in FIRST_PART_MARKERS)


def _is_second_marker(text: str) -> bool:
    return any(marker in text for marker in SECOND_PART_MARKERS)


def _strip_question_stem(text: str) -> str:
    match = QUESTION_RE.match(text.strip())
    value = match.group(1).strip() if match else text.strip()
    return LEADING_NUMBER_RE.sub("", value).strip()


def _strip_question_heading(text: str) -> str:
    match = QUESTION_HEADING_RE.match(text.strip())
    return match.group(1).strip() if match else ""


def _strip_correct(text: str) -> str:
    match = CORRECT_RE.match(text.strip())
    return match.group(1).strip() if match else ""


def _category_for(index: int) -> str:
    if index <= 6:
        return "基础辨析"
    if index <= 11:
        return "易错辨析"
    return "简单应用"


def _parse_questions(paragraphs: list[ParsedParagraph], start_index: int) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_category = ""

    for paragraph in paragraphs[start_index:]:
        text = paragraph.text.strip()
        paragraph_images = _images_payload(paragraph)
        if not text:
            if current is not None and paragraph_images:
                current.setdefault("images", []).extend(paragraph_images)
            continue
        if not text or _is_second_marker(text) or _is_practice_title(text):
            continue

        if _is_category_label(text):
            current_category = text.strip("【】")
            continue

        if _is_question_heading(text):
            if current is not None:
                questions.append(current)
            current = {
                "stem": _strip_question_heading(text),
                "correct": "",
                "wrong": [],
                "category": current_category,
                "images": paragraph_images,
            }
            continue

        if _is_question_line(text):
            stem = _strip_question_stem(text)
            if current is not None and not current.get("stem") and not current.get("correct") and not current.get("wrong"):
                current["stem"] = stem
                current.setdefault("images", []).extend(paragraph_images)
            else:
                if current is not None:
                    questions.append(current)
                current = {"stem": stem, "correct": "", "wrong": [], "category": current_category, "images": paragraph_images}
            continue

        if current is None:
            continue

        if paragraph_images:
            current.setdefault("images", []).extend(paragraph_images)

        if not current.get("stem") and not text.startswith("【"):
            current["stem"] = text
            continue

        if text.startswith("【") and not text.startswith((CORRECT_LABEL, "【错误选项")):
            if current is not None and (current.get("stem") or current.get("correct") or current.get("wrong")):
                questions.append(current)
            current = None
            continue

        correct = _strip_correct(text)
        if correct:
            current["correct"] = correct
            continue

        wrong_match = WRONG_RE.match(text)
        if wrong_match:
            current["wrong"].append(wrong_match.group(2).strip())

    if current is not None:
        questions.append(current)

    normalized: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        stem = str(question.get("stem", "")).strip()
        correct = str(question.get("correct", "")).strip()
        wrong = [str(item).strip() for item in question.get("wrong", []) if str(item).strip()]
        if not stem or not correct or len(wrong) != 3:
            continue
        normalized.append(
            {
                "category": str(question.get("category") or _category_for(index)),
                "stem": stem,
                "correct": correct,
                "wrong": wrong[:3],
                "images": list(question.get("images", [])),
            }
        )
    return normalized


def _build_blanks(knowledge_paragraphs: list[ParsedParagraph]) -> list[dict[str, Any]]:
    blanks: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(knowledge_paragraphs):
        for span in paragraph.underline_spans:
            answer = span.text.strip()
            if not answer:
                continue
            blanks.append(
                {
                    "id": f"b{len(blanks) + 1:03d}",
                    "answer": answer,
                    "paragraph_index": paragraph_index,
                    "start": span.start,
                    "end": span.end,
                    "distractors": [],
                    "distractor_source": "",
                }
            )
    return blanks


def _images_payload(paragraph: ParsedParagraph) -> list[dict[str, Any]]:
    return [image.to_payload() for image in paragraph.images]


def _build_knowledge_images(knowledge_paragraphs: list[ParsedParagraph]) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for paragraph_index, paragraph in enumerate(knowledge_paragraphs):
        for image in paragraph.images:
            payload = image.to_payload()
            payload["paragraph_index"] = paragraph_index
            images.append(payload)
    return images


def parse_finished_course(docx_path: Path | str) -> FinishedCourse:
    path = Path(docx_path)
    if path.suffix.lower() != ".docx":
        raise ValueError("只支持上传 .docx Word 文件。")
    if not path.exists():
        raise FileNotFoundError(path)

    paragraphs = _nonempty_paragraphs(path)
    if not paragraphs:
        raise ValueError("没有从 Word 文件中读取到正文。")

    first_marker_index = _find_first_index(paragraphs, _is_first_marker)
    second_marker_index = _find_first_index(paragraphs, _is_second_marker)
    first_practice_index = _find_first_index(paragraphs, _is_practice_boundary)

    if first_practice_index is None:
        raise ValueError("没有识别到快速练习区域。")

    if first_marker_index is not None:
        title = _clean_title_from_filename(path)
        knowledge_start = first_marker_index + 1
        knowledge_end = second_marker_index if second_marker_index is not None else first_practice_index
        question_start = second_marker_index if second_marker_index is not None else first_practice_index
        structure = "two_part_course"
    else:
        first_text = paragraphs[0].text.strip()
        title = first_text if not _is_question_line(first_text) else _clean_title_from_filename(path)
        knowledge_start = 1 if title == first_text and len(paragraphs) > 1 else 0
        knowledge_end = first_practice_index
        question_start = first_practice_index
        structure = "postprocessed_course"

    if knowledge_end <= knowledge_start:
        raise ValueError("没有识别到知识展示正文。")

    knowledge = paragraphs[knowledge_start:knowledge_end]
    knowledge_texts = [paragraph.text for paragraph in knowledge]
    if not any(text.strip() for text in knowledge_texts):
        raise ValueError("知识展示正文为空。")

    blanks = _build_blanks(knowledge)
    knowledge_images = _build_knowledge_images(knowledge)
    questions = _parse_questions(paragraphs, question_start)
    if not questions:
        raise ValueError("没有解析到完整的快速练习题。")

    return FinishedCourse(
        title=title,
        knowledge_paragraphs=knowledge_texts,
        knowledge_images=knowledge_images,
        blanks=blanks,
        quick_practice=questions,
        source_name=path.name,
        structure=structure,
    )

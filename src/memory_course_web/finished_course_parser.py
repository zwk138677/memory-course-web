"""Parse finished knowledge-memory course DOCX files for the web app."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from io import BytesIO
import mimetypes
from pathlib import Path
from pathlib import PurePosixPath
import re
import struct
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
V_NS = "urn:schemas-microsoft-com:vml"
O_NS = "urn:schemas-microsoft-com:office:office"

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime support
    Image = None  # type: ignore[assignment]

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


def q_o(name: str) -> str:
    return f"{{{O_NS}}}{name}"


FIRST_PART_MARKERS = ("第一部分：《知识小题》", "第一部分：《知识点》")
SECOND_PART_MARKERS = ("第二部分：《快速练习》",)
PRACTICE_TITLE_MARKERS = ("📝 练习题", "练习题", "— 配套练习题 —")
CATEGORY_LABELS = ("【基础辨析】", "【易错辨析】", "【简单应用】")
QUESTION_LABEL = "【题目内容】"
CORRECT_LABEL = "【正确选项】"
SOURCE_RE = re.compile(r"^【来源\s*[：:]\s*(知识小题\s*\d+)】\s*$")
ANALYSIS_RE = re.compile(r"^【解析】\s*[：:]\s*(.*)$")
WRONG_RE = re.compile(r"^【错误选项\s*([123])】\s*[：:]\s*(.*)$")
QUESTION_RE = re.compile(r"^【题目内容】\s*[：:]\s*(.*)$")
CORRECT_RE = re.compile(r"^【正确选项】\s*[：:]\s*(.*)$")
QUESTION_HEADING_RE = re.compile(r"^【第[一二三四五六七八九十百\d]+题】\s*[：:]?\s*(.*)$")
PHYSICS_KNOWLEDGE_POINT_RE = re.compile(r"^【知识点\s*\d+】$")
KNOWLEDGE_ITEM_RE = re.compile(r"^知识小题\s*\d+\s*[.．、]")
CHINESE_SECTION_RE = re.compile(r"^[一二三四五六七八九十]+[、.．]\s*(.+?)\s*$")
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
    inline: bool = False
    char_index: int | None = None
    kind: str = ""
    formula_text: str = ""

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
            "inline": self.inline,
            "char_index": self.char_index,
            "kind": self.kind,
            "formula_text": self.formula_text,
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


def _wmf_to_png_media(data: bytes) -> dict[str, Any] | None:
    if Image is None:
        return None
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            output = BytesIO()
            image.save(output, format="PNG")
            encoded = base64.b64encode(output.getvalue()).decode("ascii")
            return {
                "mime_type": "image/png",
                "data_uri": f"data:image/png;base64,{encoded}",
                "width_px": int(image.width),
                "height_px": int(image.height),
            }
    except Exception:
        return None


_CFB_END_OF_CHAIN = 0xFFFFFFFE
_CFB_FREE_SECTOR = 0xFFFFFFFF


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


class _CompoundBinaryFile:
    """Tiny CFB reader for MathType OLE streams embedded in DOCX."""

    def __init__(self, data: bytes) -> None:
        if len(data) < 512 or not data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            raise ValueError("not a compound file")
        self.data = data
        self.sector_size = 1 << _u16(data, 0x1E)
        self.mini_sector_size = 1 << _u16(data, 0x20)
        self.first_directory_sector = _u32(data, 0x30)
        self.mini_stream_cutoff = _u32(data, 0x38)
        self.first_mini_fat_sector = _u32(data, 0x3C)
        self.num_mini_fat_sectors = _u32(data, 0x40)
        difat = [_u32(data, 0x4C + 4 * index) for index in range(109)]
        self.difat = [sector for sector in difat if sector not in {_CFB_FREE_SECTOR, _CFB_END_OF_CHAIN}]
        self.fat: list[int] = []
        for sector in self.difat:
            sector_data = self._sector(sector)
            self.fat.extend(struct.unpack("<" + "I" * (len(sector_data) // 4), sector_data))

        self.directory_entries = self._read_directory_entries()
        root = next((entry for entry in self.directory_entries if entry["type"] == 5), None)
        self.mini_stream = b""
        if root and root["start"] not in {_CFB_FREE_SECTOR, _CFB_END_OF_CHAIN}:
            self.mini_stream = self._read_sector_chain(root["start"])[: int(root["size"])]

        self.mini_fat: list[int] = []
        if self.first_mini_fat_sector not in {_CFB_FREE_SECTOR, _CFB_END_OF_CHAIN}:
            mini_fat_data = self._read_sector_chain(
                self.first_mini_fat_sector,
                max_sectors=max(1, self.num_mini_fat_sectors),
            )
            self.mini_fat = list(
                struct.unpack("<" + "I" * (len(mini_fat_data) // 4), mini_fat_data[: len(mini_fat_data) // 4 * 4])
            )

    def _sector(self, sector: int) -> bytes:
        start = 512 + sector * self.sector_size
        return self.data[start : start + self.sector_size]

    def _read_sector_chain(self, start_sector: int, max_sectors: int = 10000) -> bytes:
        chunks: list[bytes] = []
        sector = start_sector
        seen: set[int] = set()
        while (
            sector not in {_CFB_FREE_SECTOR, _CFB_END_OF_CHAIN}
            and 0 <= sector < len(self.fat)
            and sector not in seen
            and len(seen) < max_sectors
        ):
            seen.add(sector)
            chunks.append(self._sector(sector))
            sector = self.fat[sector]
        return b"".join(chunks)

    def _read_mini_chain(self, start_sector: int, size: int) -> bytes:
        chunks: list[bytes] = []
        sector = start_sector
        seen: set[int] = set()
        while (
            sector not in {_CFB_FREE_SECTOR, _CFB_END_OF_CHAIN}
            and 0 <= sector < len(self.mini_fat)
            and sector not in seen
        ):
            seen.add(sector)
            start = sector * self.mini_sector_size
            chunks.append(self.mini_stream[start : start + self.mini_sector_size])
            sector = self.mini_fat[sector]
        return b"".join(chunks)[:size]

    def _read_directory_entries(self) -> list[dict[str, Any]]:
        directory_data = self._read_sector_chain(self.first_directory_sector)
        entries: list[dict[str, Any]] = []
        for offset in range(0, len(directory_data), 128):
            entry = directory_data[offset : offset + 128]
            if len(entry) < 128:
                continue
            name_length = _u16(entry, 64)
            name = entry[: max(0, name_length - 2)].decode("utf-16le", errors="ignore") if name_length >= 2 else ""
            entries.append(
                {
                    "name": name,
                    "type": entry[66],
                    "start": _u32(entry, 116),
                    "size": _u64(entry, 120),
                }
            )
        return entries

    def read_stream(self, name: str) -> bytes | None:
        entry = next((item for item in self.directory_entries if item["type"] == 2 and item["name"] == name), None)
        if not entry:
            return None
        size = int(entry["size"])
        if size < self.mini_stream_cutoff:
            return self._read_mini_chain(int(entry["start"]), size)
        return self._read_sector_chain(int(entry["start"]))[:size]


def _extract_mathtype_native_stream(ole_bytes: bytes) -> bytes | None:
    try:
        cfb = _CompoundBinaryFile(ole_bytes)
        return cfb.read_stream("Equation Native")
    except Exception:
        return None


def _mathtype_native_text(native_stream: bytes | None) -> str:
    if not native_stream:
        return ""
    formula_region = native_stream[native_stream.find(b"DSMT7") :] if b"DSMT7" in native_stream else native_stream
    tokens = [
        match.group(1).decode("ascii", errors="ignore")
        for match in re.finditer(rb"\x0f\x01\x02\x00\x88([ -~])", formula_region)
    ]
    if len(tokens) <= 1:
        tokens = [
            match.group(1).decode("ascii", errors="ignore")
            for match in re.finditer(rb"\x88([0-9A-Za-z])", formula_region)
        ]
    tokens = [token for token in tokens if token and token not in {" "}]
    if not tokens:
        return ""
    joined = "".join(tokens)
    if tokens == ["1", "2"]:
        return "1/2"
    if joined == "90":
        return "90°"
    return joined


def _load_ole_formula_lookup(package: ZipFile) -> dict[str, str]:
    rels_path = "word/_rels/document.xml.rels"
    if rels_path not in package.namelist():
        return {}

    relationships = ET.fromstring(package.read(rels_path))
    package_names = set(package.namelist())
    formulas: dict[str, str] = {}
    for relationship in relationships:
        rel_id = relationship.attrib.get("Id", "")
        rel_type = relationship.attrib.get("Type", "")
        target = relationship.attrib.get("Target", "")
        target_mode = relationship.attrib.get("TargetMode", "")
        if not rel_id or not rel_type.endswith("/oleObject") or not target or target_mode == "External":
            continue
        package_path = _relationship_target_path(target)
        if package_path not in package_names:
            continue
        native_stream = _extract_mathtype_native_stream(package.read(package_path))
        text = _mathtype_native_text(native_stream)
        if text:
            formulas[rel_id] = text
    return formulas


def _formula_text_from_context(native_text: str, prefix_text: str, suffix_text: str) -> str:
    native_text = native_text.strip()
    compact_prefix = re.sub(r"\s+", "", prefix_text)
    compact_suffix = re.sub(r"\s+", "", suffix_text)
    if native_text == "1/2":
        term = ""
        if "的一半" in compact_prefix:
            before_half = compact_prefix.rsplit("的一半", 1)[0]
            term = before_half.rsplit("所对的", 1)[-1]
            term = re.sub(r"^[^\u4e00-\u9fffA-Za-z∠]+", "", term)
        if term and not compact_suffix.startswith(term):
            return f"1/2{term}"
        return native_text
    if native_text == "90" or native_text == "90°":
        return "90°" if "直角" in compact_prefix or "直角" in compact_suffix else native_text
    if native_text:
        return native_text
    if "圆心角的一半" in compact_prefix and compact_prefix.endswith("圆周角="):
        return "1/2圆心角"
    if "直角" in compact_prefix and compact_suffix.startswith("的圆周角"):
        return "90°"
    return ""


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
        width_px = None
        height_px = None
        if target_mode != "External":
            package_path = _relationship_target_path(target)
            if package_path in package_names:
                image_bytes = package.read(package_path)
                if renderable:
                    encoded = base64.b64encode(image_bytes).decode("ascii")
                    data_uri = f"data:{mime_type};base64,{encoded}"
                elif mime_type in {"image/wmf", "image/x-wmf"}:
                    converted = _wmf_to_png_media(image_bytes)
                    if converted:
                        filename = f"{Path(filename).stem}.png"
                        mime_type = str(converted["mime_type"])
                        data_uri = str(converted["data_uri"])
                        width_px = int(converted["width_px"])
                        height_px = int(converted["height_px"])
                        renderable = True
        media[rel_id] = {
            "id": rel_id,
            "filename": filename,
            "mime_type": mime_type,
            "data_uri": data_uri,
            "renderable": bool(renderable and data_uri),
            "width_px": width_px,
            "height_px": height_px,
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
                    width_px=width_px or media.get("width_px"),
                    height_px=height_px or media.get("height_px"),
                )
            )
    return images


def _run_has_ole_object(run: ET.Element) -> bool:
    return any(True for _ in run.iter(q_w("object"))) or any(True for _ in run.iter(q_o("OLEObject")))


def _ole_formula_text_from_run(
    run: ET.Element,
    ole_formula_lookup: dict[str, str],
    prefix_text: str,
    suffix_text: str,
) -> tuple[str, str]:
    for ole_object in run.iter(q_o("OLEObject")):
        rel_id = ole_object.attrib.get(q_r("id")) or ole_object.attrib.get(q_r("link"))
        native_text = ole_formula_lookup.get(rel_id or "", "")
        formula_text = _formula_text_from_context(native_text, prefix_text, suffix_text)
        if formula_text:
            return formula_text, rel_id or ""
    return _formula_text_from_context("", prefix_text, suffix_text), ""


def _vml_images(
    run: ET.Element,
    media_lookup: dict[str, dict[str, Any]],
    *,
    inline_index: int | None = None,
    hide_unrenderable: bool = False,
) -> list[ParagraphImage]:
    images: list[ParagraphImage] = []
    for image_data in run.iter(q_v("imagedata")):
        rel_id = image_data.attrib.get(q_r("id")) or image_data.attrib.get(q_r("link"))
        if not rel_id or rel_id not in media_lookup:
            continue
        media = media_lookup[rel_id]
        if hide_unrenderable and not media["renderable"]:
            continue
        images.append(
            ParagraphImage(
                id=str(media["id"]),
                filename=str(media["filename"]),
                mime_type=str(media["mime_type"]),
                data_uri=str(media["data_uri"]),
                renderable=bool(media["renderable"]),
                alt_text=image_data.attrib.get("title", "") or ("公式" if inline_index is not None else ""),
                width_px=media.get("width_px"),
                height_px=media.get("height_px"),
                inline=inline_index is not None,
                char_index=inline_index,
                kind="formula" if inline_index is not None else "",
            )
        )
    return images


def _images_from_run(
    run: ET.Element,
    media_lookup: dict[str, dict[str, Any]],
    ole_formula_lookup: dict[str, str],
    char_index: int,
    prefix_text: str,
    suffix_text: str,
) -> list[ParagraphImage]:
    is_formula_object = _run_has_ole_object(run)
    images = _drawing_images(run, media_lookup)
    if is_formula_object:
        formula_text, ole_rel_id = _ole_formula_text_from_run(run, ole_formula_lookup, prefix_text, suffix_text)
        if formula_text:
            images.append(
                ParagraphImage(
                    id=ole_rel_id or f"formula-{char_index}",
                    filename="",
                    mime_type="text/plain",
                    data_uri="",
                    renderable=True,
                    alt_text="formula",
                    inline=True,
                    char_index=char_index,
                    kind="formula_text",
                    formula_text=formula_text,
                )
            )
            return images
    images.extend(
        _vml_images(
            run,
            media_lookup,
            inline_index=char_index if is_formula_object else None,
            hide_unrenderable=is_formula_object,
        )
    )
    return images


def _trim_span(text: str, start: int, end: int) -> UnderlineSpan | None:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start >= end:
        return None
    return UnderlineSpan(start=start, end=end, text=text[start:end])


def _paragraph_from_xml(
    paragraph: ET.Element,
    media_lookup: dict[str, dict[str, Any]],
    ole_formula_lookup: dict[str, str] | None = None,
) -> ParsedParagraph:
    text_parts: list[str] = []
    raw_spans: list[tuple[int, int]] = []
    images: list[ParagraphImage] = []
    cursor = 0
    ole_formula_lookup = ole_formula_lookup or {}
    runs = list(paragraph.iter(q_w("r")))
    run_texts = [_text_from_run(run) for run in runs]

    for run_index, run in enumerate(runs):
        prefix_text = "".join(text_parts)
        suffix_text = "".join(run_texts[run_index + 1 :])
        images.extend(_images_from_run(run, media_lookup, ole_formula_lookup, cursor, prefix_text, suffix_text))
        run_text = run_texts[run_index]
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
        ole_formula_lookup = _load_ole_formula_lookup(package)
        document = ET.fromstring(package.read("word/document.xml"))
    paragraphs: list[ParsedParagraph] = []
    for paragraph in document.iter(q_w("p")):
        parsed = _paragraph_from_xml(paragraph, media_lookup, ole_formula_lookup)
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


def _is_physics_knowledge_point(text: str) -> bool:
    return bool(PHYSICS_KNOWLEDGE_POINT_RE.match(text.strip()))


def _is_knowledge_item_heading(text: str) -> bool:
    return bool(KNOWLEDGE_ITEM_RE.match(text.strip()))


def _physics_section_title(text: str) -> str:
    match = CHINESE_SECTION_RE.match(text.strip())
    return match.group(1).strip() if match else ""


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


def _strip_source(text: str) -> str:
    match = SOURCE_RE.match(text.strip())
    return re.sub(r"\s+", "", match.group(1)) if match else ""


def _strip_analysis(text: str) -> str:
    match = ANALYSIS_RE.match(text.strip())
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
    saw_category_label = False

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
            saw_category_label = True
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

        source = _strip_source(text)
        if source:
            current["source"] = source
            continue

        analysis = _strip_analysis(text)
        if analysis:
            current["analysis"] = analysis
            continue

        correct = _strip_correct(text)
        if correct:
            current["correct"] = correct
            continue

        wrong_match = WRONG_RE.match(text)
        if wrong_match:
            current["wrong"].append(wrong_match.group(2).strip())
            continue

        if text.startswith("【") and not text.startswith((CORRECT_LABEL, "【错误选项")):
            if current is not None and (current.get("stem") or current.get("correct") or current.get("wrong")):
                questions.append(current)
            current = None

    if current is not None:
        questions.append(current)

    normalized: list[dict[str, Any]] = []
    for index, question in enumerate(questions, start=1):
        stem = str(question.get("stem", "")).strip()
        correct = str(question.get("correct", "")).strip()
        wrong = [str(item).strip() for item in question.get("wrong", []) if str(item).strip()]
        if not stem or not correct or len(wrong) != 3:
            continue
        source = str(question.get("source", "")).strip()
        analysis = str(question.get("analysis", "")).strip()
        category = str(question.get("category") or "").strip()
        if not category and not source and not analysis and not saw_category_label:
            category = _category_for(index)
        normalized.append(
            {
                "category": category,
                "stem": stem,
                "correct": correct,
                "wrong": wrong[:3],
                "source": source,
                "analysis": analysis,
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

    first_knowledge_item_index = next(
        (
            index
            for index, paragraph in enumerate(paragraphs[:first_practice_index])
            if index > 0 and _is_knowledge_item_heading(paragraph.text)
        ),
        None,
    )

    if first_marker_index is not None:
        title = _clean_title_from_filename(path)
        knowledge_start = first_marker_index + 1
        knowledge_end = second_marker_index if second_marker_index is not None else first_practice_index
        question_start = second_marker_index if second_marker_index is not None else first_practice_index
        structure = "two_part_course"
    elif (
        len(paragraphs) > 1
        and _is_physics_knowledge_point(paragraphs[0].text)
        and _physics_section_title(paragraphs[1].text)
    ):
        title = _physics_section_title(paragraphs[1].text)
        knowledge_start = 2
        knowledge_end = first_practice_index
        question_start = first_practice_index
        structure = "physics_course"
    elif first_knowledge_item_index is not None and paragraphs[0].text.strip():
        title = paragraphs[0].text.strip()
        knowledge_start = first_knowledge_item_index
        knowledge_end = first_practice_index
        question_start = first_practice_index
        structure = "physics_reference_course"
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

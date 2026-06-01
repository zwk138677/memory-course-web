#!/usr/bin/env python3
"""Batch extract and refine handout knowledge-list sections into DOCX files."""

from __future__ import annotations

import argparse
import copy
import json
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from zipfile import ZIP_DEFLATED, ZipFile
from lxml import etree as ET



W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
XML = "http://www.w3.org/XML/1998/namespace"

OUT_DIR_NAME = "知识清单提取结果"
FULL_DOC_NAME = "知识清单_完整拼接.docx"
REFINED_DOC_NAME = "知识清单_提炼拼接.docx"
MARKED_DOC_NAME = "知识清单_完整拼接_提炼删减标记.docx"
DECISION_TABLE_NAME = "知识清单_提炼决策对照表.xlsx"
REPORT_NAME = "知识清单_处理报告.json"
ENHANCED_REFINED_DOC_NAME = "知识清单_提炼拼接_保守增强压缩.docx"
ENHANCED_MARKED_DOC_NAME = "知识清单_完整拼接_保守增强压缩删减标记.docx"
ENHANCED_DECISION_TABLE_NAME = "知识清单_提炼决策对照表_保守增强压缩.xlsx"
KNOWLEDGE_TITLE_IMAGE_SIZES = {18068}
INTRO_TITLE_IMAGE_SIZES = {12212}
SECTION_END_TITLE_IMAGE_SIZES = {21620, 16224, 20016}

TEXT_START_MARKERS = ("知识清单",)
TEXT_END_MARKERS = ("经典例题", "笔记总结", "快速练习", "知识小题", "练习巩固")
COURSE_START_MARKERS = ("第一部分：《知识小题》", "第一部分：《知识点》")
COURSE_END_MARKERS = ("第二部分：《快速练习》",)

DROP_BLOCK_MARKERS = (
    "例题",
    "经典例题",
    "观察思考",
    "解题思路",
    "解题过程",
    "解：",
    "解析：",
    "分析：",
    "证明：",
    "思路：",
    "答案：",
    "例：",
    "知识回顾",
    "验证：",
    "故选",
    "详解",
)
DROP_ALWAYS_MARKERS = (
    "观察思考",
    "解题思路",
    "解题过程",
    "经典例题",
    "例题",
    "例：",
    "知识回顾",
    "详解",
)
REVIEW_DROP_MARKERS = (
    "解题思路",
    "解题过程",
    "解析",
    "分析",
    "证明",
    "例题",
)
DROP_SOFT_MARKERS = (
    "如图",
    "通过观察",
    "活动区域",
    "又该如何计算",
    "可以实现",
    "通常需要通过",
)
EXPLANATION_MARKERS = (
    "因为",
    "所以",
    "这说明",
    "实质是",
    "运用这些",
    "比如",
    "通常",
    "可以",
    "需要",
)
KEEP_BLOCK_MARKERS = (
    "知识点",
    "定义",
    "概念",
    "性质",
    "中心对称性",
    "旋转不变性",
    "几何意义",
    "定理",
    "推论",
    "判定",
    "判别式",
    "公式",
    "结论",
    "口诀",
    "注意",
    "易错",
    "要点",
    "记作",
    "读作",
    "又叫",
    "叫做",
    "称为",
    "等于",
    "相等",
    "对应",
    "一一对应",
    "相乘",
    "相加",
    "乘积",
    "运算法则",
    "适用",
    "关系",
    "图象",
    "范围",
    "分类",
    "方法",
    "目测法",
    "度量法",
    "叠合法",
    "规律",
    "法则",
    "符号",
    "条件",
    "当",
    "若",
)
HEADING_TERMS = (
    "实数",
    "无理数",
    "相反数",
    "绝对值",
    "反比例函数",
    "二次函数",
    "全等",
    "圆",
    "弧",
    "弦",
    "圆心角",
    "圆周角",
    "角",
    "角平分线",
    "单项式",
    "多项式",
    "整式",
    "判别式",
)
STANDALONE_LABELS = (
    "【要点提示】",
    "【特别提示】",
    "【补充】",
    "特别提示：",
    "补充：",
)
CALIBRATED_SUPPLEMENT_DROP_STARTS = (
    "双曲线既是中心对称图形",
)
CORE_EXPANSION_MARKERS = (
    "定义",
    "性质",
    "定理",
    "推论",
    "判定",
    "公式",
    "结论",
    "法则",
)

for prefix, uri in [
    ("", PKG_REL),
    ("", CT),
    ("wpc", "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas"),
    ("cx", "http://schemas.microsoft.com/office/drawing/2014/chartex"),
    ("cx1", "http://schemas.microsoft.com/office/drawing/2015/9/8/chartex"),
    ("cx2", "http://schemas.microsoft.com/office/drawing/2015/10/21/chartex"),
    ("cx3", "http://schemas.microsoft.com/office/drawing/2016/5/9/chartex"),
    ("cx4", "http://schemas.microsoft.com/office/drawing/2016/5/10/chartex"),
    ("cx5", "http://schemas.microsoft.com/office/drawing/2016/5/11/chartex"),
    ("cx6", "http://schemas.microsoft.com/office/drawing/2016/5/12/chartex"),
    ("cx7", "http://schemas.microsoft.com/office/drawing/2016/5/13/chartex"),
    ("cx8", "http://schemas.microsoft.com/office/drawing/2016/5/14/chartex"),
    ("w", W),
    ("r", R),
    ("v", "urn:schemas-microsoft-com:vml"),
    ("o", "urn:schemas-microsoft-com:office:office"),
    ("oel", "http://schemas.microsoft.com/office/2019/extlst"),
    ("m", "http://schemas.openxmlformats.org/officeDocument/2006/math"),
    ("aink", "http://schemas.microsoft.com/office/drawing/2016/ink"),
    ("am3d", "http://schemas.microsoft.com/office/drawing/2017/model3d"),
    ("w10", "urn:schemas-microsoft-com:office:word"),
    ("wp", "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"),
    ("wp14", "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing"),
    ("a", "http://schemas.openxmlformats.org/drawingml/2006/main"),
    ("pic", "http://schemas.openxmlformats.org/drawingml/2006/picture"),
    ("mc", "http://schemas.openxmlformats.org/markup-compatibility/2006"),
    ("w14", "http://schemas.microsoft.com/office/word/2010/wordml"),
    ("w15", "http://schemas.microsoft.com/office/word/2012/wordml"),
    ("w16cex", "http://schemas.microsoft.com/office/word/2018/wordml/cex"),
    ("w16cid", "http://schemas.microsoft.com/office/word/2016/wordml/cid"),
    ("w16", "http://schemas.microsoft.com/office/word/2018/wordml"),
    ("w16du", "http://schemas.microsoft.com/office/word/2023/wordml/word16du"),
    ("w16sdtdh", "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash"),
    ("w16sdtfl", "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock"),
    ("w16se", "http://schemas.microsoft.com/office/word/2015/wordml/symex"),
    ("wpg", "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup"),
    ("wpi", "http://schemas.microsoft.com/office/word/2010/wordprocessingInk"),
    ("wne", "http://schemas.microsoft.com/office/word/2006/wordml"),
    ("wps", "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"),
]:
    try:
        ET.register_namespace(prefix, uri)
    except ValueError:
        pass


def qn(uri: str, name: str) -> str:
    return f"{{{uri}}}{name}"


def q_w(name: str) -> str:
    return qn(W, name)


STYLE_REFERENCE_TAGS = {
    q_w("pStyle"),
    q_w("rStyle"),
    q_w("tblStyle"),
}
STYLE_LINK_TAGS = {
    q_w("basedOn"),
    q_w("next"),
    q_w("link"),
    q_w("numStyleLink"),
    q_w("styleLink"),
}


RANGE_MARKER_TAGS = {
    q_w("bookmarkStart"),
    q_w("bookmarkEnd"),
    q_w("commentRangeStart"),
    q_w("commentRangeEnd"),
    q_w("moveFromRangeStart"),
    q_w("moveFromRangeEnd"),
    q_w("moveToRangeStart"),
    q_w("moveToRangeEnd"),
    q_w("permStart"),
    q_w("permEnd"),
}


def natural_key(path: Path) -> list[object]:
    parts = re.split(r"(\d+)", path.stem)
    return [int(part) if part.isdigit() else part.casefold() for part in parts]


def block_text(block: ET.Element) -> str:
    return "".join(t.text or "" for t in block.iter(q_w("t"))).replace("\n", " ")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value)


def relationship_ids(block: ET.Element) -> list[str]:
    ids: set[str] = set()
    for el in block.iter():
        for value in el.attrib.values():
            if re.fullmatch(r"rId\d+", value):
                ids.add(value)
    return sorted(ids, key=lambda rid: int(rid[3:]))


def load_xml(entries: dict[str, bytes], name: str) -> ET.Element:
    return ET.fromstring(entries[name])


def load_relationships(entries: dict[str, bytes], name: str = "word/_rels/document.xml.rels") -> ET.Element:
    if name not in entries:
        return ET.Element(qn(PKG_REL, "Relationships"))
    return ET.fromstring(entries[name])


def rel_map(rels_root: ET.Element) -> dict[str, dict[str, str]]:
    return {rel.attrib["Id"]: dict(rel.attrib) for rel in rels_root}


def next_relationship_id(rels_root: ET.Element) -> str:
    max_id = 0
    for rel in rels_root:
        match = re.fullmatch(r"rId(\d+)", rel.attrib.get("Id", ""))
        if match:
            max_id = max(max_id, int(match.group(1)))
    return f"rId{max_id + 1}"


def is_picture_title_candidate(block: ET.Element, relationships: dict[str, dict[str, str]]) -> bool:
    if block_text(block).strip():
        return False
    rel_ids = relationship_ids(block)
    image_rels = [
        rid
        for rid in rel_ids
        if relationships.get(rid, {}).get("Type", "").endswith("/image")
    ]
    return len(image_rels) == 1


def is_major_picture_title_candidate(block: ET.Element, relationships: dict[str, dict[str, str]]) -> bool:
    """Identify section-title artwork, not regular diagrams inside a section."""
    rel_ids = relationship_ids(block)
    image_rels = [
        rid
        for rid in rel_ids
        if relationships.get(rid, {}).get("Type", "").endswith("/image")
    ]
    if len(image_rels) != 1:
        return False
    target = relationships[image_rels[0]].get("Target", "")
    return Path(target).suffix.lower() == ".emf"


def picture_title_image_info(
    source: "DocxPackage",
    block: ET.Element,
    relationships: dict[str, dict[str, str]],
) -> tuple[str, int] | None:
    if not is_major_picture_title_candidate(block, relationships):
        return None
    image_rel_id = [
        rid
        for rid in relationship_ids(block)
        if relationships.get(rid, {}).get("Type", "").endswith("/image")
    ][0]
    target = relationships[image_rel_id]["Target"]
    zip_path = target_to_zip_path("word/document.xml", target)
    return target, len(source.entries[zip_path])


def target_to_zip_path(source_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    base_dir = posixpath.dirname(source_part)
    return posixpath.normpath(posixpath.join(base_dir, target))


def zip_path_to_target(source_part: str, zip_path: str) -> str:
    base_dir = posixpath.dirname(source_part)
    rel = posixpath.relpath(zip_path, base_dir)
    return rel


def normalize_mc_ignorable(document_xml: bytes) -> bytes:
    match = re.search(br'\s+mc:Ignorable="([^"]*)"', document_xml)
    if match is None:
        return document_xml
    declared = {
        item.group(1).decode("ascii", errors="ignore")
        for item in re.finditer(br"xmlns:([A-Za-z0-9_]+)=", document_xml)
    }
    ignorable = match.group(1).decode("ascii", errors="ignore").split()
    kept = [prefix for prefix in ignorable if prefix in declared]
    if kept:
        replacement = b' mc:Ignorable="' + " ".join(kept).encode("ascii") + b'"'
        return document_xml[: match.start()] + replacement + document_xml[match.end() :]
    return document_xml[: match.start()] + document_xml[match.end() :]


def rels_path_for_part(part_path: str) -> str:
    folder = posixpath.dirname(part_path)
    name = posixpath.basename(part_path)
    return posixpath.join(folder, "_rels", f"{name}.rels")


def unique_zip_path(entries: dict[str, bytes], preferred: str) -> str:
    if preferred not in entries:
        return preferred
    folder = posixpath.dirname(preferred)
    stem = Path(preferred).stem
    suffix = Path(preferred).suffix
    index = 1
    while True:
        candidate = posixpath.join(folder, f"{stem}_{index}{suffix}")
        if candidate not in entries:
            return candidate
        index += 1


def content_type_for_part(src_ct: ET.Element, source_path: str) -> tuple[str, str] | None:
    part_name = "/" + source_path
    for override in src_ct.findall(qn(CT, "Override")):
        if override.attrib.get("PartName") == part_name:
            return "override", override.attrib["ContentType"]
    extension = Path(source_path).suffix.lstrip(".")
    for default in src_ct.findall(qn(CT, "Default")):
        if default.attrib.get("Extension") == extension:
            return "default", default.attrib["ContentType"]
    return None


def ensure_content_type(dst_ct: ET.Element, src_ct: ET.Element, source_path: str, dest_path: str) -> None:
    content_type = content_type_for_part(src_ct, source_path)
    if content_type is None:
        return
    kind, value = content_type
    if kind == "override":
        part_name = "/" + dest_path
        if not any(item.attrib.get("PartName") == part_name for item in dst_ct.findall(qn(CT, "Override"))):
            override = ET.Element(qn(CT, "Override"))
            override.set("PartName", part_name)
            override.set("ContentType", value)
            dst_ct.append(override)
    else:
        extension = Path(dest_path).suffix.lstrip(".")
        if not any(item.attrib.get("Extension") == extension for item in dst_ct.findall(qn(CT, "Default"))):
            default = ET.Element(qn(CT, "Default"))
            default.set("Extension", extension)
            default.set("ContentType", value)
            dst_ct.append(default)


def preferred_copy_path(source_path: str, copy_prefix: str) -> str:
    folder = posixpath.dirname(source_path)
    name = posixpath.basename(source_path)
    return posixpath.join(folder, f"{copy_prefix}_{name}")


@dataclass
class DocxPackage:
    path: Path
    entries: dict[str, bytes]
    document: ET.Element
    body: ET.Element
    rels_root: ET.Element
    content_types: ET.Element

    @classmethod
    def load(cls, path: Path) -> "DocxPackage":
        with ZipFile(path, "r") as package:
            entries = {info.filename: package.read(info.filename) for info in package.infolist()}
        document = load_xml(entries, "word/document.xml")
        body = document.find(q_w("body"))
        if body is None:
            raise ValueError(f"{path} has no word/document.xml body")
        return cls(
            path=path,
            entries=entries,
            document=document,
            body=body,
            rels_root=load_relationships(entries),
            content_types=load_xml(entries, "[Content_Types].xml"),
        )

    def relationships(self) -> dict[str, dict[str, str]]:
        return rel_map(self.rels_root)

    def serialize(self, output_path: Path) -> None:
        document_xml = ET.tostring(self.document, encoding="utf-8", xml_declaration=True)
        self.entries["word/document.xml"] = normalize_mc_ignorable(document_xml)
        self.entries["word/_rels/document.xml.rels"] = ET.tostring(self.rels_root, encoding="utf-8", xml_declaration=True)
        self.entries["[Content_Types].xml"] = ET.tostring(self.content_types, encoding="utf-8", xml_declaration=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output_path, "w", ZIP_DEFLATED) as output:
            for name, data in self.entries.items():
                output.writestr(name, data)


@dataclass
class CopyContext:
    src: DocxPackage
    dst: DocxPackage
    copy_prefix: str
    part_cache: dict[str, str] = field(default_factory=dict)


def copy_related_part(ctx: CopyContext, source_path: str) -> str:
    source_path = posixpath.normpath(source_path)
    if source_path in ctx.part_cache:
        return ctx.part_cache[source_path]
    if source_path not in ctx.src.entries:
        raise ValueError(f"Missing related part in {ctx.src.path.name}: {source_path}")

    preferred = preferred_copy_path(source_path, ctx.copy_prefix)
    dest_path = unique_zip_path(ctx.dst.entries, preferred)
    ctx.dst.entries[dest_path] = ctx.src.entries[source_path]
    ensure_content_type(ctx.dst.content_types, ctx.src.content_types, source_path, dest_path)
    ctx.part_cache[source_path] = dest_path

    src_rels_path = rels_path_for_part(source_path)
    if src_rels_path in ctx.src.entries:
        src_rels = ET.fromstring(ctx.src.entries[src_rels_path])
        dst_rels = ET.Element(qn(PKG_REL, "Relationships"))
        for src_rel in src_rels:
            new_rel = copy.copy(src_rel)
            if src_rel.attrib.get("TargetMode") != "External":
                child_source = target_to_zip_path(source_path, src_rel.attrib["Target"])
                child_dest = copy_related_part(ctx, child_source)
                new_rel.set("Target", zip_path_to_target(dest_path, child_dest))
            dst_rels.append(new_rel)
        dst_rels_path = rels_path_for_part(dest_path)
        ctx.dst.entries[dst_rels_path] = ET.tostring(dst_rels, encoding="utf-8", xml_declaration=True)
    return dest_path


def add_document_relationship(ctx: CopyContext, rel_id: str) -> str:
    relationships = ctx.src.relationships()
    source_rel = relationships.get(rel_id)
    if source_rel is None:
        raise ValueError(f"Missing relationship {rel_id} in {ctx.src.path.name}")

    new_id = next_relationship_id(ctx.dst.rels_root)
    new_rel = ET.Element(qn(PKG_REL, "Relationship"))
    new_rel.set("Id", new_id)
    new_rel.set("Type", source_rel["Type"])
    if source_rel.get("TargetMode") == "External":
        new_rel.set("Target", source_rel["Target"])
        new_rel.set("TargetMode", "External")
    else:
        source_part = target_to_zip_path("word/document.xml", source_rel["Target"])
        dest_part = copy_related_part(ctx, source_part)
        new_rel.set("Target", zip_path_to_target("word/document.xml", dest_part))
    ctx.dst.rels_root.append(new_rel)
    return new_id


def remap_relationships(blocks: list[ET.Element], ctx: CopyContext) -> None:
    rid_map: dict[str, str] = {}
    for block in blocks:
        for rel_id in relationship_ids(block):
            if rel_id not in rid_map:
                rid_map[rel_id] = add_document_relationship(ctx, rel_id)
    if not rid_map:
        return
    for block in blocks:
        for el in block.iter():
            for attr_name, value in list(el.attrib.items()):
                if value in rid_map:
                    el.set(attr_name, rid_map[value])


def set_page_break_before(paragraph: ET.Element) -> None:
    ppr = paragraph.find(q_w("pPr"))
    if ppr is None:
        ppr = ET.Element(q_w("pPr"))
        paragraph.insert(0, ppr)
    if ppr.find(q_w("pageBreakBefore")) is None:
        ET.SubElement(ppr, q_w("pageBreakBefore"))


def make_paragraph(text: str, *, bold: bool = False, size: int | None = None, page_break_before: bool = False) -> ET.Element:
    paragraph = ET.Element(q_w("p"))
    if page_break_before:
        set_page_break_before(paragraph)
    run = ET.SubElement(paragraph, q_w("r"))
    if bold or size:
        rpr = ET.SubElement(run, q_w("rPr"))
        if bold:
            ET.SubElement(rpr, q_w("b"))
        if size:
            sz = ET.SubElement(rpr, q_w("sz"))
            sz.set(q_w("val"), str(size))
            szcs = ET.SubElement(rpr, q_w("szCs"))
            szcs.set(q_w("val"), str(size))
    t = ET.SubElement(run, q_w("t"))
    t.text = text
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        t.set(qn(XML, "space"), "preserve")
    return paragraph


def clone_section_properties(body: ET.Element) -> ET.Element:
    children = list(body)
    if children and children[-1].tag == q_w("sectPr"):
        return copy.deepcopy(children[-1])
    return ET.Element(q_w("sectPr"))


def clear_body(body: ET.Element) -> None:
    for child in list(body):
        body.remove(child)


def select_by_text_markers(children: list[ET.Element], start_markers: Iterable[str], end_markers: Iterable[str]) -> tuple[int, int] | None:
    start_index = None
    for index, child in enumerate(children):
        text = normalize_text(block_text(child))
        if any(marker in text for marker in start_markers):
            start_index = index + 1
            break
    if start_index is None:
        return None
    end_index = None
    for index in range(start_index, len(children)):
        text = normalize_text(block_text(children[index]))
        if any(marker in text for marker in end_markers):
            end_index = index
            break
    if end_index is None:
        end_index = len(children)
    while end_index > start_index and children[end_index - 1].tag == q_w("sectPr"):
        end_index -= 1
    return start_index, end_index


def select_knowledge_range(source: DocxPackage, *, allow_course_fallback: bool) -> tuple[int, int, str]:
    children = [child for child in list(source.body) if child.tag != q_w("sectPr")]
    relationships = source.relationships()
    candidates: list[tuple[int, int]] = []
    for index, child in enumerate(children):
        info = picture_title_image_info(source, child, relationships)
        if info is not None:
            _, image_size = info
            candidates.append((index, image_size))

    knowledge_candidates = [
        (index, image_size)
        for index, image_size in candidates
        if image_size in KNOWLEDGE_TITLE_IMAGE_SIZES
    ]
    if not knowledge_candidates:
        for position, (index, image_size) in enumerate(candidates):
            if image_size not in INTRO_TITLE_IMAGE_SIZES:
                continue
            next_index = candidates[position + 1][0] if position + 1 < len(candidates) else len(children)
            section_text = normalize_text("".join(block_text(child) for child in children[index + 1 : next_index]))
            if "知识点" in section_text or any(marker in section_text for marker in ("定义", "法则", "性质", "公式")):
                knowledge_candidates.append((index, image_size))
                break

    if knowledge_candidates:
        start_title_index, image_size = knowledge_candidates[0]
        start = start_title_index + 1
        later_end_titles = [
            index
            for index, later_size in candidates
            if index > start_title_index and later_size in SECTION_END_TITLE_IMAGE_SIZES
        ]
        end = later_end_titles[0] if later_end_titles else len(children)
        return start, end, f"knowledge_title_image_size_{image_size}"

    text_range = select_by_text_markers(children, TEXT_START_MARKERS, TEXT_END_MARKERS)
    if text_range is not None:
        return text_range[0], text_range[1], "text_heading_knowledge_list"

    if allow_course_fallback:
        course_range = select_by_text_markers(children, COURSE_START_MARKERS, COURSE_END_MARKERS)
        if course_range is not None:
            return course_range[0], course_range[1], "existing_course_section"

    raise ValueError(
        f"Cannot locate a strict knowledge-list range in {source.path.name}; "
        f"picture title candidates={candidates}"
    )


def used_num_ids(blocks: list[ET.Element]) -> set[str]:
    values = set()
    for block in blocks:
        for num_id in block.iter(q_w("numId")):
            value = num_id.attrib.get(q_w("val"))
            if value is not None:
                values.add(value)
    return values


def max_int_attr(root: ET.Element, tag: str, attr: str) -> int:
    max_value = 0
    for item in root.iter(tag):
        value = item.attrib.get(attr)
        if value and value.isdigit():
            max_value = max(max_value, int(value))
    return max_value


def ensure_numbering_part(dst: DocxPackage) -> ET.Element:
    if "word/numbering.xml" not in dst.entries:
        root = ET.Element(q_w("numbering"))
        dst.entries["word/numbering.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        ensure_content_type(dst.content_types, dst.content_types, "word/numbering.xml", "word/numbering.xml")
    return ET.fromstring(dst.entries["word/numbering.xml"])


def merge_numbering(
    blocks: list[ET.Element],
    src: DocxPackage,
    dst: DocxPackage,
    style_map: dict[str, str] | None = None,
) -> None:
    ids = used_num_ids(blocks)
    if not ids or "word/numbering.xml" not in src.entries:
        return
    src_root = ET.fromstring(src.entries["word/numbering.xml"])
    dst_root = ensure_numbering_part(dst)
    next_abs = max_int_attr(dst_root, q_w("abstractNum"), q_w("abstractNumId")) + 1
    next_num = max_int_attr(dst_root, q_w("num"), q_w("numId")) + 1
    num_map: dict[str, str] = {}

    for old_num_id in sorted(ids, key=lambda item: int(item) if item.isdigit() else 0):
        src_num = next((item for item in src_root.findall(q_w("num")) if item.attrib.get(q_w("numId")) == old_num_id), None)
        if src_num is None:
            continue
        abs_id_el = src_num.find(q_w("abstractNumId"))
        if abs_id_el is None:
            continue
        old_abs_id = abs_id_el.attrib.get(q_w("val"))
        src_abs = next((item for item in src_root.findall(q_w("abstractNum")) if item.attrib.get(q_w("abstractNumId")) == old_abs_id), None)
        if src_abs is None:
            continue
        new_abs_id = str(next_abs)
        next_abs += 1
        new_num_id = str(next_num)
        next_num += 1

        abs_copy = copy.deepcopy(src_abs)
        abs_copy.set(q_w("abstractNumId"), new_abs_id)
        for nsid in abs_copy.iter(q_w("nsid")):
            nsid.set(q_w("val"), f"{int(new_abs_id):08X}"[-8:])
        num_copy = copy.deepcopy(src_num)
        num_copy.set(q_w("numId"), new_num_id)
        num_copy.find(q_w("abstractNumId")).set(q_w("val"), new_abs_id)
        if style_map:
            remap_style_references([abs_copy, num_copy], style_map)
        dst_root.append(abs_copy)
        dst_root.append(num_copy)
        num_map[old_num_id] = new_num_id

    if num_map:
        for block in blocks:
            for num_id in block.iter(q_w("numId")):
                value = num_id.attrib.get(q_w("val"))
                if value in num_map:
                    num_id.set(q_w("val"), num_map[value])
        dst.entries["word/numbering.xml"] = ET.tostring(dst_root, encoding="utf-8", xml_declaration=True)


def styles_by_id(styles_root: ET.Element) -> dict[str, ET.Element]:
    result: dict[str, ET.Element] = {}
    for style in styles_root.findall(q_w("style")):
        style_id = style.attrib.get(q_w("styleId"))
        if style_id:
            result[style_id] = style
    return result


def default_style_id(styles_root: ET.Element, style_type: str) -> str | None:
    for style in styles_root.findall(q_w("style")):
        if style.attrib.get(q_w("type")) != style_type:
            continue
        if style.attrib.get(q_w("default")) in {"1", "true", "on"}:
            return style.attrib.get(q_w("styleId"))
    return None


def doc_default_pr(styles_root: ET.Element, kind: str) -> ET.Element | None:
    doc_defaults = styles_root.find(q_w("docDefaults"))
    if doc_defaults is None:
        return None
    default_wrapper = doc_defaults.find(q_w(f"{kind}PrDefault"))
    if default_wrapper is None:
        return None
    return default_wrapper.find(q_w(f"{kind}Pr"))


def ensure_style_child(style: ET.Element, tag: str) -> ET.Element:
    child = style.find(tag)
    if child is None:
        child = ET.Element(tag)
        style.append(child)
    return child


def merge_missing_pr_children(target_pr: ET.Element, default_pr: ET.Element | None) -> None:
    if default_pr is None:
        return
    by_tag = {child.tag: child for child in target_pr}
    for default_child in default_pr:
        existing = by_tag.get(default_child.tag)
        if existing is None:
            target_pr.append(copy.deepcopy(default_child))
            by_tag[default_child.tag] = target_pr[-1]
            continue
        for attr_name, attr_value in default_child.attrib.items():
            if attr_name not in existing.attrib:
                existing.set(attr_name, attr_value)


def materialize_source_defaults(
    style: ET.Element,
    source_rpr_default: ET.Element | None,
    source_ppr_default: ET.Element | None,
) -> None:
    style_type = style.attrib.get(q_w("type"))
    if style_type in {"paragraph", "character", "numbering"}:
        merge_missing_pr_children(ensure_style_child(style, q_w("rPr")), source_rpr_default)
    if style_type in {"paragraph", "numbering"}:
        merge_missing_pr_children(ensure_style_child(style, q_w("pPr")), source_ppr_default)


def get_paragraph_style(paragraph: ET.Element) -> ET.Element | None:
    ppr = paragraph.find(q_w("pPr"))
    if ppr is None:
        return None
    return ppr.find(q_w("pStyle"))


def ensure_paragraph_style(paragraph: ET.Element, style_id: str) -> None:
    ppr = paragraph.find(q_w("pPr"))
    if ppr is None:
        ppr = ET.Element(q_w("pPr"))
        paragraph.insert(0, ppr)
    p_style = ppr.find(q_w("pStyle"))
    if p_style is None:
        p_style = ET.Element(q_w("pStyle"))
        ppr.insert(0, p_style)
    p_style.set(q_w("val"), style_id)


def get_table_style(table: ET.Element) -> ET.Element | None:
    tbl_pr = table.find(q_w("tblPr"))
    if tbl_pr is None:
        return None
    return tbl_pr.find(q_w("tblStyle"))


def ensure_table_style(table: ET.Element, style_id: str) -> None:
    tbl_pr = table.find(q_w("tblPr"))
    if tbl_pr is None:
        tbl_pr = ET.Element(q_w("tblPr"))
        table.insert(0, tbl_pr)
    tbl_style = tbl_pr.find(q_w("tblStyle"))
    if tbl_style is None:
        tbl_style = ET.Element(q_w("tblStyle"))
        tbl_pr.insert(0, tbl_style)
    tbl_style.set(q_w("val"), style_id)


def collect_block_style_ids(
    blocks: list[ET.Element],
    source_default_paragraph_style: str | None,
    source_default_table_style: str | None,
) -> set[str]:
    style_ids: set[str] = set()
    for block in blocks:
        for paragraph in block.iter(q_w("p")):
            p_style = get_paragraph_style(paragraph)
            if p_style is None and source_default_paragraph_style:
                ensure_paragraph_style(paragraph, source_default_paragraph_style)
                style_ids.add(source_default_paragraph_style)
        for table in block.iter(q_w("tbl")):
            tbl_style = get_table_style(table)
            if tbl_style is None and source_default_table_style:
                ensure_table_style(table, source_default_table_style)
                style_ids.add(source_default_table_style)
        for element in block.iter():
            if element.tag in STYLE_REFERENCE_TAGS:
                value = element.attrib.get(q_w("val"))
                if value:
                    style_ids.add(value)
    return style_ids


def collect_style_closure(initial_ids: set[str], source_styles: dict[str, ET.Element]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    queue = list(initial_ids)
    while queue:
        style_id = queue.pop(0)
        if style_id in seen:
            continue
        seen.add(style_id)
        style = source_styles.get(style_id)
        if style is None:
            continue
        ordered.append(style_id)
        for element in style.iter():
            if element.tag in STYLE_LINK_TAGS:
                value = element.attrib.get(q_w("val"))
                if value and value not in seen:
                    queue.append(value)
    return ordered


def unique_style_id(existing: set[str], desired: str) -> str:
    if desired not in existing:
        return desired
    suffix = 2
    while f"{desired}_{suffix}" in existing:
        suffix += 1
    return f"{desired}_{suffix}"


def remap_style_references(elements: list[ET.Element], style_map: dict[str, str]) -> None:
    for root in elements:
        for element in root.iter():
            if element.tag in STYLE_REFERENCE_TAGS or element.tag in STYLE_LINK_TAGS:
                value = element.attrib.get(q_w("val"))
                if value in style_map:
                    element.set(q_w("val"), style_map[value])


def merge_referenced_styles(
    blocks: list[ET.Element],
    src: DocxPackage,
    dst: DocxPackage,
    source_index: int,
) -> dict[str, str]:
    if "word/styles.xml" not in src.entries or "word/styles.xml" not in dst.entries:
        return {}

    src_root = ET.fromstring(src.entries["word/styles.xml"])
    dst_root = ET.fromstring(dst.entries["word/styles.xml"])
    src_styles = styles_by_id(src_root)
    dst_styles = styles_by_id(dst_root)
    dst_existing = set(dst_styles)

    initial_ids = collect_block_style_ids(
        blocks,
        default_style_id(src_root, "paragraph"),
        default_style_id(src_root, "table"),
    )
    copied_ids = collect_style_closure(initial_ids, src_styles)
    style_map: dict[str, str] = {}
    for old_id in copied_ids:
        style_map[old_id] = unique_style_id(dst_existing, f"k{source_index:03d}_{old_id}")
        dst_existing.add(style_map[old_id])

    source_rpr_default = doc_default_pr(src_root, "r")
    source_ppr_default = doc_default_pr(src_root, "p")
    changed = False
    for old_id in copied_ids:
        source_style = src_styles.get(old_id)
        if source_style is None:
            continue
        style_copy = copy.deepcopy(source_style)
        style_copy.set(q_w("styleId"), style_map[old_id])
        style_copy.attrib.pop(q_w("default"), None)
        materialize_source_defaults(style_copy, source_rpr_default, source_ppr_default)
        remap_style_references([style_copy], style_map)
        dst_root.append(style_copy)
        changed = True

    if changed:
        dst.entries["word/styles.xml"] = ET.tostring(dst_root, encoding="utf-8", xml_declaration=True)

    remap_style_references(blocks, style_map)
    return style_map


def remove_internal_markers(blocks: list[ET.Element]) -> None:
    """Drop range markers that become invalid when a middle slice is copied."""
    def visit(parent: ET.Element) -> None:
        for child in list(parent):
            if child.tag in RANGE_MARKER_TAGS:
                parent.remove(child)
            else:
                visit(child)

    for block in blocks:
        visit(block)


def anchor_to_inline(anchor: ET.Element) -> ET.Element:
    inline = ET.Element(qn(WP, "inline"))
    for attr_name in ("distT", "distB", "distL", "distR"):
        value = anchor.attrib.get(qn(WP, attr_name)) or anchor.attrib.get(attr_name)
        if value is not None:
            inline.set(attr_name, value)

    for child_name in ("extent", "effectExtent", "docPr", "cNvGraphicFramePr"):
        child = anchor.find(qn(WP, child_name))
        if child is not None:
            inline.append(copy.deepcopy(child))

    graphic = next((child for child in anchor if child.tag.endswith("}graphic")), None)
    if graphic is not None:
        inline.append(copy.deepcopy(graphic))
    return inline


def convert_floating_drawings_to_inline(blocks: list[ET.Element]) -> int:
    converted = 0
    for block in blocks:
        for drawing in block.iter(q_w("drawing")):
            for anchor in list(drawing.findall(qn(WP, "anchor"))):
                drawing.replace(anchor, anchor_to_inline(anchor))
                converted += 1
    return converted


def normalize_doc_pr_ids(blocks: list[ET.Element], next_doc_pr_id: int) -> int:
    doc_pr_tag = qn(WP, "docPr")
    for block in blocks:
        for element in block.iter(doc_pr_tag):
            element.set("id", str(next_doc_pr_id))
            next_doc_pr_id += 1
    return next_doc_pr_id


def has_relationships(block: ET.Element) -> bool:
    return bool(relationship_ids(block))


def has_math_content(block: ET.Element) -> bool:
    return any(True for _ in block.iter(qn(M, "oMath"))) or any(True for _ in block.iter(qn(M, "oMathPara")))


def has_table_like_content(block: ET.Element) -> bool:
    return block.tag == q_w("tbl")


def is_visual_or_object_block(block: ET.Element) -> bool:
    return has_relationships(block) or has_table_like_content(block) or has_math_content(block)


def is_heading_like(compact: str) -> bool:
    if not compact or len(compact) > 32:
        return False
    if compact.startswith(("一、", "二、", "三、", "四、", "五、", "知识点")):
        return True
    if compact.endswith(("：", ":")):
        return True
    if re.match(r"^(注意|提示|易错|说明)[：:].+", compact):
        return False
    if "：" in compact or ":" in compact:
        return False
    if any(term in compact for term in HEADING_TERMS) and not re.search(r"[。；.!?？．]$", compact):
        return True
    return False


def is_standalone_label(compact: str) -> bool:
    if compact in STANDALONE_LABELS:
        return True
    return bool(re.fullmatch(r"【[^】]{1,16}】[:：]?", compact))


def is_enumerated_item(compact: str) -> bool:
    return bool(re.match(r"^(（?[0-9一二三四五六七八九十]+[）).、]|[①②③④⑤⑥⑦⑧⑨⑩])", compact))


@dataclass
class BlockAnalysis:
    index: int
    block: ET.Element
    text: str
    compact: str
    parent_title: str
    block_type: str
    heading_level: int | None
    is_heading: bool
    is_enumerated: bool
    has_image_or_object: bool
    has_formula: bool
    has_table: bool
    has_keep_marker: bool
    has_drop_marker: bool
    has_soft_drop_marker: bool

    @property
    def has_media(self) -> bool:
        return self.has_image_or_object or self.has_formula or self.has_table


@dataclass
class RefineDecision:
    analysis: BlockAnalysis
    result: str
    reason: str
    confidence: float
    refined_block: ET.Element | None = None
    original_refined_text: str = ""

    @property
    def kept(self) -> bool:
        return self.result in {"保留", "压缩", "待复核"}

    @property
    def media_summary(self) -> str:
        return (
            f"图片/对象:{'是' if self.analysis.has_image_or_object else '否'}；"
            f"公式:{'是' if self.analysis.has_formula else '否'}；"
            f"表格:{'是' if self.analysis.has_table else '否'}"
        )


def heading_level(block: ET.Element) -> int | None:
    compact = normalize_text(block_text(block))
    if not compact or len(compact) > 40:
        return None
    if is_standalone_label(compact):
        return 2
    if compact.startswith(("知识点", "一、", "二、", "三、", "四、", "五、")):
        return 1
    numbered_heading = re.match(r"^[0-9一二三四五六七八九十]+[.、](.+)$", compact)
    if numbered_heading:
        heading_text = numbered_heading.group(1)
        if len(heading_text) <= 24 and not re.search(r"[。；;．.]$", compact):
            return 1
        return None
    parenthesized_heading = re.match(r"^（[0-9一二三四五六七八九十]+）(.+)$", compact)
    if parenthesized_heading:
        heading_text = parenthesized_heading.group(1)
        if len(heading_text) <= 24 and not re.search(r"[。；;．.]$", compact):
            return 2
        return None
    if re.match(r"^[①②③④⑤⑥⑦⑧⑨⑩].+", compact):
        return None
    if re.match(r"^[0-9一二三四五六七八九十]+[）)]", compact):
        return None
    if re.match(r"^[0-9一二三四五六七八九十]+、", compact):
        return 1
    if compact.endswith(("分：", "分类：")):
        return 3
    if compact.endswith(("：", ":")):
        return 2
    if is_visual_or_object_block(block):
        return None
    if is_heading_like(compact):
        return 2
    return None


def block_type_for(block: ET.Element, compact: str, level: int | None) -> str:
    if has_table_like_content(block):
        return "表格"
    if has_math_content(block):
        return "公式"
    if has_relationships(block):
        return "图片/对象"
    if level is not None:
        return "标题"
    if is_enumerated_item(compact):
        return "列表项"
    if not compact:
        return "空白块"
    if any(marker in compact for marker in EXPLANATION_MARKERS):
        return "解释段"
    return "正文段"


def analyze_blocks(blocks: list[ET.Element]) -> list[BlockAnalysis]:
    analyses: list[BlockAnalysis] = []
    heading_stack: dict[int, str] = {}
    for index, block in enumerate(blocks):
        text = block_text(block).strip()
        compact = normalize_text(text)
        level = heading_level(block)
        if level is not None:
            for existing_level in list(heading_stack):
                if existing_level >= level:
                    heading_stack.pop(existing_level, None)
        parent_title = " > ".join(heading_stack[level_key] for level_key in sorted(heading_stack))
        analysis = BlockAnalysis(
            index=index,
            block=block,
            text=text,
            compact=compact,
            parent_title=parent_title,
            block_type=block_type_for(block, compact, level),
            heading_level=level,
            is_heading=level is not None,
            is_enumerated=is_enumerated_item(compact),
            has_image_or_object=has_relationships(block),
            has_formula=has_math_content(block),
            has_table=has_table_like_content(block),
            has_keep_marker=any(marker in compact for marker in KEEP_BLOCK_MARKERS),
            has_drop_marker=any(marker in compact for marker in DROP_BLOCK_MARKERS),
            has_soft_drop_marker=any(marker in compact for marker in DROP_SOFT_MARKERS),
        )
        analyses.append(analysis)
        if level is not None and compact:
            heading_stack[level] = compact
    return analyses


def pure_symbol_text(compact: str) -> bool:
    return bool(compact) and bool(re.fullmatch(r"[A-Za-z0-9∠（）()，,.\s]+", compact))


def is_auxiliary_diagram_residue(analysis: BlockAnalysis, previous_kept: bool) -> bool:
    if not previous_kept or analysis.is_heading or not analysis.compact:
        return False
    if analysis.has_media and len(analysis.compact) <= 60:
        return True
    return bool(pure_symbol_text(analysis.compact) and len(analysis.compact) <= 40)


def has_solution_step(compact: str) -> bool:
    return bool(re.search(r"(第一步|第二步|第三步|步骤[一二三四五六七八九十]?)", compact))


def block_contains_reviewable_conclusion(analysis: BlockAnalysis) -> bool:
    return any(marker in analysis.compact for marker in ("口诀", "定义", "性质", "结论", "公式", "定理", "推论", "判定", "注意"))


def should_compress_text(analysis: BlockAnalysis) -> bool:
    if analysis.has_media or analysis.is_heading:
        return False
    if len(analysis.compact) > 120:
        return True
    return any(marker in analysis.compact for marker in ("特别提示", "解题思路", "方法", "实质", "通常", "需要", "可以"))


def can_safely_compress_media_text(analysis: BlockAnalysis) -> bool:
    return any(
        marker in analysis.compact
        for marker in (
            "【特别提示】在描述反比例函数",
            "由于反比例函数解析式为",
            "多重符号的化简规律",
            "一个具体的数前面有几个正、负号",
        )
    )


def calibrated_review_decision(analysis: BlockAnalysis) -> RefineDecision | None:
    compact = analysis.compact
    if any(compact.startswith(marker) for marker in CALIBRATED_SUPPLEMENT_DROP_STARTS):
        return RefineDecision(analysis, "删除", "复核校准：补充性结构说明与当前核心背诵目标弱相关，删除。", 0.9, None)
    if compact.startswith(("拓展：", "拓展:")) and not any(marker in compact for marker in CORE_EXPANSION_MARKERS):
        return RefineDecision(analysis, "删除", "复核校准：拓展了解类内容未命中核心知识标记，删除。", 0.88, None)
    return None


def decide_refinement(
    analysis: BlockAnalysis,
    *,
    previous_kept: bool,
    suppress_solution_followups: bool,
    seen_texts: set[str],
) -> RefineDecision:
    block_copy = copy.deepcopy(analysis.block)

    if suppress_solution_followups and not analysis.is_heading:
        return RefineDecision(analysis, "删除", "位于已删除的解题思路/过程小节下，按过程性步骤删除。", 0.9, None)

    if not analysis.compact:
        if previous_kept and analysis.has_image_or_object:
            return RefineDecision(analysis, "保留", "空文本图片/对象块跟随上一条知识点保留。", 0.7, block_copy)
        return RefineDecision(analysis, "删除", "空白块，不含可背诵内容。", 0.95, None)

    if pure_symbol_text(analysis.compact) and is_auxiliary_diagram_residue(analysis, previous_kept):
        return RefineDecision(analysis, "保留", "图形/配图标注跟随上一保留知识块保留，避免拆散配图。", 0.76, block_copy)

    if pure_symbol_text(analysis.compact):
        return RefineDecision(analysis, "删除", "仅含字母、数字或符号，缺少独立记忆价值。", 0.8, None)

    calibrated = calibrated_review_decision(analysis)
    if calibrated is not None:
        return calibrated

    if analysis.has_drop_marker and not block_contains_reviewable_conclusion(analysis):
        return RefineDecision(analysis, "删除", "命中例题/解析/证明/解题过程标记，且没有可抽取的结论型知识。", 0.9, None)

    if analysis.has_soft_drop_marker and not analysis.has_keep_marker and not analysis.has_media:
        return RefineDecision(analysis, "删除", "属于观察、情境导入或过程说明，未命中核心知识点标记。", 0.82, None)

    if has_solution_step(analysis.compact) and not any(marker in analysis.compact for marker in ("方法", "规律", "法则")):
        return RefineDecision(analysis, "删除", "步骤化推导/操作过程，非背诵清单主体。", 0.85, None)

    if analysis.has_media:
        if analysis.has_drop_marker and not block_contains_reviewable_conclusion(analysis):
            return RefineDecision(analysis, "删除", "含图片/公式/表格但归属于例题或解题过程。", 0.75, None)
        if can_safely_compress_media_text(analysis):
            refined_block = simplify_block_for_refined(analysis.block, allow_media_text=True)
            if refined_block is not None and normalize_text(block_text(refined_block)) != analysis.compact:
                return RefineDecision(analysis, "压缩", "含公式/对象的长提示段，但已命中安全改写模板；保留核心结论并压缩。", 0.78, refined_block)
        return RefineDecision(analysis, "保留", "含图片、公式、表格或结构图；均衡压缩下默认保留，避免误删结论型图示。", 0.82, block_copy)

    if analysis.compact in seen_texts and not analysis.is_heading:
        return RefineDecision(analysis, "删除", "与前文纯文本内容重复。", 0.78, None)

    if analysis.is_heading:
        return RefineDecision(analysis, "保留", "知识层级标题；若后续没有有效内容，会在孤立标题清理阶段删除。", 0.7, block_copy)

    if analysis.has_keep_marker:
        if should_compress_text(analysis):
            refined_block = simplify_block_for_refined(analysis.block)
            if refined_block is not None and normalize_text(block_text(refined_block)) != analysis.compact:
                return RefineDecision(analysis, "压缩", "命中核心知识点，同时为长解释段；保留核心结论并压缩表述。", 0.76, refined_block)
        return RefineDecision(analysis, "保留", "命中定义、性质、公式、分类、结论等背诵价值标记。", 0.88, block_copy)

    if analysis.is_enumerated and previous_kept and len(analysis.compact) <= 160:
        return RefineDecision(analysis, "保留", "短列表项跟随前一知识点，作为条件/分类/结论补充保留。", 0.72, block_copy)

    if should_compress_text(analysis):
        refined_block = simplify_block_for_refined(analysis.block)
        if refined_block is not None and normalize_text(block_text(refined_block)) != analysis.compact:
            return RefineDecision(analysis, "压缩", "解释性长段，压缩为可背诵的核心句。", 0.65, refined_block)

    return RefineDecision(analysis, "待复核", "未命中明确删/留规则；均衡压缩下先保留，供人工校准。", 0.55, block_copy)


def decision_has_content(decision: RefineDecision) -> bool:
    if not decision.kept:
        return False
    if decision.analysis.heading_level is not None:
        if (
            decision.result == "压缩"
            and decision.refined_block is not None
            and normalize_text(block_text(decision.refined_block)) != decision.analysis.compact
        ):
            return True
        return bool(
            decision.analysis.has_media
            and decision.analysis.compact
            and not is_standalone_label(decision.analysis.compact)
        )
    return bool(decision.analysis.compact or decision.analysis.has_media)


def prune_orphan_heading_decisions(decisions: list[RefineDecision]) -> int:
    removed = 0
    changed = True
    while changed:
        changed = False
        for index, decision in enumerate(decisions):
            if not decision.kept or decision.analysis.heading_level is None:
                continue
            if decision_has_content(decision):
                continue
            level = decision.analysis.heading_level
            has_child_content = False
            for following in decisions[index + 1 :]:
                following_level = following.analysis.heading_level
                if following.kept and following_level is not None and following_level <= level:
                    break
                if decision_has_content(following):
                    has_child_content = True
                    break
            if not has_child_content:
                decision.result = "删除"
                decision.reason = "下级有效内容已全部删除，清理孤立标题。"
                decision.confidence = 0.9
                decision.refined_block = None
                removed += 1
                changed = True
    return removed


def replace_paragraph_text(paragraph: ET.Element, text: str) -> None:
    runs = paragraph.findall(q_w("r"))
    run_properties = None
    for run_candidate in runs:
        existing_properties = run_candidate.find(q_w("rPr"))
        if existing_properties is not None:
            run_properties = copy.deepcopy(existing_properties)
            break
    paragraph_properties = paragraph.find(q_w("pPr"))
    for child in list(paragraph):
        if child is not paragraph_properties:
            paragraph.remove(child)
    run = ET.SubElement(paragraph, q_w("r"))
    if run_properties is not None:
        run.append(run_properties)
    text_el = ET.SubElement(run, q_w("t"))
    text_el.text = text
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        text_el.set(qn(XML, "space"), "preserve")


CIRCLED_NUMBER_BY_VALUE = {
    1: "①",
    2: "②",
    3: "③",
    4: "④",
    5: "⑤",
    6: "⑥",
    7: "⑦",
    8: "⑧",
    9: "⑨",
    10: "⑩",
}
CIRCLED_VALUE_BY_NUMBER = {value: key for key, value in CIRCLED_NUMBER_BY_VALUE.items()}
CHINESE_NUMBER_BY_VALUE = {
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
    10: "十",
    11: "十一",
    12: "十二",
    13: "十三",
    14: "十四",
    15: "十五",
    16: "十六",
    17: "十七",
    18: "十八",
    19: "十九",
    20: "二十",
}
CHINESE_VALUE_BY_NUMBER = {value: key for key, value in CHINESE_NUMBER_BY_VALUE.items()}
EAST_ASIAN_NUMBER_FORMATS = {
    "chineseCounting",
    "chineseCountingThousand",
    "chineseLegalSimplified",
    "japaneseCounting",
    "ideographDigital",
}


def first_paragraph(block: ET.Element) -> ET.Element | None:
    if block.tag == q_w("p"):
        return block
    return next(block.iter(q_w("p")), None)


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(text.text or "" for text in paragraph.iter(q_w("t")))


def set_text_node_space(text_el: ET.Element) -> None:
    text = text_el.text or ""
    space_key = qn(XML, "space")
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        text_el.set(space_key, "preserve")
    else:
        text_el.attrib.pop(space_key, None)


def replace_paragraph_prefix(paragraph: ET.Element, old_length: int, new_prefix: str) -> bool:
    text_nodes = list(paragraph.iter(q_w("t")))
    if not text_nodes or old_length <= 0:
        return False
    remaining = old_length
    inserted = False
    for text_el in text_nodes:
        current = text_el.text or ""
        if remaining == 0:
            if not inserted:
                text_el.text = new_prefix + current
                set_text_node_space(text_el)
                return True
            break
        if remaining >= len(current):
            if remaining == len(current) and not inserted:
                text_el.text = new_prefix
                inserted = True
                remaining = 0
            else:
                text_el.text = ""
                remaining -= len(current)
            set_text_node_space(text_el)
            continue
        text_el.text = (new_prefix if not inserted else "") + current[remaining:]
        inserted = True
        remaining = 0
        set_text_node_space(text_el)
        return True
    return inserted and remaining == 0


def prepend_paragraph_text(paragraph: ET.Element, prefix: str) -> bool:
    text_nodes = list(paragraph.iter(q_w("t")))
    if text_nodes:
        text_nodes[0].text = prefix + (text_nodes[0].text or "")
        set_text_node_space(text_nodes[0])
        return True

    run = ET.SubElement(paragraph, q_w("r"))
    text_el = ET.SubElement(run, q_w("t"))
    text_el.text = prefix
    set_text_node_space(text_el)
    return True


@dataclass(frozen=True)
class NumberPrefix:
    kind: str
    value: int
    length: int
    replacement: str


def manual_number_prefix(text: str, new_value: int) -> NumberPrefix | None:
    match = re.match(r"^(\s*)([一二三四五六七八九十]{1,3})(、)(\s*)", text)
    if match:
        lead, old, separator, spacing = match.groups()
        if old not in CHINESE_VALUE_BY_NUMBER or new_value not in CHINESE_NUMBER_BY_VALUE:
            return None
        return NumberPrefix(
            "chinese_comma",
            CHINESE_VALUE_BY_NUMBER[old],
            match.end(),
            f"{lead}{CHINESE_NUMBER_BY_VALUE[new_value]}{separator}{spacing}",
        )

    match = re.match(r"^(\s*)(\d+)([.．])(?!\d)(\s*)", text)
    if match:
        lead, _old, separator, spacing = match.groups()
        return NumberPrefix("arabic_dot", int(_old), match.end(), f"{lead}{new_value}{separator}{spacing}")

    match = re.match(r"^(\s*)(\d+)(、)(\s*)", text)
    if match:
        lead, _old, separator, spacing = match.groups()
        return NumberPrefix("arabic_comma", int(_old), match.end(), f"{lead}{new_value}{separator}{spacing}")

    match = re.match(r"^(\s*)([（(])(\d+)([）)])(\s*)", text)
    if match:
        lead, left, _old, right, spacing = match.groups()
        return NumberPrefix("paren", int(_old), match.end(), f"{lead}{left}{new_value}{right}{spacing}")

    match = re.match(r"^(\s*)(\d+)([）)])(\s*)", text)
    if match:
        lead, _old, right, spacing = match.groups()
        return NumberPrefix("bare_paren", int(_old), match.end(), f"{lead}{new_value}{right}{spacing}")

    match = re.match(r"^(\s*)([①②③④⑤⑥⑦⑧⑨⑩])(\s*)", text)
    if match:
        lead, old, spacing = match.groups()
        if new_value not in CIRCLED_NUMBER_BY_VALUE:
            return None
        return NumberPrefix(
            "circled",
            CIRCLED_VALUE_BY_NUMBER[old],
            match.end(),
            f"{lead}{CIRCLED_NUMBER_BY_VALUE[new_value]}{spacing}",
        )

    return None


def should_renumber_manual_item(decision: RefineDecision, prefix: NumberPrefix) -> bool:
    if decision.refined_block is None or not decision.kept:
        return False
    if prefix.kind in {"circled", "chinese_comma"}:
        return False
    if decision.analysis.has_table:
        return False
    return not decision.analysis.is_heading


def numbering_parent_key(parent_title: str) -> str:
    parts = [part.strip() for part in parent_title.split(" > ") if part.strip()]
    if not parts:
        return ""
    key_parts: list[str] = []
    for index, part in enumerate(parts):
        if index > 0 and manual_number_prefix(part, 1) is not None:
            break
        key_parts.append(part)
    return " > ".join(key_parts)


def renumber_refined_manual_items(decisions: list[RefineDecision]) -> int:
    counters: dict[tuple[str, str], int] = {}
    changed = 0
    for decision in decisions:
        block = decision.refined_block
        if block is None or not decision.kept:
            continue
        paragraph = first_paragraph(block)
        if paragraph is None:
            continue
        text = paragraph_text(paragraph)
        probe = manual_number_prefix(text, 1)
        if probe is None:
            continue

        key = (numbering_parent_key(decision.analysis.parent_title), probe.kind)
        if not should_renumber_manual_item(decision, probe):
            counters[key] = max(counters.get(key, 0), probe.value)
            continue

        next_value = counters.get(key, 0) + 1
        counters[key] = next_value
        prefix = manual_number_prefix(text, next_value)
        if prefix is None or prefix.value == next_value:
            continue
        if replace_paragraph_prefix(paragraph, prefix.length, prefix.replacement):
            changed += 1
    return changed


def paragraph_num_pr(paragraph: ET.Element) -> ET.Element | None:
    return paragraph.find(f"{q_w('pPr')}/{q_w('numPr')}")


def remove_paragraph_numbering(paragraph: ET.Element) -> None:
    p_pr = paragraph.find(q_w("pPr"))
    if p_pr is None:
        return
    num_pr = p_pr.find(q_w("numPr"))
    if num_pr is not None:
        p_pr.remove(num_pr)


def numbering_format_by_num_id(dst: DocxPackage) -> dict[tuple[str, str], tuple[str, str]]:
    if "word/numbering.xml" not in dst.entries:
        return {}
    root = ET.fromstring(dst.entries["word/numbering.xml"])
    abstract_by_id = {
        item.attrib.get(q_w("abstractNumId")): item
        for item in root.findall(q_w("abstractNum"))
        if item.attrib.get(q_w("abstractNumId")) is not None
    }
    result: dict[tuple[str, str], tuple[str, str]] = {}
    for num in root.findall(q_w("num")):
        num_id = num.attrib.get(q_w("numId"))
        abs_id_el = num.find(q_w("abstractNumId"))
        if not num_id or abs_id_el is None:
            continue
        abstract = abstract_by_id.get(abs_id_el.attrib.get(q_w("val")))
        if abstract is None:
            continue
        for level in abstract.findall(q_w("lvl")):
            ilvl = level.attrib.get(q_w("ilvl"), "0")
            fmt_el = level.find(q_w("numFmt"))
            text_el = level.find(q_w("lvlText"))
            result[(num_id, ilvl)] = (
                fmt_el.attrib.get(q_w("val"), "") if fmt_el is not None else "",
                text_el.attrib.get(q_w("val"), "") if text_el is not None else "",
            )
    return result


def normalize_refined_chinese_numbering(blocks: list[ET.Element], dst: DocxPackage) -> int:
    numbering_formats = numbering_format_by_num_id(dst)
    major_counter = 0
    decimal_counters: dict[str, int] = {}
    changed = 0
    for block in blocks:
        if block.tag == q_w("tbl"):
            continue
        paragraph = first_paragraph(block)
        if paragraph is None:
            continue
        text = paragraph_text(paragraph)
        if not normalize_text(text):
            continue

        num_pr = paragraph_num_pr(paragraph)
        if num_pr is not None:
            ilvl_el = num_pr.find(q_w("ilvl"))
            num_id_el = num_pr.find(q_w("numId"))
            ilvl = ilvl_el.attrib.get(q_w("val"), "0") if ilvl_el is not None else "0"
            num_id = num_id_el.attrib.get(q_w("val")) if num_id_el is not None else None
            fmt, _lvl_text = numbering_formats.get((num_id or "", ilvl), ("", ""))
            if fmt in EAST_ASIAN_NUMBER_FORMATS and ilvl == "0":
                major_counter += 1
                if major_counter in CHINESE_NUMBER_BY_VALUE:
                    remove_paragraph_numbering(paragraph)
                    if prepend_paragraph_text(paragraph, f"{CHINESE_NUMBER_BY_VALUE[major_counter]}、"):
                        changed += 1
                continue
            if fmt == "decimal" and ilvl == "0" and manual_number_prefix(text, 1) is None:
                suffix = _lvl_text.replace("%1", "") or "."
                key = suffix
                decimal_counters[key] = decimal_counters.get(key, 0) + 1
                remove_paragraph_numbering(paragraph)
                if prepend_paragraph_text(paragraph, f"{decimal_counters[key]}{suffix}"):
                    changed += 1
                continue

        prefix = manual_number_prefix(text, major_counter + 1)
        if prefix and prefix.kind == "chinese_comma":
            major_counter += 1
            if prefix.value != major_counter:
                updated = manual_number_prefix(text, major_counter)
                if updated and replace_paragraph_prefix(paragraph, updated.length, updated.replacement):
                    changed += 1
    return changed


def simplify_text_for_memory(text: str) -> str:
    stripped = re.sub(r"\s+", " ", text).strip()
    compact = normalize_text(stripped)
    replacements = [
        ("【特别提示】在描述反比例函数", "【特别提示】反比例函数的增减性必须限定“在每个象限内”，不能笼统说整个函数随 x 增大而增/减。"),
        ("由于反比例函数解析式为", "求反比例函数解析式：将图象上一点坐标代入，先求 k，再写解析式。"),
        ("圆的中心对称性：将圆绕圆心旋转180°", "圆的中心对称性：圆绕圆心旋转180°与自身重合，对称中心是圆心；圆具有旋转不变性。"),
        ("【补充】圆的一条弧", "【补充】同一条弧对应一个圆心角、无数个圆周角；圆周角度数有两个，和为180°。"),
        ("数轴上的任何一个点都对应一个实数", "实数与数轴上的点一一对应。"),
        ("一个具体的数前面有几个正、负号", "4. 多重符号化简规律：负号个数为奇数时结果为负，负号个数为偶数时结果为正，简记“奇负偶正”。"),
    ]
    for needle, replacement in replacements:
        if needle in compact:
            return replacement

    if compact.startswith("（1）单项式的乘法法则的实质"):
        return ""
    if compact.startswith("（1）单项式与多项式相乘的计算方法"):
        return ""
    if compact.startswith("（3）对混合运算"):
        return "（3）混合运算先乘方、再乘除、后加减；有同类项要合并。"
    if compact.startswith("目测法"):
        return "角度比较方法：目测法、度量法、叠合法。"

    if len(compact) <= 120:
        return stripped

    sentence_parts = re.split(r"(?<=[。；;．.])", stripped)
    kept: list[str] = []
    for sentence in sentence_parts:
        sentence_compact = normalize_text(sentence)
        if not sentence_compact:
            continue
        if any(marker in sentence_compact for marker in ("因为", "所以", "这说明", "实质是", "运用这些", "比如")):
            continue
        if any(marker in sentence_compact for marker in KEEP_BLOCK_MARKERS) or is_enumerated_item(sentence_compact):
            kept.append(sentence.strip())
        if len(kept) >= 2:
            break
    if kept:
        return "".join(kept)
    return stripped


def simplify_block_for_refined(block: ET.Element, *, allow_media_text: bool = False) -> ET.Element | None:
    refined = copy.deepcopy(block)
    if is_visual_or_object_block(refined) and not allow_media_text:
        return refined
    paragraphs = list(refined.iter(q_w("p")))
    if len(paragraphs) != 1:
        return refined
    original = block_text(refined)
    simplified = simplify_text_for_memory(original)
    if not simplified:
        return None
    if simplified != re.sub(r"\s+", " ", original).strip():
        replace_paragraph_text(paragraphs[0], simplified)
    return refined


ENHANCED_DELETE_STARTS = (
    "5=2+3；6=2×3",
    "(x+2)(x+3)",
    "x2+5x+6",
    "x        ",
    "12x2",
    "4x           ",
    "3x          ",
    "验证：",
    "∴原式",
    "实际问题中反比例函数的图象",
    "圆的旋转不变性是其他中心对称图形所没有的性质",
    "数轴上的任何一个点都对应一个实数",
    "（1）单项式的乘法法则的实质",
    "（1）单项式与多项式相乘的计算方法",
    "①对“中”",
    "②重合",
    "③读数",
    "如图，是的平分线",
    "反过来：",
    "如图，射线",
    "例：",
    "第一步：",
    "第二步：",
    "第三步：",
    "①画图",
    "②表示线段",
    "③找等量关系",
    "④列式求解",
    "P：",
    "Q：",
    "①Q",
    "②Q",
    "③Q",
    "等量关系：",
    "即t=",
    "Q点",
)


def enhanced_delete_text(analysis: BlockAnalysis) -> bool:
    compact = analysis.compact
    if any(compact.startswith(prefix) for prefix in ENHANCED_DELETE_STARTS):
        return True
    if ("首尾分解" in compact and "交叉相乘" in compact) and compact.count("首尾分解") > 1:
        return False
    if is_enumerated_item(compact) and "方程" in compact and "实数根" in compact:
        return True
    if "验证：" in compact or "∴原式" in compact:
        return True
    if "→ (" in compact or "→(" in compact:
        return True
    return False


def enhanced_simplify_text_for_memory(text: str) -> str:
    stripped = re.sub(r"\s+", " ", text).strip()
    compact = normalize_text(stripped)
    if "首尾分解" in compact and "交叉相乘" in compact:
        return "十字相乘法口诀：首尾分解，交叉相乘，求和凑中，横向写因式。"
    replacements = [
        (
            "与时间有关的动点问题解题思路",
            "动点问题思路：画图标方向和速度，用t表示线段，找等量关系，列式求解；多动点要找临界时间并分段讨论。",
        ),
        (
            "多个动点",
            "多动点注意：分别找各动点临界时间并综合分段；某点停止后，对应线段表达式为常数。",
        ),
        (
            "首尾分解，交叉相乘，求和凑中",
            "十字相乘法口诀：首尾分解，交叉相乘，求和凑中，横向写因式。",
        ),
        (
            "二次项系数为±1",
            "二次项系数为±1：先拆常数项，再交叉相乘凑一次项。",
        ),
        (
            "一般的二次三项式",
            "一般二次三项式：同时拆二次项和常数项，交叉相乘凑一次项。",
        ),
        (
            "对于二次函数：",
            "二次函数图象判系数：开口上a>0、下a<0；对称轴左侧a、b同号，右侧异号；交y轴上c>0、原点c=0、下c<0；交x轴两点Δ>0、一点Δ=0、无交点Δ<0；特殊点函数值判代数式符号。",
        ),
        (
            "圆的中心对称性",
            "圆的对称与旋转不变性：圆是中心对称图形，对称中心为圆心；绕圆心旋转任意角度都能与自身重合。",
        ),
        (
            "一条弧所对的圆周角等于它所对的圆心角的一半",
            "圆周角定理：同弧所对圆周角等于圆心角的一半。",
        ),
        (
            "用量角器测量角的度数方法",
            "量角器测角：顶点对中心，一边与零刻度线重合，读另一边刻度。",
        ),
        (
            "定义：从一个角的顶点引出",
            "角平分线：从角顶点引出并把角分成两个相等角的射线。",
        ),
        (
            "单项式与单项式相乘",
            "单项式乘法：系数相乘，相同字母分别相乘，只在一个单项式里的字母连同指数作为积的因式。",
        ),
        (
            "单项式与多项式相乘，就是用单项式去乘多项式的每一项",
            "单项式乘多项式：用单项式乘多项式每一项，再把积相加。",
        ),
        (
            "叫做一元二次方程根的判别式",
            "一元二次方程根的判别式：Δ=b²-4ac；Δ>0有两个不等实根，Δ=0有两个相等实根，Δ<0无实根。",
        ),
        (
            "像2和",
            "1. 相反数：只有符号不同的两个数互为相反数。",
        ),
        (
            "几何意义：相反数所表示的点",
            "2. 相反数几何意义：在数轴原点两侧，且到原点距离相等。",
        ),
        (
            "求数、字母的相反数的方法",
            "3. 求相反数：在数或字母前加“-”号。",
        ),
        (
            "数轴上表示数",
            "1. 绝对值：数轴上表示数a的点到原点的距离，记作|a|。",
        ),
        (
            "一个正数的绝对值是它本身",
            "2. 绝对值性质：正数的绝对值是本身，负数的绝对值是相反数，0的绝对值是0。",
        ),
        (
            "对于数轴上的任意两个点",
            "实数大小：数轴上右边的点表示的数更大。",
        ),
        (
            "正实数大于",
            "实数大小：正数>0，负数<0；两个负数绝对值大的反而小。",
        ),
        (
            "一个具体的数前面有几个正、负号",
            "4. 多重符号化简规律：负号个数为奇数时结果为负，负号个数为偶数时结果为正，简记“奇负偶正”。",
        ),
        (
            "目测法：如图",
            "1. 目测法：直接观察比较角的大小。",
        ),
        (
            "度量法：通过测量角的度数",
            "2. 度量法：测量角的度数比较大小。",
        ),
        (
            "叠合法：将两个角的顶点及一条边重合",
            "叠合法：顶点和一边重合，另一边放在同侧比较大小。",
        ),
    ]
    for needle, replacement in replacements:
        if needle in compact:
            return replacement

    if compact.startswith("（2）运算的结果仍为单项式"):
        return "（2）结果仍为单项式，由系数、字母和字母指数三部分组成。"
    if compact.startswith("（3）三个或三个以上的单项式"):
        return "（3）多个单项式相乘同样适用该法则。"
    if compact.startswith("（2）单项式与多项式的乘积仍是一个多项式"):
        return "（2）乘积仍为多项式，项数与原多项式相同。"
    if compact.startswith("（3）对混合运算"):
        return "（3）混合运算先乘方、再乘除、后加减；有同类项要合并。"
    if compact.startswith("（1）对于任一有理数"):
        return "（1）任一有理数a都有|a|≥0。"
    if compact.startswith("（2）若"):
        return "（2）|a|=a时a≥0；|a|=-a时a≤0。"
    if compact.startswith("注意：二次项系数为-1"):
        return "注意：二次项系数为-1时，先提出“-”再用十字相乘法。"

    return simplify_text_for_memory(text)


def simplify_block_for_enhanced(block: ET.Element, *, allow_media_text: bool = False) -> ET.Element | None:
    refined = copy.deepcopy(block)
    if is_visual_or_object_block(refined) and not allow_media_text:
        return refined
    paragraphs = list(refined.iter(q_w("p")))
    original = block_text(refined)
    simplified = enhanced_simplify_text_for_memory(original)
    if not simplified:
        return None
    if len(paragraphs) != 1 and refined.tag != q_w("p"):
        return refined
    if simplified != re.sub(r"\s+", " ", original).strip():
        replace_paragraph_text(refined if refined.tag == q_w("p") else paragraphs[0], simplified)
    return refined


def should_enhanced_compress_text(analysis: BlockAnalysis) -> bool:
    if analysis.has_media or analysis.is_heading:
        return False
    if enhanced_simplify_text_for_memory(analysis.text) != re.sub(r"\s+", " ", analysis.text).strip():
        return True
    if len(analysis.compact) > 80:
        return True
    return any(marker in analysis.compact for marker in ("方法", "实质", "通常", "需要", "可以", "如图"))


def can_safely_enhance_media_text(analysis: BlockAnalysis) -> bool:
    if can_safely_compress_media_text(analysis):
        return True
    safe_formula_text = any(
        marker in analysis.compact
        for marker in (
            "叫做一元二次方程根的判别式",
            "像2和",
            "几何意义：相反数",
            "求数、字母的相反数",
            "数轴上表示数",
            "一个正数的绝对值是它本身",
            "定义：从一个角的顶点引出",
        )
    )
    if safe_formula_text:
        return True
    if analysis.has_image_or_object:
        return False
    return False


def decide_conservative_enhanced_refinement(
    analysis: BlockAnalysis,
    *,
    previous_kept: bool,
    suppress_solution_followups: bool,
    seen_texts: set[str],
) -> RefineDecision:
    block_copy = copy.deepcopy(analysis.block)

    if suppress_solution_followups and not analysis.is_heading:
        return RefineDecision(analysis, "删除", "位于已删除的解题思路/过程小节下，保守增强压缩中继续删除过程性步骤。", 0.9, None)

    if not analysis.compact:
        if previous_kept and analysis.has_image_or_object:
            return RefineDecision(analysis, "保留", "空文本图片/对象块跟随上一条保留知识点。", 0.7, block_copy)
        return RefineDecision(analysis, "删除", "空白块，不含可背诵内容。", 0.95, None)

    if pure_symbol_text(analysis.compact) and is_auxiliary_diagram_residue(analysis, previous_kept):
        return RefineDecision(analysis, "保留", "图形/配图标注跟随上一保留知识块保留，避免拆散配图。", 0.76, block_copy)

    if pure_symbol_text(analysis.compact):
        return RefineDecision(analysis, "删除", "仅含字母、数字或符号，缺少独立记忆价值。", 0.8, None)

    calibrated = calibrated_review_decision(analysis)
    if calibrated is not None:
        return calibrated

    if analysis.compact.startswith("与时间有关的动点问题解题思路"):
        refined_block = simplify_block_for_enhanced(analysis.block)
        if refined_block is not None:
            return RefineDecision(analysis, "压缩", "保守增强压缩：动点问题解题步骤合并为一般思路。", 0.82, refined_block)

    delete_formula_expansion = (
        is_enumerated_item(analysis.compact) and "方程" in analysis.compact and "实数根" in analysis.compact
    )
    delete_process_formula = any(
        marker in analysis.compact
        for marker in ("即t=", "Q点", "等量关系：", "验证：", "∴原式")
    )
    if enhanced_delete_text(analysis) and (not analysis.has_image_or_object or delete_formula_expansion or delete_process_formula):
        return RefineDecision(analysis, "删除", "保守增强压缩：解释、步骤或重复展开已被上级结论覆盖，删除。", 0.86, None)

    if analysis.has_drop_marker and not block_contains_reviewable_conclusion(analysis):
        return RefineDecision(analysis, "删除", "命中例题/解析/证明/解题过程标记，且没有可抽取的结论型知识。", 0.9, None)

    if analysis.has_soft_drop_marker and not analysis.has_keep_marker and not analysis.has_media:
        return RefineDecision(analysis, "删除", "属于观察、情境导入或过程说明，未命中核心知识点标记。", 0.82, None)

    if has_solution_step(analysis.compact) and not any(marker in analysis.compact for marker in ("方法", "规律", "法则")):
        return RefineDecision(analysis, "删除", "步骤化推导/操作过程，非背诵清单主体。", 0.85, None)

    if analysis.has_media:
        if analysis.has_drop_marker and not block_contains_reviewable_conclusion(analysis):
            return RefineDecision(analysis, "删除", "含图片/公式/表格但归属于例题或解题过程。", 0.75, None)
        if can_safely_enhance_media_text(analysis):
            refined_block = simplify_block_for_enhanced(analysis.block, allow_media_text=True)
            if refined_block is not None and normalize_text(block_text(refined_block)) != analysis.compact:
                return RefineDecision(analysis, "压缩", "保守增强压缩：含对象长提示命中安全改写模板，保留核心结论。", 0.78, refined_block)
        return RefineDecision(analysis, "保留", "含图片、公式、表格或结构图；保守增强压缩下仍默认保留结论型图示。", 0.82, block_copy)

    if analysis.compact in seen_texts and not analysis.is_heading:
        return RefineDecision(analysis, "删除", "与前文纯文本内容重复。", 0.78, None)

    if analysis.is_heading and not is_standalone_label(analysis.compact):
        refined_block = simplify_block_for_enhanced(analysis.block)
        if refined_block is not None and normalize_text(block_text(refined_block)) != analysis.compact:
            return RefineDecision(analysis, "压缩", "保守增强压缩：方法类小标题改写为可背结论句。", 0.76, refined_block)

    if analysis.is_heading:
        return RefineDecision(analysis, "保留", "知识层级标题；若后续没有有效内容，会在孤立标题清理阶段删除。", 0.7, block_copy)

    if should_enhanced_compress_text(analysis):
        refined_block = simplify_block_for_enhanced(analysis.block)
        if refined_block is None:
            return RefineDecision(analysis, "删除", "保守增强压缩：长解释或方法展开删去，只保留核心结论。", 0.82, None)
        if normalize_text(block_text(refined_block)) != analysis.compact:
            return RefineDecision(analysis, "压缩", "保守增强压缩：保留结论、条件或适用范围，压缩解释展开。", 0.78, refined_block)

    if analysis.has_keep_marker:
        return RefineDecision(analysis, "保留", "命中定义、性质、公式、分类、结论等背诵价值标记。", 0.86, block_copy)

    if analysis.is_enumerated and previous_kept and len(analysis.compact) <= 120:
        return RefineDecision(analysis, "保留", "短列表项跟随前一知识点，作为条件/分类/结论补充保留。", 0.68, block_copy)

    return RefineDecision(analysis, "保留", "保守增强压缩下模糊内容先保留，避免误删知识点。", 0.58, block_copy)


def refine_blocks_conservative_enhanced(blocks: list[ET.Element]) -> tuple[list[ET.Element], dict[str, int], list[RefineDecision]]:
    analyses = analyze_blocks(blocks)
    decisions: list[RefineDecision] = []
    seen_texts: set[str] = set()
    previous_kept = False
    suppress_solution_followups = False
    for analysis in analyses:
        if suppress_solution_followups and analysis.is_heading:
            suppress_solution_followups = False
        decision = decide_conservative_enhanced_refinement(
            analysis,
            previous_kept=previous_kept,
            suppress_solution_followups=suppress_solution_followups,
            seen_texts=seen_texts,
        )
        if decision.kept and analysis.compact and not analysis.has_media and not analysis.is_heading:
            seen_texts.add(analysis.compact)
        if decision.kept:
            previous_kept = True
        else:
            if "解题思路" in analysis.compact or "解题过程" in analysis.compact:
                suppress_solution_followups = True
            previous_kept = False
        decisions.append(decision)

    orphan_headings = prune_orphan_heading_decisions(decisions)
    renumbered = renumber_refined_manual_items(decisions)
    refined = [decision.refined_block for decision in decisions if decision.refined_block is not None and decision.kept]
    removed = sum(1 for decision in decisions if decision.result == "删除")
    duplicates = sum(1 for decision in decisions if "重复" in decision.reason)
    simplified = sum(1 for decision in decisions if decision.result == "压缩")
    review = sum(1 for decision in decisions if decision.result == "待复核")
    return refined, {
        "removed_blocks": removed,
        "duplicate_blocks": duplicates,
        "simplified_blocks": simplified,
        "orphan_heading_blocks": orphan_headings,
        "renumbered_blocks": renumbered,
        "review_blocks": review,
        "kept_blocks": len(refined),
    }, decisions


def refine_blocks(blocks: list[ET.Element]) -> tuple[list[ET.Element], dict[str, int], list[RefineDecision]]:
    analyses = analyze_blocks(blocks)
    decisions: list[RefineDecision] = []
    seen_texts: set[str] = set()
    previous_kept = False
    suppress_solution_followups = False
    for analysis in analyses:
        if suppress_solution_followups and analysis.is_heading:
            suppress_solution_followups = False
        decision = decide_refinement(
            analysis,
            previous_kept=previous_kept,
            suppress_solution_followups=suppress_solution_followups,
            seen_texts=seen_texts,
        )
        if decision.kept and analysis.compact and not analysis.has_media and not analysis.is_heading:
            seen_texts.add(analysis.compact)
        if decision.kept:
            previous_kept = True
        else:
            if "解题思路" in analysis.compact or "解题过程" in analysis.compact:
                suppress_solution_followups = True
            previous_kept = False
        decisions.append(decision)

    orphan_headings = prune_orphan_heading_decisions(decisions)
    renumbered = renumber_refined_manual_items(decisions)
    refined = [decision.refined_block for decision in decisions if decision.refined_block is not None and decision.kept]
    removed = sum(1 for decision in decisions if decision.result == "删除")
    duplicates = sum(1 for decision in decisions if "重复" in decision.reason)
    simplified = sum(1 for decision in decisions if decision.result == "压缩")
    review = sum(1 for decision in decisions if decision.result == "待复核")
    return refined, {
        "removed_blocks": removed,
        "duplicate_blocks": duplicates,
        "simplified_blocks": simplified,
        "orphan_heading_blocks": orphan_headings,
        "renumbered_blocks": renumbered,
        "review_blocks": review,
        "kept_blocks": len(refined),
    }, decisions


def ensure_first_child(parent: ET.Element, tag: str) -> ET.Element:
    child = parent.find(tag)
    if child is not None:
        return child
    child = ET.Element(tag)
    parent.insert(0, child)
    return child


def apply_light_blue_shading_to_pr(properties: ET.Element, fill: str = "DDEBFF") -> None:
    for existing in list(properties.findall(q_w("shd"))):
        properties.remove(existing)
    shading = ET.Element(q_w("shd"))
    shading.set(q_w("val"), "clear")
    shading.set(q_w("color"), "auto")
    shading.set(q_w("fill"), fill)
    properties.append(shading)


def mark_block_as_deleted_in_refined(block: ET.Element) -> None:
    for paragraph in block.iter(q_w("p")):
        apply_light_blue_shading_to_pr(ensure_first_child(paragraph, q_w("pPr")))
    for run in block.iter(q_w("r")):
        apply_light_blue_shading_to_pr(ensure_first_child(run, q_w("rPr")))
    for table in block.iter(q_w("tbl")):
        apply_light_blue_shading_to_pr(ensure_first_child(table, q_w("tblPr")))
    for cell in block.iter(q_w("tc")):
        apply_light_blue_shading_to_pr(ensure_first_child(cell, q_w("tcPr")))


def marked_full_blocks(
    full_blocks: list[ET.Element],
    decisions: list[RefineDecision],
) -> tuple[list[ET.Element], int]:
    marked: list[ET.Element] = []
    marked_count = 0
    for block, decision in zip(full_blocks, decisions, strict=True):
        clone = copy.deepcopy(block)
        if decision.result in {"删除", "压缩"}:
            mark_block_as_deleted_in_refined(clone)
            marked_count += 1
        marked.append(clone)
    return marked, marked_count


def append_source_section(
    dst: DocxPackage,
    source: DocxPackage,
    source_index: int,
    children: list[ET.Element],
    *,
    title: str,
    page_break_before: bool,
    doc_pr_state: dict[str, int],
    normalize_chinese_numbering: bool = False,
) -> int:
    cloned = [
        copy.deepcopy(child)
        for child in children
        if child.tag != q_w("sectPr") and child.tag not in RANGE_MARKER_TAGS
    ]
    remove_internal_markers(cloned)
    style_map = merge_referenced_styles(cloned, source, dst, source_index)
    merge_numbering(cloned, source, dst, style_map)
    if normalize_chinese_numbering:
        normalize_refined_chinese_numbering(cloned, dst)
        convert_floating_drawings_to_inline(cloned)
    doc_pr_state["next"] = normalize_doc_pr_ids(cloned, doc_pr_state["next"])
    ctx = CopyContext(source, dst, f"klist{source_index:03d}")
    remap_relationships(cloned, ctx)
    dst.body.append(make_paragraph(title, bold=True, size=28, page_break_before=page_break_before))
    for child in cloned:
        dst.body.append(child)
    return len(cloned)


def validate_relationship_targets(docx: Path) -> dict[str, object]:
    with ZipFile(docx, "r") as package:
        bad = package.testzip()
        if bad:
            raise ValueError(f"Bad zip member in {docx.name}: {bad}")
        names = set(package.namelist())
        document = ET.fromstring(package.read("word/document.xml"))
        rels = ET.fromstring(package.read("word/_rels/document.xml.rels"))
        rels_by_id = {rel.attrib["Id"]: dict(rel.attrib) for rel in rels}
        used_ids = set()
        for el in document.iter():
            for value in el.attrib.values():
                if re.fullmatch(r"rId\d+", value):
                    used_ids.add(value)
        missing = []
        for rel_id in sorted(used_ids, key=lambda rid: int(rid[3:])):
            rel = rels_by_id.get(rel_id)
            if rel is None:
                missing.append((rel_id, "NO_REL"))
                continue
            if rel.get("TargetMode") == "External":
                continue
            target = target_to_zip_path("word/document.xml", rel["Target"])
            if target not in names:
                missing.append((rel_id, target))
        if missing:
            raise ValueError(f"Missing relationship targets in {docx.name}: {missing}")
        titles = [
            "".join(t.text or "" for t in paragraph.iter(q_w("t")))
            for paragraph in document.iter(q_w("p"))
        ]
        part_titles = [title for title in titles if re.match(r"^第\s*\d+\s*篇：", title)]
        return {"used_relationships": len(used_ids), "part_titles": len(part_titles)}


DECISION_TABLE_HEADERS = [
    "篇号",
    "原文件名",
    "父级标题",
    "原文摘录",
    "块类型",
    "处理结果",
    "处理理由",
    "置信度",
    "是否含图片/公式/表格",
]


def truncate_for_review(text: str, limit: int = 220) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def decision_row(part_index: int, source_path: Path, decision: RefineDecision) -> list[object]:
    analysis = decision.analysis
    return [
        part_index,
        source_path.name,
        analysis.parent_title or "（无）",
        truncate_for_review(analysis.text),
        analysis.block_type,
        decision.result,
        decision.reason,
        round(decision.confidence, 2),
        decision.media_summary,
    ]


def write_decision_table(path: Path, rows: list[list[object]]) -> None:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.worksheet.table import Table, TableStyleInfo
    except ImportError as exc:
        raise RuntimeError("openpyxl is required to write the decision review workbook.") from exc

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "提炼决策"
    sheet.append(DECISION_TABLE_HEADERS)
    for row in rows:
        sheet.append(row)

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    result_fills = {
        "保留": PatternFill("solid", fgColor="E2F0D9"),
        "删除": PatternFill("solid", fgColor="DDEBFF"),
        "压缩": PatternFill("solid", fgColor="FFF2CC"),
        "待复核": PatternFill("solid", fgColor="FCE4D6"),
    }
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row in sheet.iter_rows(min_row=2):
        result = row[5].value
        fill = result_fills.get(str(result))
        if fill:
            for cell in row:
                cell.fill = fill
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    widths = {
        "A": 8,
        "B": 42,
        "C": 34,
        "D": 60,
        "E": 14,
        "F": 12,
        "G": 58,
        "H": 10,
        "I": 28,
    }
    for col, width in widths.items():
        sheet.column_dimensions[col].width = width
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    if sheet.max_row >= 2:
        table = Table(displayName="DecisionReview", ref=sheet.dimensions)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        sheet.add_table(table)

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def build_outputs(
    folder: Path,
    *,
    expected_count: int,
    allow_course_fallback: bool,
    output_dir: Path | None = None,
) -> dict[str, object]:
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError(f"Input folder does not exist: {folder}")
    docx_files = sorted(
        [path for path in folder.glob("*.docx") if not path.name.startswith("~$")],
        key=natural_key,
    )
    if expected_count and len(docx_files) != expected_count:
        raise ValueError(f"Expected {expected_count} .docx files, found {len(docx_files)} in {folder}")
    if not docx_files:
        raise ValueError(f"No .docx files found in {folder}")

    output_dir = (output_dir or folder / OUT_DIR_NAME).resolve()
    full_output = output_dir / FULL_DOC_NAME
    refined_output = output_dir / REFINED_DOC_NAME
    marked_output = output_dir / MARKED_DOC_NAME
    decision_table_output = output_dir / DECISION_TABLE_NAME
    report_output = output_dir / REPORT_NAME

    output_dir.mkdir(parents=True, exist_ok=True)
    base_full = DocxPackage.load(docx_files[0])
    base_refined = DocxPackage.load(docx_files[0])
    base_marked = DocxPackage.load(docx_files[0])
    full_section = clone_section_properties(base_full.body)
    refined_section = clone_section_properties(base_refined.body)
    marked_section = clone_section_properties(base_marked.body)
    clear_body(base_full.body)
    clear_body(base_refined.body)
    clear_body(base_marked.body)

    full_doc_pr_state = {"next": 1}
    refined_doc_pr_state = {"next": 1}
    marked_doc_pr_state = {"next": 1}
    report_items = []
    decision_rows: list[list[object]] = []

    for index, source_path in enumerate(docx_files, start=1):
        source = DocxPackage.load(source_path)
        start, end, method = select_knowledge_range(source, allow_course_fallback=allow_course_fallback)
        source_children = [child for child in list(source.body) if child.tag != q_w("sectPr")]
        selected = source_children[start:end]
        selected = [child for child in selected if child.tag != q_w("sectPr")]
        refined, refined_stats, decisions = refine_blocks(selected)
        marked_selected, marked_blocks = marked_full_blocks(selected, decisions)
        decision_rows.extend(decision_row(index, source_path, decision) for decision in decisions)
        title = f"第 {index} 篇：{source_path.stem}"
        full_blocks = append_source_section(
            base_full,
            source,
            index,
            selected,
            title=title,
            page_break_before=index > 1,
            doc_pr_state=full_doc_pr_state,
        )
        marked_full_count = append_source_section(
            base_marked,
            source,
            index,
            marked_selected,
            title=title,
            page_break_before=index > 1,
            doc_pr_state=marked_doc_pr_state,
        )
        refined_blocks = append_source_section(
            base_refined,
            source,
            index,
            refined,
            title=title,
            page_break_before=index > 1,
            doc_pr_state=refined_doc_pr_state,
            normalize_chinese_numbering=True,
        )
        report_items.append(
            {
                "index": index,
                "file": str(source_path),
                "method": method,
                "start_body_index": start,
                "end_body_index": end,
                "full_blocks": full_blocks,
                "marked_full_blocks": marked_full_count,
                "marked_deleted_blocks": marked_blocks,
                "refined_blocks": refined_blocks,
                "relationship_blocks": sum(1 for child in selected if relationship_ids(child)),
                **refined_stats,
            }
        )

    base_full.body.append(full_section)
    base_refined.body.append(refined_section)
    base_marked.body.append(marked_section)
    base_full.serialize(full_output)
    base_refined.serialize(refined_output)
    base_marked.serialize(marked_output)
    write_decision_table(decision_table_output, decision_rows)

    validation = {
        "full": validate_relationship_targets(full_output),
        "refined": validate_relationship_targets(refined_output),
        "marked": validate_relationship_targets(marked_output),
    }
    report = {
        "input_folder": str(folder),
        "file_count": len(docx_files),
        "outputs": {
            "full": str(full_output),
            "refined": str(refined_output),
            "marked": str(marked_output),
            "decision_table": str(decision_table_output),
            "report": str(report_output),
        },
        "validation": validation,
        "items": report_items,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    report_output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_conservative_enhanced_outputs(
    folder: Path,
    *,
    expected_count: int,
    allow_course_fallback: bool,
    output_dir: Path | None = None,
) -> dict[str, object]:
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError(f"Input folder does not exist: {folder}")
    docx_files = sorted(
        [path for path in folder.glob("*.docx") if not path.name.startswith("~$")],
        key=natural_key,
    )
    if expected_count and len(docx_files) != expected_count:
        raise ValueError(f"Expected {expected_count} .docx files, found {len(docx_files)} in {folder}")
    if not docx_files:
        raise ValueError(f"No .docx files found in {folder}")

    output_dir = (output_dir or folder / OUT_DIR_NAME).resolve()
    enhanced_output = output_dir / ENHANCED_REFINED_DOC_NAME
    enhanced_marked_output = output_dir / ENHANCED_MARKED_DOC_NAME
    enhanced_decision_table_output = output_dir / ENHANCED_DECISION_TABLE_NAME

    output_dir.mkdir(parents=True, exist_ok=True)
    base_enhanced = DocxPackage.load(docx_files[0])
    base_enhanced_marked = DocxPackage.load(docx_files[0])
    enhanced_section = clone_section_properties(base_enhanced.body)
    enhanced_marked_section = clone_section_properties(base_enhanced_marked.body)
    clear_body(base_enhanced.body)
    clear_body(base_enhanced_marked.body)

    enhanced_doc_pr_state = {"next": 1}
    enhanced_marked_doc_pr_state = {"next": 1}
    decision_rows: list[list[object]] = []
    report_items = []

    for index, source_path in enumerate(docx_files, start=1):
        source = DocxPackage.load(source_path)
        start, end, method = select_knowledge_range(source, allow_course_fallback=allow_course_fallback)
        source_children = [child for child in list(source.body) if child.tag != q_w("sectPr")]
        selected = [child for child in source_children[start:end] if child.tag != q_w("sectPr")]
        enhanced, enhanced_stats, enhanced_decisions = refine_blocks_conservative_enhanced(selected)
        enhanced_marked_selected, enhanced_marked_blocks = marked_full_blocks(selected, enhanced_decisions)
        decision_rows.extend(decision_row(index, source_path, decision) for decision in enhanced_decisions)
        title = f"第 {index} 篇：{source_path.stem}"
        enhanced_blocks = append_source_section(
            base_enhanced,
            source,
            index,
            enhanced,
            title=title,
            page_break_before=index > 1,
            doc_pr_state=enhanced_doc_pr_state,
            normalize_chinese_numbering=True,
        )
        enhanced_marked_count = append_source_section(
            base_enhanced_marked,
            source,
            index,
            enhanced_marked_selected,
            title=title,
            page_break_before=index > 1,
            doc_pr_state=enhanced_marked_doc_pr_state,
        )
        report_items.append(
            {
                "index": index,
                "file": str(source_path),
                "method": method,
                "start_body_index": start,
                "end_body_index": end,
                "enhanced_blocks": enhanced_blocks,
                "enhanced_marked_blocks": enhanced_marked_count,
                "enhanced_marked_deleted_blocks": enhanced_marked_blocks,
                "relationship_blocks": sum(1 for child in selected if relationship_ids(child)),
                **enhanced_stats,
            }
        )

    base_enhanced.body.append(enhanced_section)
    base_enhanced_marked.body.append(enhanced_marked_section)
    base_enhanced.serialize(enhanced_output)
    base_enhanced_marked.serialize(enhanced_marked_output)
    write_decision_table(enhanced_decision_table_output, decision_rows)

    validation = {
        "enhanced_refined": validate_relationship_targets(enhanced_output),
        "enhanced_marked": validate_relationship_targets(enhanced_marked_output),
    }
    return {
        "input_folder": str(folder),
        "file_count": len(docx_files),
        "outputs": {
            "enhanced_refined": str(enhanced_output),
            "enhanced_marked": str(enhanced_marked_output),
            "enhanced_decision_table": str(enhanced_decision_table_output),
        },
        "validation": validation,
        "items": report_items,
    }


def build_all_outputs(
    folder: Path,
    *,
    expected_count: int,
    allow_course_fallback: bool,
    output_dir: Path | None = None,
) -> dict[str, object]:
    standard_report = build_outputs(
        folder,
        expected_count=expected_count,
        allow_course_fallback=allow_course_fallback,
        output_dir=output_dir,
    )
    enhanced_report = build_conservative_enhanced_outputs(
        folder,
        expected_count=expected_count,
        allow_course_fallback=allow_course_fallback,
        output_dir=output_dir,
    )
    merged_report = dict(standard_report)
    merged_report["outputs"] = {
        **standard_report["outputs"],
        **enhanced_report["outputs"],
    }
    merged_report["validation"] = {
        **standard_report["validation"],
        **enhanced_report["validation"],
    }
    merged_report["enhanced_items"] = enhanced_report["items"]
    report_path = Path(standard_report["outputs"]["report"])
    report_path.write_text(json.dumps(merged_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path, help="Folder containing source .docx handouts.")
    parser.add_argument("--expected-count", type=int, default=0)
    parser.add_argument("--output-dir", type=Path)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--standard-only",
        action="store_true",
        help="Only create the complete, standard refined, standard marked, decision table, and report outputs.",
    )
    mode_group.add_argument(
        "--enhanced-only",
        "--conservative-enhanced-only",
        dest="enhanced_only",
        action="store_true",
        help="Only create the conservative enhanced compression deliverables; leave existing standard outputs untouched.",
    )
    parser.add_argument(
        "--allow-course-fallback",
        action="store_true",
        help="Also accept existing knowledge-memory course files by extracting their first section.",
    )
    args = parser.parse_args()
    if args.enhanced_only:
        report = build_conservative_enhanced_outputs(
            args.folder,
            expected_count=args.expected_count,
            allow_course_fallback=args.allow_course_fallback,
            output_dir=args.output_dir,
        )
    elif args.standard_only:
        report = build_outputs(
            args.folder,
            expected_count=args.expected_count,
            allow_course_fallback=args.allow_course_fallback,
            output_dir=args.output_dir,
        )
    else:
        report = build_all_outputs(
            args.folder,
            expected_count=args.expected_count,
            allow_course_fallback=args.allow_course_fallback,
            output_dir=args.output_dir,
        )
    print(json.dumps(report["outputs"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

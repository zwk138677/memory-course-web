from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from src.memory_course_web.finished_course_parser import ParsedParagraph, _paragraph_from_xml, _parse_questions, parse_finished_course
from src.memory_course_web.validation import validate_finished_course_payload


def _course_samples() -> list[Path]:
    marker = "".join(map(chr, [0x77E5, 0x8BC6, 0x80CC, 0x8BB0, 0x8BFE, 0x7A0B]))
    return [path for path in Path(".").glob("**/*.docx") if marker in path.name and "lo_render_work" not in path.as_posix()]


def _image_course_samples() -> list[Path]:
    course_marker = "".join(map(chr, [0x77E5, 0x8BC6, 0x80CC, 0x8BB0, 0x8BFE, 0x7A0B]))
    image_marker = "".join(map(chr, [0x914D, 0x56FE]))
    return [
        path
        for path in Path(".").glob("**/*.docx")
        if course_marker in path.name and image_marker in path.name and "lo_render_work" not in path.as_posix()
    ]


def test_parse_existing_finished_course_when_available():
    samples = _course_samples()
    if not samples:
        pytest.skip("finished course DOCX sample is not present")

    course = parse_finished_course(samples[0])
    payload = validate_finished_course_payload(course.to_payload())

    assert payload["title"]
    assert payload["knowledge_paragraphs"]
    assert payload["quick_practice"]
    for blank in payload["blanks"]:
        paragraph = payload["knowledge_paragraphs"][blank["paragraph_index"]]
        assert paragraph[blank["start"] : blank["end"]] == blank["answer"]


def test_parse_questions_from_finished_course_sample_when_available():
    samples = _course_samples()
    if not samples:
        pytest.skip("finished course DOCX sample is not present")

    payload = parse_finished_course(samples[0]).to_payload()

    first_question = payload["quick_practice"][0]
    assert first_question["stem"]
    assert first_question["correct"]
    assert len(first_question["wrong"]) == 3


def test_parse_split_question_heading_format():
    paragraphs = [
        ParsedParagraph("【基础辨析】"),
        ParsedParagraph("【第一题】："),
        ParsedParagraph("圆是下列哪一种图形？"),
        ParsedParagraph("【正确选项】：中心对称图形"),
        ParsedParagraph("【错误选项1】：轴对称但不是中心对称图形"),
        ParsedParagraph("【错误选项2】：只能平移重合的图形"),
        ParsedParagraph("【错误选项3】：没有对称性的图形"),
    ]

    questions = _parse_questions(paragraphs, 0)

    assert len(questions) == 1
    assert questions[0]["category"] == "基础辨析"
    assert questions[0]["stem"] == "圆是下列哪一种图形？"
    assert questions[0]["correct"] == "中心对称图形"
    assert len(questions[0]["wrong"]) == 3


def test_parse_mathtype_preview_as_inline_formula():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:v="urn:schemas-microsoft-com:vml"
             xmlns:o="urn:schemas-microsoft-com:office:office">
          <w:r><w:t>a=</w:t></w:r>
          <w:r>
            <w:object>
              <v:shape><v:imagedata r:id="rId1" /></v:shape>
              <o:OLEObject r:id="rId2" />
            </w:object>
          </w:r>
          <w:r><w:t>)</w:t></w:r>
        </w:p>
        """
    )
    media_lookup = {
        "rId1": {
            "id": "rId1",
            "filename": "formula.png",
            "mime_type": "image/png",
            "data_uri": "data:image/png;base64,AA==",
            "renderable": True,
            "width_px": 45,
            "height_px": 27,
        }
    }

    parsed = _paragraph_from_xml(paragraph, media_lookup)

    assert parsed.text == "a=)"
    assert len(parsed.images) == 1
    assert parsed.images[0].inline is True
    assert parsed.images[0].char_index == 2
    assert parsed.images[0].kind == "formula"


def test_parse_mathtype_formula_prefers_readable_text():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:v="urn:schemas-microsoft-com:vml"
             xmlns:o="urn:schemas-microsoft-com:office:office">
          <w:r><w:t>圆周角定理：一条弧所对的圆周角等于它所对的圆心角的一半.（即：圆周角=</w:t></w:r>
          <w:r>
            <w:object>
              <v:shape><v:imagedata r:id="rId1" /></v:shape>
              <o:OLEObject r:id="rId2" />
            </w:object>
          </w:r>
          <w:r><w:t>）</w:t></w:r>
        </w:p>
        """
    )
    media_lookup = {
        "rId1": {
            "id": "rId1",
            "filename": "formula.png",
            "mime_type": "image/png",
            "data_uri": "data:image/png;base64,AA==",
            "renderable": True,
            "width_px": 45,
            "height_px": 27,
        }
    }

    parsed = _paragraph_from_xml(paragraph, media_lookup, {"rId2": "1/2"})

    assert parsed.text.endswith("圆周角=）")
    assert len(parsed.images) == 1
    assert parsed.images[0].kind == "formula_text"
    assert parsed.images[0].formula_text == "1/2圆心角"
    assert parsed.images[0].data_uri == ""


def test_parse_images_from_finished_course_sample_when_available():
    samples = _image_course_samples()
    if not samples:
        pytest.skip("image course DOCX sample is not present")

    payload = validate_finished_course_payload(parse_finished_course(samples[0]).to_payload())
    question_image_count = sum(len(question.get("images", [])) for question in payload["quick_practice"])

    assert payload["knowledge_images"] or question_image_count
    for image in payload["knowledge_images"]:
        assert 0 <= image["paragraph_index"] < len(payload["knowledge_paragraphs"])
        assert image["filename"]

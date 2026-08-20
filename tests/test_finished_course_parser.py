from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from xml.etree import ElementTree as ET

import pytest

from src.memory_course_web import finished_course_parser
from src.memory_course_web.finished_course_parser import (
    ParagraphImage,
    ParsedParagraph,
    _extract_distractor_groups,
    _paragraph_from_xml,
    _parse_questions,
    _split_distractor_text,
    parse_finished_course,
)
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


def test_distractor_parser_preserves_case_distinct_units():
    assert _split_distractor_text(["DB; db; dB"]) == ["DB", "db", "dB"]


def test_parse_word_superscript_digits_as_unicode():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:r><w:t>4.2×10</w:t></w:r>
          <w:r>
            <w:rPr><w:vertAlign w:val="superscript" /></w:rPr>
            <w:t>3</w:t>
          </w:r>
          <w:r><w:t xml:space="preserve"> J/(kg·℃)</w:t></w:r>
        </w:p>
        """
    )

    parsed = _paragraph_from_xml(paragraph, {})

    assert parsed.text == "4.2×10³ J/(kg·℃)"


def test_parse_word_text_subscript_as_latex():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:r><w:t>ρ</w:t></w:r>
          <w:r>
            <w:rPr><w:vertAlign w:val="subscript" /></w:rPr>
            <w:t>水</w:t>
          </w:r>
        </w:p>
        """
    )

    parsed = _paragraph_from_xml(paragraph, {})

    assert parsed.text == r"ρ${}_{\text{水}}$"


def test_parse_native_word_fraction_inline_in_paragraph():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <w:r><w:t>密度公式 ρ=</w:t></w:r>
          <m:oMath>
            <m:f>
              <m:num><m:r><m:t>m</m:t></m:r></m:num>
              <m:den><m:r><m:t>V</m:t></m:r></m:den>
            </m:f>
          </m:oMath>
          <w:r><w:t>。</w:t></w:r>
        </w:p>
        """
    )

    parsed = _paragraph_from_xml(paragraph, {})

    assert parsed.text == r"密度公式 ρ=$\frac{m}{V}$。"


def test_parse_native_word_fraction_with_subscripts():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <m:oMath>
            <m:f>
              <m:num>
                <m:sSub><m:e><m:r><m:t>m</m:t></m:r></m:e><m:sub><m:r><m:t>2</m:t></m:r></m:sub></m:sSub>
                <m:r><m:t>-</m:t></m:r>
                <m:sSub><m:e><m:r><m:t>m</m:t></m:r></m:e><m:sub><m:r><m:t>0</m:t></m:r></m:sub></m:sSub>
              </m:num>
              <m:den>
                <m:sSub><m:e><m:r><m:t>m</m:t></m:r></m:e><m:sub><m:r><m:t>1</m:t></m:r></m:sub></m:sSub>
                <m:r><m:t>-</m:t></m:r>
                <m:sSub><m:e><m:r><m:t>m</m:t></m:r></m:e><m:sub><m:r><m:t>0</m:t></m:r></m:sub></m:sSub>
              </m:den>
            </m:f>
            <m:sSub><m:e><m:r><m:t>ρ</m:t></m:r></m:e><m:sub><m:r><m:t>水</m:t></m:r></m:sub></m:sSub>
          </m:oMath>
        </w:p>
        """
    )

    parsed = _paragraph_from_xml(paragraph, {})

    assert parsed.text == r"$\frac{m_{2}-m_{0}}{m_{1}-m_{0}}ρ_{\text{水}}$"


def test_parse_underlined_native_word_formula_as_one_blank():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <w:r><w:t>密度公式：</w:t></w:r>
          <m:oMath>
            <m:f>
              <m:fPr><m:ctrlPr><w:rPr><w:u w:val="single" /></w:rPr></m:ctrlPr></m:fPr>
              <m:num><m:r><w:rPr><w:u w:val="single" /></w:rPr><m:t>m</m:t></m:r></m:num>
              <m:den><m:r><w:rPr><w:u w:val="single" /></w:rPr><m:t>V</m:t></m:r></m:den>
            </m:f>
          </m:oMath>
          <w:r><w:t>。</w:t></w:r>
        </w:p>
        """
    )

    parsed = _paragraph_from_xml(paragraph, {})

    assert parsed.text == r"密度公式：$\frac{m}{V}$。"
    assert [(span.start, span.end, span.text) for span in parsed.underline_spans] == [
        (5, 18, r"$\frac{m}{V}$")
    ]


def test_parse_common_native_word_formula_structures():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <m:oMath>
            <m:sSup><m:e><m:r><m:t>x</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup></m:sSup>
            <m:r><m:t>+</m:t></m:r>
            <m:rad><m:deg><m:r><m:t>3</m:t></m:r></m:deg><m:e><m:r><m:t>x</m:t></m:r></m:e></m:rad>
            <m:r><m:t>+</m:t></m:r>
            <m:d>
              <m:dPr><m:begChr m:val="[" /><m:endChr m:val="]" /></m:dPr>
              <m:e><m:r><m:t>y+1</m:t></m:r></m:e>
            </m:d>
          </m:oMath>
        </w:p>
        """
    )

    parsed = _paragraph_from_xml(paragraph, {})

    assert parsed.text == r"$x^{2}+\sqrt[3]{x}+\left[y+1\right]$"


def test_parse_native_word_combined_subscript_and_superscript():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <m:oMath>
            <m:sSubSup>
              <m:e><m:r><m:t>A</m:t></m:r></m:e>
              <m:sub><m:r><m:t>1</m:t></m:r></m:sub>
              <m:sup><m:r><m:t>2</m:t></m:r></m:sup>
            </m:sSubSup>
          </m:oMath>
        </w:p>
        """
    )

    parsed = _paragraph_from_xml(paragraph, {})

    assert parsed.text == r"$A_{1}^{2}$"


def test_parse_unsupported_native_word_formula_with_visible_placeholder():
    paragraph = ET.fromstring(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
          <m:oMath>
            <m:m>
              <m:mr><m:e><m:r><m:t>a</m:t></m:r></m:e><m:e><m:r><m:t>b</m:t></m:r></m:e></m:mr>
              <m:mr><m:e><m:r><m:t>c</m:t></m:r></m:e><m:e><m:r><m:t>d</m:t></m:r></m:e></m:mr>
            </m:m>
          </m:oMath>
        </w:p>
        """
    )

    parsed = _paragraph_from_xml(paragraph, {})

    assert parsed.text == r"$\text{[暂不支持的 Word 公式]}$"


def test_distractor_parser_keeps_image_only_paragraph_after_distractors():
    image = ParagraphImage(
        id="rId1",
        filename="reflection.png",
        mime_type="image/png",
        data_uri="data:image/png;base64,AA==",
        renderable=True,
    )
    knowledge = [
        ParsedParagraph("知识小题1.反射类型"),
        ParsedParagraph("镜面反射和漫反射都满足反射定律。"),
        ParsedParagraph("干扰项：不满足；不一定满足"),
        ParsedParagraph("", images=[image]),
    ]

    cleaned, groups = _extract_distractor_groups(knowledge)

    assert [paragraph.text for paragraph in cleaned] == ["知识小题1.反射类型", "镜面反射和漫反射都满足反射定律。", ""]
    assert cleaned[-1].images == [image]
    assert groups[0]["distractors"] == ["不满足", "不一定满足"]


def test_parse_existing_finished_course_when_available():
    samples = _course_samples()
    if not samples:
        pytest.skip("finished course DOCX sample is not present")

    raw_payload = parse_finished_course(samples[0]).to_payload()
    if raw_payload["blanks"] and not raw_payload.get("distractor_groups"):
        pytest.skip("finished course DOCX sample has no self-contained distractor groups")
    payload = validate_finished_course_payload(raw_payload)

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


def test_parse_physics_question_source_and_analysis_without_category():
    paragraphs = [
        ParsedParagraph("— 配套练习题 —"),
        ParsedParagraph("【第一题】："),
        ParsedParagraph("【来源：知识小题1】"),
        ParsedParagraph("【题目内容】：下列关于分子热运动的说法正确的是哪一项？"),
        ParsedParagraph("【正确选项】：温度越高，分子热运动越剧烈"),
        ParsedParagraph("【错误选项1】：温度越高，分子热运动越缓慢"),
        ParsedParagraph("【错误选项2】：分子静止不动"),
        ParsedParagraph("【错误选项3】：热运动只发生在固体中"),
        ParsedParagraph("【解析】：分子永不停息地做无规则运动，温度越高运动越剧烈。"),
    ]

    questions = _parse_questions(paragraphs, 0)

    assert len(questions) == 1
    assert questions[0]["category"] == ""
    assert questions[0]["source"] == "知识小题1"
    assert questions[0]["analysis"] == "分子永不停息地做无规则运动，温度越高运动越剧烈。"
    assert questions[0]["stem"] == "下列关于分子热运动的说法正确的是哪一项？"


def test_parse_question_stem_keeps_leading_decimal():
    paragraphs = [
        ParsedParagraph("【第五题】："),
        ParsedParagraph("【来源：知识小题2】"),
        ParsedParagraph("【题目内容】：0.1010010001...（相邻两个 1 之间依次多一个 0）属于无理数，主要依据是什么？"),
        ParsedParagraph("【正确选项】：它是具有特定结构的无限不循环小数。"),
        ParsedParagraph("【错误选项1】：它的小数位数有限。"),
        ParsedParagraph("【错误选项2】：它的小数部分循环重复。"),
        ParsedParagraph("【错误选项3】：它可以直接化成分数。"),
        ParsedParagraph("【解析】：该小数按特定规律无限延伸，但不循环，所以属于无理数。"),
    ]

    questions = _parse_questions(paragraphs, 0)

    assert questions[0]["stem"].startswith("0.1010010001...")


def test_parse_question_stem_strips_leading_item_number():
    paragraphs = [
        ParsedParagraph("【第一题】："),
        ParsedParagraph("【题目内容】：1. 下列说法正确的是哪一项？"),
        ParsedParagraph("【正确选项】：正确说法"),
        ParsedParagraph("【错误选项1】：错误一"),
        ParsedParagraph("【错误选项2】：错误二"),
        ParsedParagraph("【错误选项3】：错误三"),
    ]

    questions = _parse_questions(paragraphs, 0)

    assert questions[0]["stem"] == "下列说法正确的是哪一项？"


def _write_minimal_docx(path: Path, texts: list[str]) -> None:
    def paragraph(text: str) -> str:
        if text.lstrip().startswith("<w:p"):
            return text
        return f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>"

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraph(text) for text in texts)
        + "<w:sectPr/></w:body></w:document>"
    )
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", content_types)
        package.writestr("_rels/.rels", root_rels)
        package.writestr("word/document.xml", document)
        package.writestr("word/_rels/document.xml.rels", doc_rels)


def _complete_reference_course(title: str, answer: str, correct: str) -> list[str]:
    return [
        title,
        "知识小题1.核心概念",
        (
            "<w:p>"
            "<w:r><w:t>需要记住：</w:t></w:r>"
            f'<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>{answer}</w:t></w:r>'
            "</w:p>"
        ),
        "干扰项：干扰甲；干扰乙；干扰丙",
        "— 配套练习题 —",
        "【第一题】：",
        "【来源：知识小题1】",
        f"【题目内容】：{title}的正确表述是哪一项？",
        f"【正确选项】：{correct}",
        "【错误选项1】：错误甲",
        "【错误选项2】：错误乙",
        "【错误选项3】：错误丙",
        f"【解析】：应选择{correct}。",
    ]


def test_parse_finished_courses_splits_on_equals_separator_and_ignores_empty_tail(tmp_path: Path):
    docx = tmp_path / "physics_collection.docx"
    first = _complete_reference_course("一、第一课", "答案一", "正确一")
    second = _complete_reference_course("二、第二课", "答案二", "正确二")
    _write_minimal_docx(docx, first + ["========================================"] + second + ["========================================"])

    courses = finished_course_parser.parse_finished_courses(docx)

    assert [course.title for course in courses] == ["一、第一课", "二、第二课"]
    assert [[question["correct"] for question in course.quick_practice] for course in courses] == [["正确一"], ["正确二"]]
    assert [[blank["answer"] for blank in course.blanks] for course in courses] == [["答案一"], ["答案二"]]


def test_parse_finished_courses_does_not_guess_a_boundary_without_separator(tmp_path: Path):
    docx = tmp_path / "missing_separator.docx"
    first = _complete_reference_course("一、第一课", "答案一", "正确一")
    second = _complete_reference_course("二、第二课", "答案二", "正确二")
    _write_minimal_docx(docx, first + second)

    courses = finished_course_parser.parse_finished_courses(docx)

    assert len(courses) == 1
    assert courses[0].title == "一、第一课"


def test_parse_finished_courses_requires_the_full_forty_equals_separator(tmp_path: Path):
    docx = tmp_path / "short_separator.docx"
    first = _complete_reference_course("一、第一课", "答案一", "正确一")
    second = _complete_reference_course("二、第二课", "答案二", "正确二")
    _write_minimal_docx(docx, first + ["=" * 39] + second)

    courses = finished_course_parser.parse_finished_courses(docx)

    assert len(courses) == 1


def test_parser_removes_shared_distractor_that_duplicates_an_item_answer(tmp_path: Path):
    docx = tmp_path / "shared_answer_in_distractors.docx"
    course = _complete_reference_course("颜色", "反射", "正确项")
    course[3] = "干扰项：反射；透过；白色"
    _write_minimal_docx(docx, course)

    payload = validate_finished_course_payload(parse_finished_course(docx).to_payload())

    assert payload["distractor_groups"][0]["distractors"] == ["透过", "白色"]


def test_parse_physics_course_title_and_hides_title_paragraphs(tmp_path: Path):
    docx = tmp_path / "physics.docx"
    _write_minimal_docx(
        docx,
        [
            "【知识点 1】",
            "一、分子动理论",
            "知识小题1.分子热运动",
            "一切物质的分子都在不停地做无规则运动。",
            "— 配套练习题 —",
            "【第一题】：",
            "【来源：知识小题1】",
            "【题目内容】：下列说法正确的是哪一项？",
            "【正确选项】：分子在不停地做无规则运动",
            "【错误选项1】：分子总是静止的",
            "【错误选项2】：只有液体分子运动",
            "【错误选项3】：温度与分子运动无关",
            "【解析】：分子动理论认为，分子在不停地做无规则运动。",
        ],
    )

    payload = validate_finished_course_payload(parse_finished_course(docx).to_payload())

    assert payload["title"] == "分子动理论"
    assert payload["structure"] == "physics_course"
    assert "【知识点 1】" not in payload["knowledge_paragraphs"]
    assert "一、分子动理论" not in payload["knowledge_paragraphs"]
    assert payload["knowledge_paragraphs"][0] == "知识小题1.分子热运动"
    assert payload["quick_practice"][0]["source"] == "知识小题1"
    assert payload["quick_practice"][0]["analysis"] == "分子动理论认为，分子在不停地做无规则运动。"


def test_parse_direct_title_physics_reference_course(tmp_path: Path):
    docx = tmp_path / "physics_reference.docx"
    _write_minimal_docx(
        docx,
        [
            "分子动理论",
            "知识小题1.物质构成",
            "物质是由大量分子和原子构成的",
            "知识小题2.分子热运动",
            "定义：分子在永不停息地做无规则运动",
            "— 配套练习题 —",
            "【第一题】：",
            "【来源：知识小题1】",
            "【题目内容】：关于物质构成，下列说法正确的是",
            "【正确选项】：物质是由大量分子和原子构成的",
            "【错误选项1】：一切物质都只由分子构成",
            "【错误选项2】：分子不能再分",
            "【错误选项3】：原子不能构成物质",
            "【解析】：物质可由分子、原子等微粒构成。",
        ],
    )

    payload = validate_finished_course_payload(parse_finished_course(docx).to_payload())

    assert payload["title"] == "分子动理论"
    assert payload["structure"] == "physics_reference_course"
    assert payload["knowledge_paragraphs"][0] == "知识小题1.物质构成"
    assert "分子动理论" not in payload["knowledge_paragraphs"]
    assert payload["quick_practice"][0]["source"] == "知识小题1"
    assert payload["quick_practice"][0]["analysis"] == "物质可由分子、原子等微粒构成。"


def test_parse_self_contained_distractor_groups_and_hides_marker_paragraphs(tmp_path: Path):
    docx = tmp_path / "physics_self_distractors.docx"
    _write_minimal_docx(
        docx,
        [
            "二力平衡",
            "知识小题1.定义",
            (
                "<w:p>"
                "<w:r><w:t>物体保持</w:t></w:r>"
                '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>静止</w:t></w:r>'
                "<w:r><w:t>或</w:t></w:r>"
                '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>匀速直线运动</w:t></w:r>'
                "</w:p>"
            ),
            "干扰项：运动；匀速运动；匀速圆周运动",
            "知识小题2.二力平衡的条件",
            (
                "<w:p>"
                '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>同一物体</w:t></w:r>'
                "<w:r><w:t>上的两个力，大小</w:t></w:r>"
                '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>相等</w:t></w:r>'
                "<w:r><w:t>，方向</w:t></w:r>"
                '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>相反</w:t></w:r>'
                "</w:p>"
            ),
            "干扰项：不同物体；相同；同一平面",
            "— 配套练习题 —",
            "【第一题】：",
            "【来源：知识小题1】",
            "【题目内容】：二力平衡时物体可处于什么状态？",
            "【正确选项】：静止或匀速直线运动",
            "【错误选项1】：只做曲线运动",
            "【错误选项2】：速度一定变大",
            "【错误选项3】：方向不断改变",
            "【解析】：二力平衡时合力为零，物体保持平衡状态。",
        ],
    )

    payload = validate_finished_course_payload(parse_finished_course(docx).to_payload())

    assert all("干扰项" not in paragraph for paragraph in payload["knowledge_paragraphs"])
    assert [group["distractors"] for group in payload["distractor_groups"]] == [
        ["运动", "匀速运动", "匀速圆周运动"],
        ["不同物体", "相同", "同一平面"],
    ]
    assert payload["distractor_groups"][0]["paragraph_indexes"] == [0, 1]
    assert payload["distractor_groups"][1]["paragraph_indexes"] == [2, 3]
    assert [blank["answer"] for blank in payload["blanks"]] == ["静止", "匀速直线运动", "同一物体", "相等", "相反"]


def test_parse_math_numbered_sections_as_distractor_group_boundaries(tmp_path: Path):
    docx = tmp_path / "math_numbered_sections.docx"
    _write_minimal_docx(
        docx,
        [
            "实数及其运算",
            "一、相反数与绝对值",
            (
                "<w:p>"
                "<w:r><w:t>若 a 表示一个数，则 a 的相反数是</w:t></w:r>"
                '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>-a</w:t></w:r>'
                "</w:p>"
            ),
            "干扰项：a；|a|",
            "二、实数的运算顺序",
            (
                "<w:p>"
                "<w:r><w:t>实数运算先算</w:t></w:r>"
                '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>乘方和开方</w:t></w:r>'
                "</w:p>"
            ),
            "干扰项：加减；乘除",
            "— 配套练习题 —",
            "【第一题】：",
            "【来源：相反数与绝对值】",
            "【题目内容】：a 的相反数是什么？",
            "【正确选项】：-a",
            "【错误选项1】：a",
            "【错误选项2】：|a|",
            "【错误选项3】：0",
            "【解析】：相反数与原数符号相反。",
        ],
    )

    payload = validate_finished_course_payload(parse_finished_course(docx).to_payload())

    assert all("干扰项" not in paragraph for paragraph in payload["knowledge_paragraphs"])
    assert [group["title"] for group in payload["distractor_groups"]] == ["一、相反数与绝对值", "二、实数的运算顺序"]
    assert [group["paragraph_indexes"] for group in payload["distractor_groups"]] == [[0, 1], [2, 3]]
    assert [group["distractors"] for group in payload["distractor_groups"]] == [["a", "|a|"], ["加减", "乘除"]]


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

    raw_payload = parse_finished_course(samples[0]).to_payload()
    if raw_payload["blanks"] and not raw_payload.get("distractor_groups"):
        pytest.skip("image course DOCX sample has no self-contained distractor groups")
    payload = validate_finished_course_payload(raw_payload)
    question_image_count = sum(len(question.get("images", [])) for question in payload["quick_practice"])

    assert payload["knowledge_images"] or question_image_count
    for image in payload["knowledge_images"]:
        assert 0 <= image["paragraph_index"] < len(payload["knowledge_paragraphs"])
        assert image["filename"]

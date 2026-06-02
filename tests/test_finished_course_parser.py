from pathlib import Path

import pytest

from src.memory_course_web.finished_course_parser import ParsedParagraph, _parse_questions, parse_finished_course
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

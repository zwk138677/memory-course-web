from pathlib import Path

import pytest

from src.memory_course_web.extraction import extract_knowledge_text


def test_extract_existing_sample_docx_when_available():
    sample = Path("skill_test_绝对值_知识背记课程.docx")
    if not sample.exists():
        pytest.skip("sample DOCX is not present in this checkout")

    result = extract_knowledge_text(sample)

    assert result.knowledge_text.strip()
    assert result.paragraphs
    assert result.method

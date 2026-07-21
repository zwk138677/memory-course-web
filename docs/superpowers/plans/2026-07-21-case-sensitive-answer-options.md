# Case-Sensitive Answer Options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `DB` and `db` to be valid distractors for the correct answer `dB` throughout parsing, validation, and fill-word-bank construction.

**Architecture:** Keep the existing whitespace cleanup in each component, but remove case folding from option identity. Parser, validators, and word-bank construction will compare cleaned strings exactly, matching the already case-sensitive browser answer checks.

**Tech Stack:** Python 3, pytest, Streamlit HTML/JavaScript

## Global Constraints

- Apply the rule to both knowledge-fill distractors and quick-practice options.
- Treat `dB`, `DB`, and `db` as distinct values.
- Continue treating values that differ only by surrounding or repeated whitespace as duplicates.
- Do not change DOCX text, answer locations, option display text, or frontend scoring behavior.

---

### Task 1: Use case-sensitive option identity end to end

**Files:**
- Modify: `tests/test_distractors.py`
- Modify: `tests/test_finished_course_parser.py`
- Modify: `src/memory_course_web/finished_course_parser.py:708-719`
- Modify: `src/memory_course_web/validation.py:71-99,145-159`
- Modify: `src/memory_course_web/rendering.py:101-136`

**Interfaces:**
- Consumes: `_split_distractor_text(texts: list[str]) -> list[str]`, `validate_finished_course_payload(payload: dict) -> dict`, and `build_word_bank(blanks: list[dict], salt: str, ...) -> list[dict]`.
- Produces: The same signatures with cleaned, case-sensitive option identity.

- [ ] **Step 1: Add parser and end-to-end failing tests**

Add to `tests/test_finished_course_parser.py`:

```python
from src.memory_course_web.finished_course_parser import _split_distractor_text


def test_distractor_parser_preserves_case_distinct_units():
    assert _split_distractor_text(["DB; db; dB"]) == ["DB", "db", "dB"]
```

Add to `tests/test_distractors.py`:

```python
def test_case_distinct_units_pass_validation_and_reach_word_bank():
    payload = {
        "title": "声音单位",
        "knowledge_paragraphs": ["知识小题1.单位", "声级单位为dB"],
        "blanks": [{"id": "b001", "answer": "dB", "paragraph_index": 1, "start": 5, "end": 7}],
        "distractor_groups": [{
            "id": "dg001",
            "title": "知识小题1.单位",
            "paragraph_indexes": [0, 1],
            "distractors": ["DB", "db", "B"],
            "source": "资料自带",
        }],
        "quick_practice": [{
            "category": "基础辨析",
            "stem": "分贝的单位符号是？",
            "correct": "dB",
            "wrong": ["DB", "db", "B"],
        }],
    }

    validated = validate_finished_course_payload(payload)
    word_bank = build_word_bank(
        validated["blanks"],
        "case-sensitive-unit",
        distractor_groups=validated["distractor_groups"],
        paragraph_indexes=[0, 1],
    )

    assert set(item["text"] for item in word_bank) == {"dB", "DB", "db", "B"}
    assert validated["quick_practice"][0]["wrong"] == ["DB", "db", "B"]
```

Add a whitespace regression test that calls `validate_distractor_list("dB", [" dB ", "db", "B"], "测试")` and asserts it still raises `PayloadValidationError`.

- [ ] **Step 2: Run the focused tests and verify they fail for case folding**

Run: `python -m pytest tests/test_finished_course_parser.py::test_distractor_parser_preserves_case_distinct_units tests/test_distractors.py::test_case_distinct_units_pass_validation_and_reach_word_bank -q`

Expected: FAIL because the parser collapses all three values and validation reports a distractor equal to the answer.

- [ ] **Step 3: Remove case folding while preserving whitespace cleanup**

Use each component's already-cleaned string directly as its key:

```python
# finished_course_parser.py
key = cleaned

# validation.py list validators
keys = {" ".join(answer.split()).strip()}
key = item

# validation.py group coverage
answers_by_group_id.setdefault(str(group["id"]), set()).add(" ".join(str(blank["answer"]).split()).strip())
if " ".join(distractor.split()).strip() in answer_keys:
    ...

# rendering.py
answer_keys = {_clean_option_text(blank.get("answer", "")) for blank in blanks}
key = cleaned
```

- [ ] **Step 4: Run focused and complete verification**

Run: `python -m pytest tests/test_finished_course_parser.py::test_distractor_parser_preserves_case_distinct_units tests/test_distractors.py::test_case_distinct_units_pass_validation_and_reach_word_bank tests/test_distractors.py::test_case_sensitive_validation_rejects_whitespace_duplicate -q`

Expected: `3 passed`.

Run: `python -m pytest -q`

Expected: all tests pass.

Run: `python -m compileall -q app.py src tests`

Expected: exit code 0.

- [ ] **Step 5: Commit and synchronize**

```powershell
git add -- src/memory_course_web/finished_course_parser.py src/memory_course_web/validation.py src/memory_course_web/rendering.py tests/test_finished_course_parser.py tests/test_distractors.py docs/superpowers/plans/2026-07-21-case-sensitive-answer-options.md
git commit -m "Allow case-sensitive answer distractors"
git push origin main
```

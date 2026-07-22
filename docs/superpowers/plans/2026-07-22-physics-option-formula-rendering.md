# Physics Option Formula Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render standalone coefficient-variable tokens and spaced chained inequalities with one consistent KaTeX math font in knowledge-fill options and quick practice.

**Architecture:** Keep formula recognition centralized in `src/memory_course_web/rendering.py`. Extend the shared bare-math tokenizer so every existing caller receives the fix while raw option strings, answer values, and scoring remain untouched.

**Tech Stack:** Python 3, regular expressions, pytest, Streamlit HTML components, KaTeX

## Global Constraints

- Only display HTML changes; raw option text, `data-text`, correct answers, and submitted scoring values must remain unchanged.
- Knowledge display, fill word bank, and quick practice must continue to share one normalization path.
- Existing LaTeX delimiters, fractions, ordinary English, physical units, and case-sensitive `dB`/`DB`/`db` answers must remain supported.
- Do not modify DOCX parsing, payload validation, or question generation.

---

### Task 1: Add regression coverage for both component paths

**Files:**
- Modify: `tests/test_distractors.py:370`
- Modify: `tests/test_distractors.py:419`
- Modify: `tests/test_distractors.py:674`

**Interfaces:**
- Consumes: `_normalize_plain_math_for_latex(text: str) -> str`, `word_bank_html(word_bank: list[dict[str, Any]]) -> str`, and `practice_interaction_html(questions: list[dict[str, Any]], ...) -> str`.
- Produces: Regression tests that define the required normalized display and prove raw answer values are unchanged.

- [ ] **Step 1: Extend the shared-normalizer regression test**

Add these assertions to `test_rendering_keeps_numeric_coefficients_inside_bare_math_expressions`:

```python
assert _normalize_plain_math_for_latex("2f") == "$2f$"
assert _normalize_plain_math_for_latex("f < v < 2f") == "$f<v<2f$"
assert _normalize_plain_math_for_latex("3 m") == "3 m"
assert _normalize_plain_math_for_latex("3m") == "3m"
```

- [ ] **Step 2: Add a word-bank display regression test**

Add this test after `test_word_bank_normalizes_display_without_changing_raw_text`:

```python
def test_word_bank_normalizes_standalone_coefficient_without_changing_raw_text():
    word_bank = [
        {
            "number": 5,
            "option_id": "answer-b005",
            "text": "2f",
            "is_answer": True,
            "source_blank_id": "b005",
        }
    ]

    html = word_bank_html(word_bank)

    assert 'data-text="2f"' in html
    assert 'data-display-html="$2f$"' in html
    assert '<span class="word-bank-text">$2f$</span>' in html
```

- [ ] **Step 3: Add a quick-practice chained-expression regression test**

Add this test after `test_practice_interaction_html_normalizes_bare_math_tokens`:

```python
def test_practice_interaction_html_keeps_spaced_chain_in_one_math_node():
    html = practice_interaction_html(
        [
            {
                "display_index": 2,
                "original_index": 1,
                "category": "",
                "stem": "照相机成像时，像距 v 应满足",
                "correct": "f < v < 2f",
                "wrong": ["v > 2f", "v < f", "v = 2f"],
                "analysis": "",
                "options": ["v < f", "v = 2f", "v > 2f", "f < v < 2f"],
                "images": [],
            }
        ]
    )

    assert "$f&lt;v&lt;2f$" in html
    assert "$f&lt;v$ &lt; 2f" not in html
```

- [ ] **Step 4: Run the focused tests and verify the intended failures**

Run:

```powershell
python -m pytest -q tests/test_distractors.py -k "numeric_coefficients or standalone_coefficient or spaced_chain"
```

Expected: failures show that `2f` remains plain and `f < v < 2f` becomes the partial result `$f<v$ < 2f`; the physical-unit assertions pass.

- [ ] **Step 5: Commit the red tests**

```powershell
git add tests/test_distractors.py
git commit -m "Test formula rendering in answer options"
```

---

### Task 2: Extend the shared bare-math tokenizer

**Files:**
- Modify: `src/memory_course_web/rendering.py:246-298`
- Test: `tests/test_distractors.py`

**Interfaces:**
- Consumes: Plain display text passed through `_normalize_plain_math_for_latex(text: str) -> str`.
- Produces: Complete `$...$` delimiters for `2f` and `f < v < 2f`, while returning likely one-letter physical units unchanged.

- [ ] **Step 1: Add a conservative unit-suffix guard**

Near `_PLAIN_MATH_TOKEN_RE`, define the lowercase one-letter unit symbols that must not be interpreted as coefficient-variable expressions:

```python
_PLAIN_ONE_LETTER_UNIT_SUFFIXES = {"g", "h", "l", "m", "s"}
```

- [ ] **Step 2: Update expression and coefficient token branches**

Replace the current `expr` branch and add a `coef` branch immediately after it:

```python
r"|(?<![0-9A-Za-z\\])(?P<expr>[A-Za-z](?:\s*(?:>=|<=|!=|[+\-=<>≤≥≠^])\s*-?\s*(?:\d+(?:\.\d+)?\s*[A-Za-z]?|[A-Za-z]))+)"
r"|(?<![0-9A-Za-z\\.])(?P<coef>\d+(?:\.\d+)?[a-z])(?![0-9A-Za-z\\.])"
```

The `expr` branch accepts whitespace before every operator, so all comparisons in a chain remain in one match. The `coef` branch recognizes standalone adjacent coefficient-variable text without matching multi-letter units such as `mm`.

- [ ] **Step 3: Preserve likely one-letter units in the replacement function**

Add this guard near the start of `_plain_math_replacement`:

```python
if match.lastgroup == "coef" and token[-1] in _PLAIN_ONE_LETTER_UNIT_SUFFIXES:
    return token
```

- [ ] **Step 4: Run the focused regression tests**

Run:

```powershell
python -m pytest -q tests/test_distractors.py -k "numeric_coefficients or standalone_coefficient or spaced_chain"
```

Expected: all selected tests pass.

- [ ] **Step 5: Run all rendering tests**

Run:

```powershell
python -m pytest -q tests/test_distractors.py
```

Expected: all tests in `tests/test_distractors.py` pass, including unit protection, LaTeX preservation, case-sensitive options, fill interactions, and quick practice.

- [ ] **Step 6: Commit the implementation**

```powershell
git add src/memory_course_web/rendering.py
git commit -m "Fix formula rendering in answer options"
```

---

### Task 3: Verify the real course and the complete application

**Files:**
- Verify: `C:\Users\Romeo\Desktop\凸透镜的应用.docx`
- Verify: `app.py`
- Verify: `src/memory_course_web/rendering.py`

**Interfaces:**
- Consumes: The finished-course parser output and the shared display normalizer.
- Produces: Evidence that the real option values normalize completely and the application remains deployable.

- [ ] **Step 1: Verify values parsed from the real DOCX**

Run:

```powershell
python -c "from pathlib import Path; from src.memory_course_web.finished_course_parser import parse_finished_course; from src.memory_course_web.rendering import _normalize_plain_math_for_latex as n; p=parse_finished_course(Path(r'C:\Users\Romeo\Desktop\凸透镜的应用.docx')).to_payload(); q=next(q for q in p['quick_practice'] if q['correct'].replace(' ','')=='f<v<2f'); assert n(q['correct'])=='$f<v<2f$'; assert n('2f')=='$2f$'; print(q['correct'], '=>', n(q['correct'])); print('2f =>', n('2f'))"
```

Expected output contains:

```text
f < v < 2f => $f<v<2f$
2f => $2f$
```

- [ ] **Step 2: Run the full automated suite**

Run:

```powershell
python -m pytest -q
python -m compileall app.py src tests
```

Expected: pytest exits successfully with no failures; compileall exits with code 0.

- [ ] **Step 3: Perform browser rendering smoke verification**

Start the app on a free local port, upload `C:\Users\Romeo\Desktop\凸透镜的应用.docx`, and inspect the knowledge-fill word bank and quick-practice question containing `f < v < 2f`.

Expected:

- Standalone `f` and `2f` options both render through KaTeX.
- The complete `f < v < 2f` option is one KaTeX node with no ordinary-font tail.
- The browser console contains no KaTeX or component errors.
- Selecting and submitting the option still compares the original raw answer text.

- [ ] **Step 4: Inspect the final change set**

Run:

```powershell
git status --short
git diff HEAD~2 -- src/memory_course_web/rendering.py tests/test_distractors.py
```

Expected: only the intended tokenizer and regression-test changes appear; unrelated untracked workspace files remain untouched.


# Physics Formula Coefficient Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render coefficient-variable terms such as `2f` with one consistent math font inside bare physics expressions.

**Architecture:** Keep the existing DOCX parser and rendering pipeline unchanged. Add a focused regression test for the plain-text math normalizer, then extend only the expression atom in `_PLAIN_MATH_TOKEN_RE` so a numeric coefficient and its trailing variable stay in the same LaTeX span.

**Tech Stack:** Python 3, pytest, regular expressions, Streamlit HTML rendering, KaTeX

## Global Constraints

- Preserve existing LaTeX delimiters, fraction rendering, physics-unit protection, and English-prose protection.
- Do not change uploaded DOCX content or blank/practice parsing.
- Limit production changes to the bare-math expression matcher.

---

### Task 1: Keep coefficient variables inside one formula span

**Files:**
- Modify: `tests/test_distractors.py:312`
- Modify: `src/memory_course_web/rendering.py:248`

**Interfaces:**
- Consumes: `_normalize_plain_math_for_latex(text: str) -> str`
- Produces: The same function signature, with `u>2f` and `f<u<2f` normalized as whole expressions.

- [ ] **Step 1: Write the failing regression test**

```python
from src.memory_course_web.rendering import _normalize_plain_math_for_latex


def test_rendering_keeps_numeric_coefficients_inside_bare_math_expressions():
    assert _normalize_plain_math_for_latex("u>2f") == "$u>2f$"
    assert _normalize_plain_math_for_latex("f<u<2f") == "$f<u<2f$"
    assert _normalize_plain_math_for_latex("u<f") == "$u<f$"
```

- [ ] **Step 2: Run the test and verify the current split**

Run: `python -m pytest tests/test_distractors.py::test_rendering_keeps_numeric_coefficients_inside_bare_math_expressions -q`

Expected: FAIL because the current output is `$u>2$f` instead of `$u>2f$`.

- [ ] **Step 3: Extend the expression atom minimally**

Replace the `expr` branch in `_PLAIN_MATH_TOKEN_RE` with:

```python
r"|(?<![0-9A-Za-z\\])(?P<expr>[A-Za-z]\s*(?:(?:>=|<=|!=|[+\-=<>≤≥≠^])\s*-?\s*(?:\d+(?:\.\d+)?\s*[A-Za-z]?|[A-Za-z]))+)"
```

- [ ] **Step 4: Run focused and full verification**

Run: `python -m pytest tests/test_distractors.py::test_rendering_keeps_numeric_coefficients_inside_bare_math_expressions -q`

Expected: PASS.

Run: `python -m pytest -q`

Expected: all tests PASS.

Run: `python -m compileall app.py src tests`

Expected: compilation succeeds without syntax errors.

- [ ] **Step 5: Commit and synchronize**

```powershell
git add -- tests/test_distractors.py src/memory_course_web/rendering.py docs/superpowers/plans/2026-07-21-physics-formula-coefficient-rendering.md
git commit -m "Fix physics coefficient formula rendering"
git push origin main
```

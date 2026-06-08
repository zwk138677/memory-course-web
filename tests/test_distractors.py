from pathlib import Path

from src.memory_course_web.rendering import (
    _katex_inline_assets_html,
    build_word_bank,
    fill_interaction_html,
    fill_sheet_html,
    image_group_html,
    knowledge_html,
    practice_interaction_html,
    word_bank_html,
)
from src.memory_course_web.validation import validate_distractor_list, validate_finished_course_payload


def sample_payload():
    return {
        "title": "测试课程",
        "knowledge_paragraphs": [
            "知识小题1.alpha",
            "alpha beta gamma",
            "delta epsilon",
        ],
        "blanks": [
            {"id": "b001", "answer": "alpha", "paragraph_index": 1, "start": 0, "end": 5},
            {"id": "b002", "answer": "beta", "paragraph_index": 1, "start": 6, "end": 10},
        ],
        "distractor_groups": [
            {
                "id": "dg001",
                "title": "知识小题1.alpha",
                "paragraph_indexes": [0, 1, 2],
                "distractors": ["delta-wrong", "theta-wrong"],
                "source": "资料自带",
            }
        ],
        "quick_practice": [
            {"category": "基础辨析", "stem": "alpha 对应哪个选项？", "correct": "A", "wrong": ["B", "C", "D"]}
        ],
    }


def three_blank_payload():
    return {
        "title": "测试课程",
        "knowledge_paragraphs": ["知识小题1.alpha", "alpha beta gamma"],
        "blanks": [
            {"id": "b001", "answer": "alpha", "paragraph_index": 1, "start": 0, "end": 5},
            {"id": "b002", "answer": "beta", "paragraph_index": 1, "start": 6, "end": 10},
            {"id": "b003", "answer": "gamma", "paragraph_index": 1, "start": 11, "end": 16},
        ],
        "distractor_groups": [
            {
                "id": "dg001",
                "title": "知识小题1.alpha",
                "paragraph_indexes": [0, 1],
                "distractors": ["delta", "theta", "eta"],
                "source": "资料自带",
            }
        ],
        "quick_practice": [
            {"category": "基础辨析", "stem": "alpha 对应哪个选项？", "correct": "A", "wrong": ["B", "C", "D"]}
        ],
    }


def test_validate_distractor_list_rejects_answer_duplicate():
    try:
        validate_distractor_list("A", ["B", "A", "C"], "测试")
    except Exception as exc:
        assert "互不相同" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_payload_requires_self_contained_distractor_group_for_blank():
    payload = sample_payload()
    payload["distractor_groups"] = []

    try:
        validate_finished_course_payload(payload)
    except Exception as exc:
        assert "缺少“干扰项：”" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_payload_rejects_group_distractor_equal_to_item_answer():
    payload = sample_payload()
    payload["distractor_groups"][0]["distractors"] = ["alpha"]

    try:
        validate_finished_course_payload(payload)
    except Exception as exc:
        assert "不能和本知识小题填空答案相同" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_payload_accepts_shared_item_distractor_pool():
    payload = validate_finished_course_payload(sample_payload())

    assert payload["distractor_groups"][0]["distractors"] == ["delta-wrong", "theta-wrong"]
    assert "distractors" not in payload["blanks"][0]


def test_word_bank_uses_shared_item_distractor_pool():
    payload = validate_finished_course_payload(three_blank_payload())

    word_bank = build_word_bank(
        payload["blanks"],
        "shared-pool",
        distractor_groups=payload["distractor_groups"],
        paragraph_indexes=[0, 1],
    )
    texts = {item["text"] for item in word_bank}

    assert {"alpha", "beta", "gamma", "delta", "theta", "eta"} <= texts


def test_rendering_uses_character_positions_for_repeated_answers():
    payload = {
        "knowledge_paragraphs": ["A B A"],
        "blanks": [{"id": "b001", "answer": "A", "paragraph_index": 0, "start": 4, "end": 5}],
    }

    html = knowledge_html(payload["knowledge_paragraphs"], payload["blanks"])

    assert "A B <span" in html


def test_knowledge_item_headings_render_with_section_style():
    html = knowledge_html(["知识小题1.定义", "alpha"], [])

    assert '<div class="knowledge-item-heading" role="heading" aria-level="3">' in html
    assert '<span class="knowledge-item-heading-marker" aria-hidden="true"></span>' in html
    assert '<span class="knowledge-item-heading-text">知识小题1.定义</span>' in html
    assert "<p>知识小题1.定义</p>" not in html
    assert "<p>alpha</p>" in html


def test_fill_interaction_html_styles_knowledge_item_headings():
    blanks = [{"id": "b001", "answer": "alpha", "paragraph_index": 1, "start": 0, "end": 5}]
    html = fill_interaction_html(
        ["知识小题1.定义", "alpha"],
        blanks,
        [],
        distractor_groups=[{"paragraph_indexes": [0, 1], "distractors": ["beta"]}],
    )

    assert '<div class="knowledge-item-heading" role="heading" aria-level="3">' in html
    assert ".knowledge-item-heading" in html
    assert "<p>知识小题1.定义</p>" not in html
    assert 'class="fill-page active"' in html


def test_rendering_keeps_paragraph_images():
    html = knowledge_html(
        [""],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "diagram.svg",
                "mime_type": "image/svg+xml",
                "data_uri": "data:image/svg+xml;base64,PHN2Zy8+",
                "renderable": True,
            }
        ],
    )

    assert "course-image" in html
    assert "diagram.svg" in image_group_html(
        [{"filename": "diagram.svg", "mime_type": "image/svg+xml", "data_uri": "", "renderable": False}]
    )


def test_rendering_inserts_inline_formula_without_placeholder():
    html = knowledge_html(
        ["a=)"],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "formula.png",
                "mime_type": "image/png",
                "data_uri": "data:image/png;base64,AA==",
                "renderable": True,
                "inline": True,
                "char_index": 2,
                "kind": "formula",
            }
        ],
    )

    assert 'class="inline-formula"' in html
    assert "course-image-placeholder" not in html
    assert "a=<img" in html


def test_rendering_inserts_inline_formula_text_without_image():
    html = knowledge_html(
        ["圆周角=）"],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "",
                "mime_type": "text/plain",
                "data_uri": "",
                "renderable": True,
                "inline": True,
                "char_index": 4,
                "kind": "formula_text",
                "formula_text": "1/2圆心角",
            }
        ],
    )

    assert 'class="inline-formula-text"' in html
    assert 'class="inline-formula-frac"' in html
    assert "vertical-align:middle" in html
    assert "translateY(-0.06em)" in html
    assert "vertical-align:-0.28em" not in html
    assert 'class="frac-top"' in html
    assert ">1</span>" in html
    assert 'class="frac-bottom"' in html
    assert ">2</span>" in html
    assert "圆心角" in html
    assert 'class="inline-formula"' not in html
    assert "course-image-placeholder" not in html


def test_rendering_splits_literal_text_fraction():
    html = knowledge_html(["圆周角=1/2圆心角"], [])

    assert 'class="inline-formula-frac"' in html
    assert 'class="frac-top"' in html
    assert ">1</span>" in html
    assert 'class="frac-bottom"' in html
    assert ">2</span>" in html
    assert "圆心角" in html
    assert "1/2圆心角" not in html


def test_rendering_keeps_non_fraction_formula_text_plain():
    html = knowledge_html(
        ["angle="],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "",
                "mime_type": "text/plain",
                "data_uri": "",
                "renderable": True,
                "inline": True,
                "char_index": 6,
                "kind": "formula_text",
                "formula_text": "90°",
            }
        ],
    )

    assert 'class="inline-formula-text"' in html
    assert 'class="inline-formula-frac"' not in html
    assert "90°" in html
    assert 'class="inline-formula"' not in html


def test_rendering_does_not_split_complex_fraction_text():
    html = knowledge_html(
        ["x="],
        [],
        [
            {
                "paragraph_index": 0,
                "filename": "",
                "mime_type": "text/plain",
                "data_uri": "",
                "renderable": True,
                "inline": True,
                "char_index": 2,
                "kind": "formula_text",
                "formula_text": "a/b/c",
            }
        ],
    )

    assert 'class="inline-formula-text"' in html
    assert 'class="inline-formula-frac"' not in html
    assert "a/b/c" in html


def test_rendering_does_not_split_complex_literal_fraction_text():
    html = knowledge_html(["x=a/b/c"], [])

    assert 'class="inline-formula-frac"' not in html
    assert "a/b/c" in html


def test_rendering_preserves_latex_delimiters_for_katex():
    html = knowledge_html([r"$1/2$ and 1/2 and \(\sqrt{x}\)"], [])

    assert "$1/2$" in html
    assert r"\(\sqrt{x}\)" in html
    assert html.count('class="inline-formula-frac"') == 1
    assert "katex-inline-assets" in html
    assert "renderMathInElement" in html


def test_rendering_normalizes_bare_math_tokens_for_katex():
    html = knowledge_html(["\u53d8\u91cf a satisfies a>=0, x²=9, |a|, π+1, and 0"], [])

    assert "$a$" in html
    assert r"$a\ge 0$" in html
    assert "$x^2=9$" in html
    assert "$|a|$" in html
    assert r"$\pi+1$" in html
    assert "$0$" in html
    assert "and $0$" in html


def test_rendering_does_not_double_wrap_existing_latex():
    html = knowledge_html([r"$\sqrt{a}$ and a"], [])

    assert html.count(r"$\sqrt{a}$") == 1
    assert "$a$" in html
    assert "$$a$$" not in html


def test_rendering_does_not_normalize_physics_units_or_english_articles():
    html = knowledge_html(["speed is 10 m/s, distance is 3 m, and not a section"], [])

    assert "10 m/s" in html
    assert "3 m" in html
    assert "not a section" in html
    assert "$m/s$" not in html
    assert "$m$" not in html
    assert 'class="inline-formula-frac"' not in html


def test_inline_katex_assets_embed_woff2_fonts():
    html = _katex_inline_assets_html()

    assert "data:font/woff2;base64," in html
    assert "fonts/KaTeX_Main-Regular.woff2" not in html


def test_word_bank_visible_text_preserves_latex():
    word_bank = [
        {
            "number": 1,
            "option_id": "answer-b001",
            "text": r"$x^2$",
            "is_answer": True,
            "source_blank_id": "b001",
        }
    ]

    html = word_bank_html(word_bank)

    assert r"$x^2$" in html
    assert 'data-text="$x^2$"' in html


def test_word_bank_normalizes_display_without_changing_raw_text():
    word_bank = [
        {
            "number": 1,
            "option_id": "answer-b001",
            "text": "a>=0",
            "is_answer": True,
            "source_blank_id": "b001",
        }
    ]

    html = word_bank_html(word_bank)

    assert 'data-text="a&gt;=0"' in html
    assert 'data-display-html="' in html
    assert r"$a\ge 0$" in html


def test_word_bank_uses_one_to_one_distractor_ratio():
    blanks = [
        {"id": "b001", "answer": "alpha", "distractors": ["delta"]},
        {"id": "b002", "answer": "beta", "distractors": ["eta"]},
    ]

    word_bank = build_word_bank(blanks, "sample")

    answer_count = sum(1 for item in word_bank if item["is_answer"])
    distractor_count = len(word_bank) - answer_count
    assert answer_count == 2
    assert distractor_count == 2
    assert {item["number"] for item in word_bank} == {1, 2, 3, 4}
    assert "word-bank-item" in word_bank_html(word_bank)


def test_word_bank_counts_repeated_answers_by_blank():
    blanks = []
    for index in range(11):
        answer = "same" if index < 2 else f"answer-{index}"
        blanks.append(
            {
                "id": f"b{index + 1:03d}",
                "answer": answer,
                "distractors": [f"wrong-{index}"],
            }
        )

    word_bank = build_word_bank(blanks, "repeated")

    assert len(word_bank) == 22
    assert sum(1 for item in word_bank if item["is_answer"]) == 11
    assert sum(1 for item in word_bank if not item["is_answer"]) == 11
    assert sum(1 for item in word_bank if item["text"] == "same" and item["is_answer"]) == 2


def test_fill_sheet_hides_all_answers_at_once():
    html = fill_sheet_html(
        ["alpha and beta"],
        [
            {"id": "b001", "answer": "alpha", "paragraph_index": 0, "start": 0, "end": 5},
            {"id": "b002", "answer": "beta", "paragraph_index": 0, "start": 10, "end": 14},
        ],
    )

    assert "<p>alpha" not in html
    assert "and beta" not in html
    assert html.count("word-blank") >= 2


def test_fill_sheet_uses_uniform_blank_placeholder_width():
    html = fill_sheet_html(
        ["A and verylonganswer"],
        [
            {"id": "b001", "answer": "A", "paragraph_index": 0, "start": 0, "end": 1},
            {"id": "b002", "answer": "verylonganswer", "paragraph_index": 0, "start": 6, "end": 20},
        ],
    )

    assert html.count('<span class="word-blank-line">______</span>') == 2
    assert "____________" not in html
    assert ">verylonganswer<" not in html


def test_fill_interaction_html_contains_drag_click_and_check_controls():
    blanks = [{"id": "b001", "answer": "alpha", "paragraph_index": 0, "start": 0, "end": 5, "distractors": ["delta"]}]
    word_bank = build_word_bank(blanks, "interactive")

    html = fill_interaction_html(["alpha"], blanks, [], word_bank)

    assert 'draggable="true"' in html
    assert 'data-blank-id="b001"' in html
    assert 'addEventListener("drop"' in html
    assert "提交检查" in html
    assert "重做" in html
    assert "共 " not in html
    assert "word-bank-title" in html
    assert "fill-sheet" in html
    assert "katex-inline-assets" in html
    assert ".word-blank.filled .word-blank-number" in html
    assert "gap: .82rem" in html
    assert html.index('id="goNextPage"') < html.index('id="resetAnswers"')
    assert html.index('id="enterPractice"') < html.index('id="resetAnswers"')


def test_fill_interaction_html_displays_normalized_math_but_checks_raw_text():
    blanks = [{"id": "b001", "answer": "a>=0", "paragraph_index": 0, "start": 0, "end": 4}]
    word_bank = build_word_bank(blanks, "math-fill")

    html = fill_interaction_html(["a>=0"], blanks, [], word_bank)

    assert 'data-answer="a&gt;=0"' in html
    assert 'data-text="a&gt;=0"' in html
    assert r"$a\ge 0$" in html
    assert "answer.innerHTML = option.dataset.displayHtml" in html
    assert "blank.dataset.filledText = rawText" in html


def test_fill_interaction_html_paginates_numbered_sections():
    paragraphs = ["1", "alpha", "2", "beta"]
    blanks = [
        {"id": "b001", "answer": "alpha", "paragraph_index": 1, "start": 0, "end": 5, "distractors": ["delta"]},
        {"id": "b002", "answer": "beta", "paragraph_index": 3, "start": 0, "end": 4, "distractors": ["theta"]},
    ]
    word_bank = build_word_bank(blanks, "paged")

    html = fill_interaction_html(paragraphs, blanks, [], word_bank, course_cid="course123")

    assert 'class="fill-page active"' in html
    assert 'class="fill-page"' in html
    assert 'data-page-target="0"' in html
    assert 'data-page-target="1"' in html
    assert "‹ 上一页" not in html
    assert "下一页 ›" not in html
    assert "data-page-prev" not in html
    assert "data-page-next" not in html
    assert "button.addEventListener(\"click\", () => showPage(Number(button.dataset.pageTarget" not in html
    assert 'id="goNextPage"' in html
    assert 'id="enterPractice"' in html
    assert 'target="_top"' not in html
    assert "flow_action" not in html
    assert "notifyPracticeReady" in html
    assert "requestFillResize" in html
    assert "window.__fillWidgetApi" in html
    assert "restoreState(window.__fillSavedState)" in html
    assert "blank.dataset.filledText" in html
    assert "window.parent.location" not in html
    assert "accuracy >= 0.6" in html
    assert "本页正确率" in html


def test_fill_interaction_html_paginates_chinese_numbered_headings_without_spaces():
    paragraphs = ["\u4e00\u3001alpha", "first", "3.14 is not a section", "middle", "\u4e8c\u3001beta", "second"]
    blanks = [
        {"id": "b001", "answer": "first", "paragraph_index": 1, "start": 0, "end": 5, "distractors": ["delta"]},
        {"id": "b002", "answer": "second", "paragraph_index": 5, "start": 0, "end": 6, "distractors": ["theta"]},
    ]
    word_bank = build_word_bank(blanks, "cn-paged")

    html = fill_interaction_html(paragraphs, blanks, [], word_bank)

    assert 'data-page-target="0"' in html
    assert 'data-page-target="1"' in html
    assert 'data-page-target="2"' not in html
    nav_start = html.index('class="fill-page-nav"')
    nav_end = html.index("</nav>", nav_start)
    nav = html[nav_start:nav_end]
    assert ">1</span>" in nav
    assert ">2</span>" in nav
    assert "\u4e00</span>" not in nav
    assert "\u4e8c</span>" not in nav
    first_page_start = html.index('class="fill-page active"')
    second_page_start = html.index('class="fill-page"', first_page_start + 1)
    first_page = html[first_page_start:second_page_start]
    second_page = html[second_page_start:]
    assert "\u4e00\u3001alpha" in first_page
    assert "3.14 is not a section" in first_page
    assert "\u4e8c\u3001beta" not in first_page
    assert "\u4e8c\u3001beta" in second_page
    assert "second" in second_page


def test_fill_component_restores_state_without_global_mutation_observer():
    component_html = Path("src/memory_course_web/fill_component/index.html").read_text(encoding="utf-8")

    assert "collectFillState" in component_html
    assert "restoreFillState" in component_html
    assert "window.__fillWidgetApi.collectState" in component_html
    assert "window.__fillSavedState = previousState" in component_html
    assert "/app/static/katex/katex.min.css" in component_html
    assert "/app/static/katex/katex.min.js" in component_html
    assert "/app/static/katex/auto-render.min.js" in component_html
    assert "renderMathInElement" in component_html
    assert ".katex" in component_html
    assert "font-size: 1.08em" in component_html
    assert "vertical-align: -0.06em" in component_html
    assert "line-height: 1.08" in component_html
    assert "MutationObserver" not in component_html


def test_practice_component_loads_local_katex_assets():
    component_html = Path("src/memory_course_web/practice_component/index.html").read_text(encoding="utf-8")

    assert "/app/static/katex/katex.min.css" in component_html
    assert "/app/static/katex/katex.min.js" in component_html
    assert "/app/static/katex/auto-render.min.js" in component_html
    assert "renderMathInElement" in component_html
    assert ".katex" in component_html
    assert "font-size: 1.08em" in component_html
    assert "vertical-align: -0.06em" in component_html


def test_html_component_loads_local_katex_assets():
    component_html = Path("src/memory_course_web/html_component/index.html").read_text(encoding="utf-8")

    assert "/app/static/katex/katex.min.css" in component_html
    assert "/app/static/katex/katex.min.js" in component_html
    assert "/app/static/katex/auto-render.min.js" in component_html
    assert "renderMathInElement" in component_html
    assert ".katex" in component_html
    assert "font-size: 1.08em" in component_html
    assert "vertical-align: -0.06em" in component_html
    assert ".knowledge-body p" in component_html
    assert ".answer-mark" in component_html


def test_static_katex_assets_are_present():
    assert Path("static/katex/katex.min.css").exists()
    assert Path("static/katex/katex.min.js").exists()
    assert Path("static/katex/auto-render.min.js").exists()
    assert any(Path("static/katex/fonts").glob("KaTeX_Main-Regular.*"))


def test_practice_interaction_html_contains_latex_and_submit_payload():
    html = practice_interaction_html(
        [
            {
                "display_index": 1,
                "original_index": 0,
                "category": "",
                "stem": r"计算 $\frac{1}{2}+x$",
                "correct": r"$x$",
                "wrong": [r"$2x$", "1"],
                "analysis": r"保留 $\frac{1}{2}$。",
                "options": [r"$x$", r"$2x$", "1"],
                "images": [],
            }
        ]
    )

    assert r"$\frac{1}{2}+x$" in html
    assert r"$x$" in html
    assert "katex-inline-assets" in html
    assert "practice_submitted" in html
    assert "notifyPracticeSubmitted" in html


def test_practice_interaction_html_normalizes_bare_math_tokens():
    html = practice_interaction_html(
        [
            {
                "display_index": 1,
                "original_index": 0,
                "category": "",
                "stem": "When a>=0, choose x²=9, |a|, and \u03c0+1.",
                "correct": "a>=0",
                "wrong": ["a<0", "x=0", "plain words"],
                "analysis": "Use |a| and \u03c0+1.",
                "options": ["a>=0", "a<0", "x=0", "plain words"],
                "images": [],
            }
        ]
    )

    assert r"$a\ge 0$" in html
    assert "$x^2=9$" in html
    assert "$a&lt;0$" in html
    assert "$x=0$" in html
    assert "$|a|$" in html
    assert r"$\pi+1$" in html
    assert "plain words" in html


def test_fill_interaction_html_page_word_banks_only_include_page_options():
    paragraphs = ["1", "alpha", "2", "beta"]
    blanks = [
        {"id": "b001", "answer": "alpha", "paragraph_index": 1, "start": 0, "end": 5},
        {"id": "b002", "answer": "beta", "paragraph_index": 3, "start": 0, "end": 4},
    ]
    distractor_groups = [
        {"id": "dg001", "paragraph_indexes": [0, 1], "distractors": ["delta"], "source": "资料自带"},
        {"id": "dg002", "paragraph_indexes": [2, 3], "distractors": ["theta"], "source": "资料自带"},
    ]

    html = fill_interaction_html(paragraphs, blanks, [], distractor_groups=distractor_groups)

    first_bank_start = html.index('class="word-bank-page active"')
    second_bank_start = html.index('class="word-bank-page"', first_bank_start + 1)
    first_bank = html[first_bank_start:second_bank_start]
    second_bank = html[second_bank_start:]
    assert "alpha" in first_bank
    assert "delta" in first_bank
    assert "beta" not in first_bank
    assert "theta" not in first_bank
    assert "beta" in second_bank
    assert "theta" in second_bank


def test_fill_interaction_html_paginates_knowledge_item_sections():
    paragraphs = ["知识小题1.物质构成", "alpha", "知识小题2.分子热运动", "beta"]
    blanks = [
        {"id": "b001", "answer": "alpha", "paragraph_index": 1, "start": 0, "end": 5},
        {"id": "b002", "answer": "beta", "paragraph_index": 3, "start": 0, "end": 4},
    ]
    distractor_groups = [
        {"id": "dg001", "paragraph_indexes": [0, 1], "distractors": ["delta"], "source": "资料自带"},
        {"id": "dg002", "paragraph_indexes": [2, 3], "distractors": ["theta"], "source": "资料自带"},
    ]

    html = fill_interaction_html(paragraphs, blanks, [], distractor_groups=distractor_groups)

    assert 'data-page-target="0"' in html
    assert 'data-page-target="1"' in html
    first_page_start = html.index('class="fill-page active"')
    second_page_start = html.index('class="fill-page"', first_page_start + 1)
    first_page = html[first_page_start:second_page_start]
    second_page = html[second_page_start:]
    assert "知识小题1.物质构成" in first_page
    assert "alpha" in first_page
    assert "知识小题2.分子热运动" not in first_page
    assert "知识小题2.分子热运动" in second_page
    assert "beta" in second_page

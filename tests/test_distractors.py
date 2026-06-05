from pathlib import Path

from src.memory_course_web.distractors import fallback_distractors_for_blank
from src.memory_course_web import generation
from src.memory_course_web.generation import DeepSeekConfig, generate_blank_distractors
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
            "alpha beta gamma",
            "delta epsilon",
        ],
        "blanks": [
            {"id": "b001", "answer": "alpha", "paragraph_index": 0, "start": 0, "end": 5, "distractors": [], "distractor_source": ""},
            {"id": "b002", "answer": "beta", "paragraph_index": 0, "start": 6, "end": 10, "distractors": [], "distractor_source": ""},
        ],
        "quick_practice": [
            {"category": "基础辨析", "stem": "alpha 对应哪个选项？", "correct": "A", "wrong": ["B", "C", "D"]}
        ],
    }


def three_blank_payload():
    return {
        "title": "测试课程",
        "knowledge_paragraphs": ["alpha beta gamma"],
        "blanks": [
            {"id": "b001", "answer": "alpha", "paragraph_index": 0, "start": 0, "end": 5, "distractors": [], "distractor_source": ""},
            {"id": "b002", "answer": "beta", "paragraph_index": 0, "start": 6, "end": 10, "distractors": [], "distractor_source": ""},
            {"id": "b003", "answer": "gamma", "paragraph_index": 0, "start": 11, "end": 16, "distractors": [], "distractor_source": ""},
        ],
        "quick_practice": [
            {"category": "基础辨析", "stem": "alpha 对应哪个选项？", "correct": "A", "wrong": ["B", "C", "D"]}
        ],
    }


def install_fake_openai(monkeypatch, responses):
    calls = []
    response_queue = list(responses)

    class FakeMessage:
        def __init__(self, content):
            self.content = content

    class FakeChoice:
        def __init__(self, content):
            self.message = FakeMessage(content)

    class FakeResponse:
        def __init__(self, content):
            self.choices = [FakeChoice(content)]

    class FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if not response_queue:
                raise AssertionError("unexpected DeepSeek call")
            response = response_queue.pop(0)
            if isinstance(response, Exception):
                raise response
            return FakeResponse(response)

    class FakeOpenAI:
        def __init__(self, *, api_key, base_url, timeout):
            self.api_key = api_key
            self.base_url = base_url
            self.timeout = timeout
            self.chat = type("FakeChat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr(generation, "OpenAI", FakeOpenAI)
    return calls


def test_validate_distractor_list_rejects_answer_duplicate():
    try:
        validate_distractor_list("A", ["B", "A", "C"], "测试")
    except Exception as exc:
        assert "互不相同" in str(exc)
    else:
        raise AssertionError("expected validation error")


def test_code_fallback_generates_three_distinct_distractors():
    payload = validate_finished_course_payload(sample_payload())
    distractors = fallback_distractors_for_blank(payload["blanks"][0], payload)

    assert len(distractors) == 3
    assert len(set(distractors + [payload["blanks"][0]["answer"]])) == 4
    assert not any(item.startswith("干扰项") for item in distractors)


def test_code_fallback_does_not_expose_placeholder_when_pool_is_sparse():
    payload = validate_finished_course_payload(
        {
            "title": "empty",
            "knowledge_paragraphs": ["A"],
            "blanks": [
                {"id": "b001", "answer": "A", "paragraph_index": 0, "start": 0, "end": 1, "distractors": [], "distractor_source": ""}
            ],
            "quick_practice": [{"category": "基础辨析", "stem": "A 是什么？", "correct": "A", "wrong": ["B", "C", "D"]}],
        }
    )

    distractors = fallback_distractors_for_blank(payload["blanks"][0], payload)

    assert len(distractors) == 3
    assert not any(item.startswith("干扰项") for item in distractors)


def test_no_api_key_uses_one_code_fallback_for_each_blank():
    payload = generate_blank_distractors(sample_payload(), DeepSeekConfig(api_key=""))

    assert {blank["distractor_source"] for blank in payload["blanks"]} == {"代码兜底"}
    assert all(len(blank["distractors"]) == 1 for blank in payload["blanks"])
    answer_keys = {blank["answer"].casefold() for blank in payload["blanks"]}
    distractor_keys = {blank["distractors"][0].casefold() for blank in payload["blanks"]}
    assert not answer_keys & distractor_keys
    assert len(distractor_keys) == len(payload["blanks"])
    assert not any(item.startswith("干扰项") for item in distractor_keys)


def test_deepseek_partial_batch_keeps_valid_items_and_only_fallbacks_missing(monkeypatch):
    calls = install_fake_openai(
        monkeypatch,
        [
            '{"items":[{"id":"b001","distractor":"delta"}]}',
            '{"items":[{"id":"b002","distractor":"theta"}]}',
        ],
    )

    payload = generate_blank_distractors(three_blank_payload(), DeepSeekConfig(api_key="key"), batch_size=3)

    assert [blank["distractor_source"] for blank in payload["blanks"]] == ["DeepSeek", "DeepSeek重试", "代码兜底"]
    assert payload["blanks"][0]["distractors"] == ["delta"]
    assert payload["blanks"][1]["distractors"] == ["theta"]
    assert payload["distractor_summary"] == {"DeepSeek": 1, "DeepSeek重试": 1, "代码兜底": 1}
    assert payload["distractor_diagnostics"]["failure_summary"]["缺项"] == 3
    assert calls[0]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert calls[0]["reasoning_effort"] == "high"


def test_deepseek_empty_first_attempt_then_retry_success_marks_retry(monkeypatch):
    install_fake_openai(
        monkeypatch,
        [
            "",
            '{"items":[{"id":"b001","distractor":"delta"},{"id":"b002","distractor":"theta"}]}',
        ],
    )
    progress_events = []

    payload = generate_blank_distractors(
        sample_payload(),
        DeepSeekConfig(api_key="key"),
        progress_callback=progress_events.append,
    )

    assert {blank["distractor_source"] for blank in payload["blanks"]} == {"DeepSeek重试"}
    assert payload["distractor_summary"] == {"DeepSeek重试": 2}
    assert payload["distractor_diagnostics"]["failure_summary"]["空返回"] == 1
    assert [event["attempt"] for event in progress_events] == [1, 2]


def test_deepseek_invalid_placeholder_after_retries_uses_code_fallback(monkeypatch):
    install_fake_openai(
        monkeypatch,
        [
            '{"items":[{"id":"b001","distractor":"干扰项23"}]}',
            '{"items":[{"id":"b001","distractor":"干扰项24"}]}',
        ],
    )
    payload = {
        "title": "测试课程",
        "knowledge_paragraphs": ["圆心角"],
        "blanks": [
            {"id": "b001", "answer": "圆心角", "paragraph_index": 0, "start": 0, "end": 3, "distractors": [], "distractor_source": ""}
        ],
        "quick_practice": [{"category": "基础辨析", "stem": "圆心角是什么？", "correct": "A", "wrong": ["B", "C", "D"]}],
    }

    result = generate_blank_distractors(payload, DeepSeekConfig(api_key="key"))

    assert result["blanks"][0]["distractor_source"] == "代码兜底"
    assert result["blanks"][0]["distractors"][0] != "干扰项23"
    assert not result["blanks"][0]["distractors"][0].startswith("干扰项")
    assert result["distractor_diagnostics"]["failure_summary"]["无效项"] == 2


def test_word_bank_replaces_existing_placeholder_distractor():
    blanks = [
        {
            "id": "b001",
            "answer": "圆心角",
            "paragraph_index": 0,
            "start": 0,
            "end": 3,
            "distractors": ["干扰项23"],
            "distractor_source": "代码兜底",
        }
    ]

    word_bank = build_word_bank(blanks, "placeholder")
    distractors = [item["text"] for item in word_bank if not item["is_answer"]]

    assert len(distractors) == 1
    assert distractors[0] != "干扰项23"
    assert not distractors[0].startswith("干扰项")


def test_rendering_uses_character_positions_for_repeated_answers():
    payload = {
        "knowledge_paragraphs": ["A B A"],
        "blanks": [{"id": "b001", "answer": "A", "paragraph_index": 0, "start": 4, "end": 5}],
    }

    html = knowledge_html(payload["knowledge_paragraphs"], payload["blanks"])

    assert "A B <span" in html


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


def test_fill_interaction_html_page_word_banks_only_include_page_options():
    paragraphs = ["1", "alpha", "2", "beta"]
    blanks = [
        {"id": "b001", "answer": "alpha", "paragraph_index": 1, "start": 0, "end": 5, "distractors": ["delta"]},
        {"id": "b002", "answer": "beta", "paragraph_index": 3, "start": 0, "end": 4, "distractors": ["theta"]},
    ]
    word_bank = build_word_bank(blanks, "paged-bank")

    html = fill_interaction_html(paragraphs, blanks, [], word_bank)

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
        {"id": "b001", "answer": "alpha", "paragraph_index": 1, "start": 0, "end": 5, "distractors": ["delta"]},
        {"id": "b002", "answer": "beta", "paragraph_index": 3, "start": 0, "end": 4, "distractors": ["theta"]},
    ]
    word_bank = build_word_bank(blanks, "physics-paged-bank")

    html = fill_interaction_html(paragraphs, blanks, [], word_bank)

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

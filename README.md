# Streamlit 成品背记资料学习页

这个项目用于上传已经由 `knowledge-list-extractor` 生成好的成品背记课 Word 文件，并把内容组织成网页学习模式。

网页会识别：

- 知识展示：来自 Word 成品里的知识正文。
- 知识填空：来自 Word 成品里的下划线内容。
- 快速练习：直接复用 Word 成品里的题干、正确选项和错误选项。

DeepSeek 现在只负责给“知识填空”的下划线答案生成 3 个干扰项。没有 API Key 或模型返回不合格时，网页会使用代码兜底生成干扰项，并在页面上标明来源。

## 本地运行

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## DeepSeek 配置

本地可以把真实 Key 放在 `.streamlit/secrets.toml`：

```toml
DEEPSEEK_API_KEY = "sk-..."
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"
```

`.streamlit/secrets.toml` 已经被 `.gitignore` 忽略，不要提交真实 Key。部署到 Streamlit Cloud 时，需要在应用的 Secrets 面板里配置同样三行。

没有配置 `DEEPSEEK_API_KEY` 时，应用仍可使用，只是填空干扰项会显示为“代码兜底”。

## 上传文件要求

- 只支持 `.docx`。
- 上传文件应是已经生成好的背记课成品，而不是原始讲义。
- 支持含 `第一部分：《知识小题》` / `第二部分：《快速练习》` 的旧结构。
- 支持后处理后的结构：标题、知识正文、`【题目内容】` 开头的快速练习。
- 已支持识别并展示 Word 正文和快速练习中的常见网页图片格式（PNG/JPEG/SVG/GIF/WebP/BMP）。
- Word 专用的 EMF/WMF 图片会被识别出来并显示占位提示，后续可接入图片转换能力进一步还原。
- 第一版仍以文字和静态图片为主，不额外还原 Word 公式、表格的高保真排版。

## 测试

```powershell
python -m pytest -q
python -m compileall app.py src tests
```

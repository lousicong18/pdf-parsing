# PDF Parser Demo

PDF 图文混排解析 Demo：混合流水线（MinerU + VLM OCR）+ 精度优先架构（Block = 结构化真相源，Markdown = 派生视图）。

## 启动

### 后端

```bash
uv sync
cp .env.example .env      # 填写 VLM_BASE_URL / VLM_API_KEY 等
uv run python -m src.server
# listen on http://0.0.0.0:8082
```

### 前端

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173 (vite proxy /api -> 8082)
```

## 配置（.env）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `VLM_BASE_URL` | — | OpenAI 兼容 VLM 端点（智谱 / 通义 / DeepSeek / MiniMax） |
| `VLM_API_KEY` | — | API Key |
| `VLM_MODEL` | `MiniMax-M3` | 默认模型 |
| `MAX_FILE_MB` | `50` | 上传上限 |
| `HOST` / `PORT` | `0.0.0.0` / `8082` | 监听地址 |

### 分类阈值（`CLS_*`）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CLS_LINE_COUNT_TABLE` | `20` | 行数 ≥ 该值判 table |
| `CLS_TEXT_BLOCKS_MIN` | `4` | text_blocks ≥ 该值辅助判 table |
| `CLS_AREA_RATIO_MIN` | `0.15` | 密集线面积比 ≥ 该值判 table |
| `CLS_DRAWINGS_PATH_MIXED` | `200` | 矢量路径数 ≥ 该值判 mixed |

## 混合流水线

页面按类型路由到最优工具，输出统一 Block 格式：

| 页面类型 | 工具 | 原因 |
| --- | --- | --- |
| `text` / `table` | **MinerU** | 结构保留好，公式转 LaTeX |
| `mixed` + 图表表格 | **VLM OCR** | 唯一能读图表数据（散点/柱状/折线） |
| `mixed` + 普通图文 | **MinerU** + **VLM 描述图片** | MinerU 提取文字结构，VLM 描述图片内容 |
| `scan` | **VLM OCR** | 扫描件 OCR |

```
classify → dispatch
            ├─ text/table ──→ MinerU ──→ fallback 原提取器
            ├─ mixed + chart ──→ VLM OCR
            ├─ mixed + 图文 ──→ MinerU(文字) + VLM(描述图片)
            └─ scan ──→ VLM OCR
```

### 安装 MinerU（可选）

```bash
uv pip install "mineru[pipeline]"
mineru-models-download -s modelscope
```

不装 MinerU 时自动 fallback 到原提取器。

## API

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/parse` | 上传 PDF，创建解析任务（`file`, 可选 `vlm_model`） |
| `GET` | `/api/v1/tasks` | 任务列表 |
| `GET` | `/api/v1/tasks/{task_id}` | 任务详情（完整 Block + 特征 + 成本） |
| `GET` | `/api/v1/tasks/{task_id}/export` | 导出 Markdown |
| `GET` | `/api/v1/tasks/{task_id}/export_kb` | 导出知识库 Markdown（分块） |
| `GET` | `/api/v1/tasks/{task_id}/images/{page}/{index}` | 获取页面渲染图 |
| `GET` | `/api/v1/models` | 可用模型列表 |

## 架构

```
┌─────────────────────────────────────────────────────┐
│ 前端 (Vue 3 + Vite)                                  │
│   JSON 视图 / Markdown 视图 / 知识库视图 / 成本面板    │
└────────────────────┬────────────────────────────────┘
                     │ /api/v1
┌────────────────────▼────────────────────────────────┐
│ FastAPI 服务层                                       │
│   parse / task / export / kb_export / image / models │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│ 任务管理 (task_manager + task_store)                 │
│   创建 → 解析 → 持久化 (JSON on disk)                │
└────────────────────┬────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────┐
│ 解析 pipeline                                        │
│   classify → dispatch(text/table/mixed/scan)         │
│   mineru_parser / extract_text / extract_table       │
│   mixed / scan / vlm                                 │
└─────────────────────────────────────────────────────┘
```

### 数据模型（Block）

```python
Block:
  type: "text" | "table" | "image"
  bbox: [x0, y0, x1, y1]
  page_type: "text" | "table" | "mixed" | "scan"
  order: int
  text: str | None          # type=text 时
  table: TableData | None   # type=table 时（结构化行列）
  image: ImageData | None   # type=image 时
  content: str              # markdown 内容（派生视图）
```

## 目录结构

```
src/
├── server.py              # FastAPI 入口
├── controller/            # REST 控制器
│   ├── parse_controller.py
│   ├── task_controller.py
│   ├── export_controller.py
│   ├── kb_export_controller.py
│   ├── image_controller.py
│   └── models_controller.py
├── models/schemas.py      # Pydantic 数据模型
├── parser/                # 解析核心
│   ├── pipeline.py        # 页面分发（混合路由）
│   ├── classify.py        # 分类 + 特征提取
│   ├── mineru_parser.py   # MinerU CLI 包装器
│   ├── extract_text.py    # 文本抽取（fallback）
│   ├── extract_table.py   # 表格抽取（fallback）
│   ├── mixed.py           # 图文混排页（图表表格检测 + VLM OCR）
│   ├── scan.py            # 扫描件 OCR
│   ├── formula.py         # 公式检测
│   └── vlm.py             # VLM 调用
├── task_manager/          # 任务调度 / 进度
├── store/                 # 任务持久化 / 图片缓存
└── utils/                 # 配置 / PDF 工具
```

## MCP Server

PDF 解析 MCP Server，通过 stdio 传输，可集成到 Claude Code / Cursor 等 AI 编辑器。

### 安装（uvx）

```bash
uvx --from git+https://github.com/lousicong18/pdf-parsing pdf-parser-mcp
```

### 配置 Claude Code

```json
{
  "mcpServers": {
    "pdf-parser": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lousicong18/pdf-parsing", "pdf-parser-mcp"]
    }
  }
}
```

### 使用

配置完成后，在 Claude Code 中直接说"解析这个 PDF"即可调用。

## 知识库导出

`export_kb` 将 Markdown 按 token 分块，用于向量数据库入库：

- 默认 chunk = 500 tokens，overlap = 50 tokens
- 元数据：chunk_id / page_start / page_end / page_types / token_estimate
- 中文字符估算：`_CHARS_PER_TOKEN = 2.5`

# PDF 图文混排解析 Demo - 技术设计文档（code_plan.md）

> 本文档基于 `spec.md`（产品规格）与 `需求说明与Demo蓝图.md`（技术细节来源：§5/§7/§8/§10/§13/附录B），结合本项目后端 agent（`.claude/agents/backend.md`）与前端 agent（`.claude/agents/frontend.md`）的编码规范，产出模块/文件/函数级技术方案，供后续 `plan_backend.md` / `plan_frontend.md` 拆任务、供 supervisor 调度代码 agent 实现。
>
> 忠实于 spec 与需求文档，不新增产品功能。所有标注「跳过/不适用」的约定均依据 spec.md 决策 3 与需求文档 §14 决策 3（内存 dict 无 DB）。

---

## 1. 技术栈选型

### 1.1 后端

| 维度 | 选型 | 说明 |
|------|------|------|
| Web 框架 | FastAPI + Uvicorn | 入口 `src/server.py`，端口 **8082**（backend agent 约定） |
| 运行方式 | 同步 `def`（**禁止 `async def`**） | 路由与后台任务均同步，FastAPI 自动将同步 handler / BackgroundTask 投入线程池执行；适配 PyMuPDF/pdfplumber/httpx 的阻塞调用 |
| PDF 解析 | PyMuPDF (`fitz`) | 页面分类、文本 `get_text("markdown")`、图片裁剪、整页渲染 |
| 表格提取 | pdfplumber | `extract_tables()` 结构化表格（附录 B.2） |
| VLM | OpenAI 兼容接口（`httpx.Client` 同步） | `base_url` 可配，支持通义/智谱/DeepSeek 等；`vlm.py` 统一实现 |
| 存储 | 内存 dict（`task_id -> ParseResult`） | 进程重启即清空，**无任何 SQL/数据库** |
| 依赖管理 | uv（`pyproject.toml`） | `uv run python -m src.server` 启动 |
| 配置 | `.env` + `python-dotenv` | `VLM_BASE_URL` / `VLM_API_KEY` / `VLM_MODEL` / `MAX_FILE_MB=50` |
| 数据校验 | Pydantic v2 | 数据模型定义 |
| 文件上传 | `python-multipart` | FastAPI `UploadFile` 依赖 |

### 1.2 前端

| 维度 | 选型 | 说明 |
|------|------|------|
| 框架 | Vue 3 + TypeScript | 组合式 API |
| 构建 | Vite | dev server 5173，proxy `/api` -> 后端 8082 |
| UI | Element Plus | 管理后台风格 SPA |
| 状态管理 | Pinia | 任务状态 / 轮询 / 结果 |
| 路由 | vue-router | 单页主路由 |
| 样式 | SCSS（`style/variables.scss` + `common.scss`） | 遵循 frontend agent 样式规范，禁私有样式 |
| HTTP | axios | `services/` 封装 |
| Markdown 渲染 | markdown-it | 渲染文本块 / 表格块 Markdown |

---

## 2. 目录结构

### 2.1 后端目录树（遵循 backend agent 的 `src/` 根约定，端口 8082）

需求文档 §13.2 的 `backend/` 模块（parser/models/store/config）适配进 `src/` 分层结构：`parser/` 保留；`models.py` -> `src/models/`；`store.py` -> `src/store/`；`config.py` -> `src/utils/env.py`；`main.py` -> `src/server.py`；并按 backend agent 约定补 `controller/`（顶层 API）、`task_manager/`（调度+进度）。

```
src/
├── server.py                      # FastAPI app + 路由注册 + Uvicorn 启动（端口 8082）
├── controller/                    # 顶层 API 控制器（路由薄层）
│   ├── __init__.py
│   ├── parse_controller.py        # POST /api/v1/parse
│   ├── task_controller.py         # GET  /api/v1/tasks/{task_id}
│   ├── export_controller.py       # GET  /api/v1/tasks/{task_id}/export?format=
│   └── image_controller.py        # GET  /api/v1/tasks/{task_id}/images/{page}/{index}
├── parser/                        # 解析管线（分层路由）
│   ├── __init__.py
│   ├── classify.py                # classify_page() PyMuPDF 页面分类（附录 B.1 + 边界增强）
│   ├── extract_text.py            # extract_text() get_text("markdown")
│   ├── extract_table.py           # extract_tables() pdfplumber（附录 B.2）+ tables_to_markdown()
│   ├── mixed.py                   # process_mixed_page() + extract_and_describe_images()
│   ├── scan.py                    # process_scan_page() 整页渲染 + vlm_ocr
│   ├── pipeline.py                # dispatch_page() 按类型分派（附录 B.4 路由）
│   └── vlm.py                     # vlm_describe / vlm_ocr + _call_vlm（OpenAI 兼容，重试1次+退避+超时）
├── task_manager/                  # 任务调度 + 进度（共享）
│   ├── __init__.py
│   ├── task_service.py            # create_task / run_parse（后台编排）/ 状态拼装
│   └── progress_service.py        # 进度回写 API（供 parser 回调，禁止反向依赖）
├── models/                        # Pydantic 数据模型
│   ├── __init__.py
│   └── schemas.py                 # TaskStatus/PageType/BlockType/Block/PageResult/ParseResult/ErrorResponse
├── store/                         # 内存任务存储（无 DB）
│   ├── __init__.py
│   ├── task_store.py              # 内存 dict (task_id -> ParseResult) CRUD + Lock
│   └── image_cache.py             # 裁剪图 bytes 缓存 (task_id/page/index -> bytes) + Lock
├── utils/                         # 工具
│   ├── __init__.py
│   ├── env.py                     # 读 .env（VLM_BASE_URL/VLM_API_KEY/VLM_MODEL/MAX_FILE_MB/HOST/PORT）
│   ├── unique_id.py               # 生成 task_id（string，uuid4 hex）
│   ├── pdf_utils.py               # PDF 校验（类型/大小）/ 页数 / 临时文件管理
│   ├── column_detection.py        # 共享栏检测（bbox[0] 聚类判栏数），供 classify_features / extract_text / mixed 共用（避免 columns 写入职责不清）
│   ├── metrics.py                 # VLM 成本/效果埋点（VlmCallMetric 记录 + TaskMetrics 汇总；当前串行场景用显式传参，禁模块级 task 上下文）
│   └── vlm_models.py              # VLM 模型注册表（models.json）+ ModelConfig / get_model / list_models
├── test/                          # 测试
│   ├── __init__.py
│   ├── test_classify.py
│   └── test_pipeline.py
└── pyproject.toml                 # uv 依赖管理
```

**根目录文件**：`.env` / `.env.example` / `README.md`。

### 2.2 前端目录树（遵循 frontend agent 的 `frontend/src/` 结构）

```
frontend/
├── src/
│   ├── components/                # 公共组件
│   │   ├── Uploader.vue           # 拖拽/点击上传 PDF + 预校验（类型/50MB）
│   │   ├── StatusBar.vue          # 解析状态条（状态 + 进度百分比 + 已处理X/共Y页）
│   │   ├── PageCard.vue           # 单页结果卡片（第N页 · 类型：mixed）
│   │   ├── BlockView.vue          # 块渲染调度（按 type 分发到 Text/Image/TableBlock）
│   │   ├── TextBlock.vue          # 文本块 Markdown 渲染
│   │   ├── ImageBlock.vue         # 图片块：缩略图 + VLM 描述 + bbox 标注
│   │   ├── TableBlock.vue         # 表格块渲染 + 复制 Markdown
│   │   └── ExportBtn.vue          # 导出 Markdown / JSON
│   ├── views/                     # 页面组件
│   │   └── ParserView.vue         # 主解析页（上传 + 状态 + 分页结果列表 + 导出）
│   ├── router/
│   │   └── index.ts               # 路由配置（/ -> ParserView）
│   ├── stores/
│   │   └── parser.ts              # Pinia：task 状态 / 轮询 / 结果 / 导出
│   ├── services/                  # API 服务层（axios）
│   │   ├── request.ts             # axios 实例 + 拦截器（baseURL /api/v1）
│   │   └── parse.ts               # createParseTask / getTask / exportTask / imageUrl
│   ├── style/
│   │   ├── variables.scss         # SCSS 变量（颜色/阴影/尺寸/间距）
│   │   └── common.scss            # 公共样式类（page/card/upload-zone/...）
│   ├── types/
│   │   └── index.ts               # TS 类型（ParseResult/PageResult/Block 等）
│   ├── App.vue                    # 根组件
│   └── main.ts                    # 入口（挂载 Vue + Element Plus + Pinia + Router）
├── public/
├── index.html
├── vite.config.ts                 # proxy /api -> http://localhost:8082
├── tsconfig.json
└── package.json
```

---

## 3. 关键约定适配（重点：backend agent 约定的取舍）

backend agent 规范面向「MySQL 持久化 + mapper/@Transaction/conn 注入」的项目；本 Demo 依据 spec.md 决策 3 / 需求文档 §14 决策 3 为「内存 dict 无 DB」，故对 backend agent 约定做明确取舍。

### 3.1 跳过 / 不适用的 backend agent 约定（无 DB）

| 约定 | 处置 | 依据 |
|------|------|------|
| MySQL 持久化 / `yo_mysql/` 连接池 | **跳过**，不创建该模块 | 决策 3：内存 dict |
| `mapper/` 层（所有 SQL 在 mapper） | **跳过**，无 SQL | 决策 3 |
| `@Transaction()` 装饰器 | **跳过**，不使用 | 决策 3 |
| `conn` 自动注入 / 线程绑定 / `conn=None` 参数 | **跳过**，函数签名不出现 `conn` | 决策 3 |
| `db_utils.py` | **跳过** | 无 DB |
| id 字段 `NUMBER(19)` 主键、禁止自增 | **跳过**该 DB 约束；但保留「ID 用 string、用 `src/utils/unique_id.py` 生成」的思想（见 3.2） | 决策 3 |
| `业务模块 -> progress_service` 依赖方向 | **保留**（progress_service 仍存在，只是写内存而非 DB） | backend agent 依赖方向 |

> 明确：本 Demo **不创建** `yo_mysql/`、`mapper/` 目录，代码中**不出现**任何 SQL 字符串、`@Transaction`、`conn`、`get_conn`、`release_conn`。任务存储用 `src/store/task_store.py` 的内存 dict，进程重启即清空。

### 3.2 保留并严格执行的 backend agent 约定

| 约定 | 执行方式 |
|------|----------|
| **同步方法（禁止 `async def`）** | 所有方法用 `def`，包括路由 handler、`run_parse` 后台任务、VLM 调用、store 操作。FastAPI 自动将同步 handler 与同步 BackgroundTask 投入线程池执行 |
| **模块导入风格** | 项目根为根，统一 `import src.xxx` / `from src.xxx import yyy`；**禁止 `from . import`** |
| **uv 依赖管理** | `pyproject.toml` 管理依赖；启动 `uv run python -m src.server`；测试 `uv run pytest src/test/` |
| **错误处理风格** | 业务异常在 service 层捕获并转为 `ParseResult.errors` / HTTP `ErrorResponse`；外层不裸抛 |
| **函数拆分** | 每个功能合理拆分 `def`，避免单函数过长；模块内文件合理组织 |
| **ID 用 string** | `task_id` 为 string，由 `src/utils/unique_id.py`（uuid4 hex）生成 |
| **`src/server.py` 入口 + 端口 8082** | 入口文件 `src/server.py`，Uvicorn 监听 8082 |
| **LLM Prompt 规范** | prompt 模板含 JSON 示例且用 `.format()`/f-string 时转义花括号 `{{}}` |
| **依赖方向** | `parser -> task_manager.progress_service`（允许回写进度）；`progress_service -> parser`（禁止） |

### 3.3 导入与函数签名示例（落实保留约定）

```python
# ✅ 正确：同步 def + import src.xxx + 无 conn
# src/task_manager/task_service.py
import src.store.task_store as task_store
from src.parser import classify, pipeline
from src.utils import unique_id, pdf_utils

def create_task(file, vlm_model=None):
    ...

def run_parse(task_id: str, pdf_path: str):
    ...

# ❌ 错误：禁止 async def / 禁止 from . import / 禁止 conn
# async def run_parse(task_id, conn=None): ...
# from . import task_store
```

---

## 4. API 契约

Base：FastAPI，前缀 `/api/v1`，JSON 响应（导出/图片接口除外）。VLM 为 OpenAI 兼容接口。所有 handler 为同步 `def`。

### 4.1 POST /api/v1/parse - 创建解析任务

| 项 | 内容 |
|----|------|
| Content-Type | `multipart/form-data` |
| 表单字段 | `file`（PDF 文件，必填）；`vlm_model`（string，可选，不传用 `.env` 默认） |
| 200 响应 | `{ "task_id": "uuid", "filename": "report.pdf", "status": "pending", "total_pages": 12, "created_at": "2026-08-13T15:20:00+08:00" }` |
| 400 | 非 PDF（`INVALID_FILE_TYPE`）/ 超过 50MB（`FILE_TOO_LARGE`） |
| 422 | 表单校验失败 |
| 500 | 内部错误 |

行为：校验 -> 保存 PDF 到临时路径 -> `fitz.open` 取 `total_pages` -> 创建 `ParseResult(status=pending)` 入内存 store -> `BackgroundTasks.add_task(run_parse, task_id, pdf_path)` -> 立即返回 `task_id`。

### 4.2 GET /api/v1/tasks/{task_id} - 查询任务状态与结果

| 项 | 内容 |
|----|------|
| 200 响应 | 完整 `ParseResult`（见 §5）：`task_id` / `status` / `progress` / `total_pages` / `pages[]` / `cost_usd` / `errors[]` / `created_at` / `finished_at?` |
| 404 | 任务不存在（`TASK_NOT_FOUND`） |

`pages[].blocks[]` 中 `image` 块含 `image_url`，形如 `/api/v1/tasks/{task_id}/images/{page}/{index}`。

### 4.3 GET /api/v1/tasks/{task_id}/export?format=markdown|json - 导出

| 项 | 内容 |
|----|------|
| query | `format` = `markdown` \| `json` |
| 200 | 文件下载，`Content-Type: text/markdown` 或 `application/json`，`Content-Disposition: attachment; filename="<task_id>.md"` |
| 400 | `format` 非法（`INVALID_FORMAT`） |
| 404 | 任务不存在（`TASK_NOT_FOUND`） |
| 409 | 任务未完成，不可导出（`TASK_NOT_READY`，status 为 pending/parsing） |

- **`format=json`**：导出完整 `ParseResult`（含每个 Block 的结构化真相源 `text` / `table`（行列 + 合并单元格）/ `image` + `bbox` + `page_type`）-- **保全精度**（S2/S4，决策 4）。
- **`format=markdown`**：导出派生视图（各 Block `content` 按页拼接，§8.2 示例）-- 人读 + LLM 友好，但丢失合并单元格 / 坐标 / 跨页结构。

### 4.4 GET /api/v1/tasks/{task_id}/images/{page}/{index} - 裁剪图（F10）

| 项 | 内容 |
|----|------|
| 路径参数 | `task_id` / `page`(int) / `index`(int) |
| 200 | `image/*`（从 `image_cache` 取裁剪图 bytes 返回） |
| 404 | 任务或图片不存在（`IMAGE_NOT_FOUND`） |

### 4.5 任务状态机

```
pending ──(run_parse 启动)──> parsing ──┬──> completed   (全部页成功，无 errors)
                                        ├──> partial     (存在页/块失败，errors 非空，X2/X3)
                                        └──> failed      (致命错误，X1：文件损坏/无法打开)
```

- `parsing` 期间 `progress` 逐页递增（每完成一页 +1），`pages[]` 逐页追加。
- 终态固化后 `finished_at` 写入，前端停止轮询。

### 4.6 错误码与提示（统一信封）

```json
{ "detail": "可读错误信息", "code": "ERROR_CODE" }
```

| code | HTTP | 场景 |
|------|------|------|
| `INVALID_FILE_TYPE` | 400 | 非 PDF（U1） |
| `FILE_TOO_LARGE` | 400 | 超过 50MB（U2） |
| `TASK_NOT_FOUND` | 404 | task_id 不存在 |
| `TASK_NOT_READY` | 409 | 导出时任务未完成 |
| `INVALID_FORMAT` | 400 | 导出 format 非法 |
| `IMAGE_NOT_FOUND` | 404 | 裁剪图不存在 |
| `PARSE_FAILED` | 200(体内) | X1 文件损坏，记入 `errors` + status=failed |
| `VLM_FAILED` | 200(体内) | X2/X3 VLM 失败，记入 `errors` + status=partial |

> 任务级错误（X1/X2/X3）不表现为 HTTP 错误码，而是 HTTP 200 返回 `ParseResult`，通过 `status` 与 `errors[]` 表达（符合 EARS X2/X3「继续处理、整体置 partial」）。

### 4.7 GET /api/v1/models - 列出可用 VLM 模型（#7 扩展/§11.10）

| 项 | 内容 |
|----|------|
| 200 | `{ "models": ["glm-4v", "qwen-vl-max", "deepseek-vl"], "default": "glm-4v" }` |
| 说明 | 从 `models.json` 注册表读取（无注册表则返回 `.env` 单模型）；供前端模型下拉 + eval 对比选择 |

---

## 5. 数据模型

### 5.1 后端 Pydantic 定义（`src/models/schemas.py`）

```python
from typing import Literal, Optional
from pydantic import BaseModel

TaskStatus = Literal["pending", "parsing", "completed", "partial", "failed"]
PageType = Literal["text", "table", "mixed", "scan"]
BlockType = Literal["text", "image", "table"]

# 精度优先架构（需求 §5 / 决策 4）：
#   抽取层（唯一真相源）= 结构化字段 text / table(行列+合并单元格) / image(描述+url) + bbox + page_type
#   呈现层（派生视图）   = content：由结构化字段派生的 markdown（text->文本 / table->markdown 表格 / image->描述）
#   JSON 导出 = 完整 Block（含结构化真相源 + bbox + page_type）= 精度；Markdown 导出 = content（派生视图）
class MergedCell(BaseModel):
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1

class TableData(BaseModel):
    rows: list[list[str]]            # 行列结构（真相源，不扁平化）
    n_rows: int
    n_cols: int
    merged: list[MergedCell] = []    # 合并单元格信息（S2）
    cross_page: bool = False         # 跨页续表标记（S5）

class ImageData(BaseModel):
    description: str                 # VLM 描述
    image_url: str
    mime: str = "image/png"
    width: Optional[int] = None
    height: Optional[int] = None

class PageFeatures(BaseModel):
    line_count: int
    text_blocks_count: int
    images_count: int
    drawings_path_count: int
    area_ratio: float           # 线密集区面积/页面面积
    overlap_rate: float         # 文本块 bbox 重叠率
    char_density: float         # 字符数/文本面积
    font_flags: list[str] = []  # 隐形层特征字体
    orthogonality: float        # 线条正交性 0-1
    columns: int = 1            # 栏数（§11.5）

class VlmCallMetric(BaseModel):
    kind: str                   # image / scan
    model: str
    latency_ms: int
    tokens: int = 0
    cost_usd: float = 0.0
    retry: int = 0
    success: bool

class TaskMetrics(BaseModel):
    vlm_calls: list[VlmCallMetric] = []
    total_cost: float = 0.0
    total_latency_ms: int = 0
    by_kind: dict[str, int] = {}

class Block(BaseModel):
    type: BlockType
    bbox: list[float]                # [x0, y0, x1, y1] 始终保留（S4）
    page_type: PageType              # 始终保留（S4）
    order: int                       # 同页阅读顺序
    # 抽取层：结构化真相源（按 type 取用，JSON 导出保全精度）
    text: Optional[str] = None       # type=text：原生抽取文本
    table: Optional[TableData] = None# type=table：行列 + 合并单元格
    image: Optional[ImageData] = None# type=image：描述 + image_url
    # 呈现层：markdown 派生视图（默认展示 / markdown 导出）
    content: str                     # 由结构化字段派生
    image_url: Optional[str] = None  # 便利字段 = image.image_url

class PageResult(BaseModel):
    page: int
    type: PageType
    blocks: list[Block] = []
    features: Optional[PageFeatures] = None   # classify 特征向量（探究/eval，§11.2）

class TaskError(BaseModel):
    page: Optional[int] = None
    message: str

class ParseResult(BaseModel):
    task_id: str
    filename: str
    status: TaskStatus
    total_pages: int
    progress: int = 0
    pages: list[PageResult] = []
    cost_usd: float = 0.0
    errors: list[TaskError] = []
    metrics: Optional[TaskMetrics] = None      # VLM 成本/耗时埋点（§11.7）
    created_at: str
    finished_at: Optional[str] = None

class CreateTaskResponse(BaseModel):
    task_id: str
    filename: str
    status: TaskStatus
    total_pages: int
    created_at: str

class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None
```

### 5.2 前端 TS interface（`frontend/src/types/index.ts`）

```typescript
export type TaskStatus = 'pending' | 'parsing' | 'completed' | 'partial' | 'failed'
export type PageType = 'text' | 'table' | 'mixed' | 'scan'
export type BlockType = 'text' | 'image' | 'table'

export interface MergedCell {
  row: number
  col: number
  rowspan: number
  colspan: number
}

export interface TableData {
  rows: string[][]
  n_rows: number
  n_cols: number
  merged: MergedCell[]
  cross_page: boolean
}

export interface ImageData {
  description: string
  image_url: string
  mime: string
  width?: number
  height?: number
}

export interface Block {
  type: BlockType
  bbox: [number, number, number, number]   // 始终保留（S4）
  page_type: PageType                      // 始终保留（S4）
  order: number
  // 抽取层：结构化真相源
  text?: string
  table?: TableData
  image?: ImageData
  // 呈现层：markdown 派生视图
  content: string
  image_url?: string
}

export interface PageResult {
  page: number
  type: PageType
  blocks: Block[]
}

export interface TaskError {
  page?: number
  message: string
}

export interface ParseResult {
  task_id: string
  filename: string
  status: TaskStatus
  total_pages: number
  progress: number
  pages: PageResult[]
  cost_usd?: number
  errors: TaskError[]
  created_at: string
  finished_at?: string
}

export interface CreateTaskResponse {
  task_id: string
  filename: string
  status: TaskStatus
  total_pages: number
  created_at: string
}
```

---

## 6. 解析管线设计（§5 + 附录 B 分层路由）

### 6.1 总体流程

```
run_parse(task_id, pdf_path)
  ├─ mark_parsing(task_id)
  ├─ doc = fitz.open(pdf_path)        # 懒加载，不预载全部位图
  ├─ prev_type = None
  ├─ for page_num, page in enumerate(doc):
  │     page_type = classify.classify_page(page, prev_type)   # B.1 + 边界增强
  │     blocks, features = pipeline.dispatch_page(page, page_type, task_id, page_num, doc, prev_type)
  │     progress_service.update_page_done(task_id, page_num+1, page_type, blocks, features)
  │     prev_type = page_type
  ├─ status = completed / partial / failed（按 errors 拼装）
  └─ progress_service.finish(task_id, status)
```

### 6.2 各模块职责

#### `src/parser/classify.py` - `classify_page(page, prev_type=None) -> PageType` + `classify_features(page) -> PageFeatures`

附录 B.1 启发式 + §10 边界增强（同步，入参 `fitz.Page`）。**探究层（§11.2/#1/#2/#3）**：`classify_features` 提取特征向量（line_count/area_ratio/overlap_rate/char_density/font_flags/orthogonality/columns），`classify_page` 按 **`.env` 可配置阈值 `CLS_*`** 判定（不再硬编码）；`dispatch_page` 调 `classify_features` 取特征向量，经 columns 覆盖后作为 `PageResult.features` 返回：

- `text_blocks = page.get_text("blocks")`；`images = page.get_images()`；`drawings = page.get_drawings()`
- **栏检测**：`columns = utils.column_detection(text_blocks)`（共享函数，按 `bbox[0]` 聚类判栏数，供 classify_features 直接写入 `PageFeatures.columns`，避免 extract_text 无法回写已返回对象的歧义）。
- **scan**：`len(text_blocks)==0 and len(images)>0`；另检测隐形文本层（§10）：文本块坐标异常密集/重叠且图片为主 -> `scan`
- **table**：`line_count = len([d for d in drawings if d['type'] in ('line','rect')])`；`line_count > 20 and len(text_blocks) >= 4`，**加面积过滤**（§10 矢量 Logo）：要求线密集区域占页面面积足够大，过滤小 Logo
- **跨页表格上下文**（§10）：若 `prev_type == "table"`，当前页偏向按 `table` 处理
- **mixed**：`len(images)>0 and len(text_blocks)>0`；另矢量图情形（§10）：`get_images()` 空但 `get_drawings()` 路径极多 -> `mixed`
- **text**：`len(text_blocks)>0 and len(images)==0 and line_count<10`
- 兜底：`mixed`

#### `src/parser/extract_text.py` - `extract_text(page, page_type) -> list[Block]`（精度优先）

- **抽取层**：`page.get_text("dict")` 遍历 `blocks`，对每个文本块（`block["type"]==0`）拼接 spans 得文本，取 `block["bbox"]`；组装 `Block{type:"text", bbox, page_type, order, text=<文本>, content=<文本>}`（content 为派生视图 = text）。
- 按 y 坐标（`bbox[1]`）排序设置 `order`（阅读顺序）；多段文本产出多个 text Block，**每个均带 bbox + page_type**（S4）。
- **不使用 `get_text("markdown")` 整页视图**：markdown 为派生视图，须从结构化真相源（dict 文本块）派生，避免双表示不一致（决策 4 / §5 架构原则）。
- 公式标注（§10/§11.6/#8）：由 `formula.py` 处理（`FORMULA_MODE` 可配），`probe_latex` 验证 `get_text("latex")` 可用性并记 eval。
- **多栏阅读顺序（§11.5/#6）**：排序前先调用共享 `utils.column_detection(blocks)` 栏检测，单栏按 y 排序，多栏栏内按 y + 栏间按 x；**栏数不由 extract_text 回写 `PageFeatures`**（`features` 已在 classify 阶段由共享函数算准并作为单数据源返回，避免"已返回对象无法回写"的歧义）。

#### `src/parser/extract_table.py` - pdfplumber 表格（精度优先：保留合并单元格 S2）

- `extract_tables(page, page_type, pdf_path, page_num, prev_type=None) -> list[Block]`：
  - **抽取层**：`pdfplumber.open(pdf_path)` -> `pg = pdf.pages[page_num]`；`found = pg.find_tables()`（返回 Table 对象，含 `.cells` 几何信息）。
  - 对每个 Table：`rows = table.extract()` 得行列文本（`list[list[str]]`）；`n_rows`/`n_cols` 由行列数定；**合并单元格**：据 `table.cells`（cell bbox）与行列网格比对，cell 跨多行/多列 -> 记 `MergedCell{row,col,rowspan,colspan}`（S2）。
  - 组装 `TableData{rows, n_rows, n_cols, merged, cross_page=(prev_type=="table")}`；`content = tables_to_markdown(TableData)`（派生视图：markdown 表格，合并信息在 md 中退化为普通表格）；跨页时 content 前置 "> （跨页续表）"。
  - `bbox` 取 `table.bbox`；返回 `Block{type:"table", bbox, page_type, order, table=TableData, content}`，每表一个 Block（S4：带 bbox + page_type）。
- `tables_to_markdown(table: TableData) -> str`：由 `TableData.rows` 渲染 Markdown 表格（含表头分隔行）；多表用分隔符拼接。
- **跨页续表（S5）**：`prev_type=="table"` 时当前表 `cross_page=True` 并在 `content` 标注"（跨页续表）"，避免行断裂丢结构（best-effort 标注，不做跨页 in-place 行合并以避免污染已回写的上页结果）。
- **可插拔后端（§11.3/#4）**：`extract_tables` 委托 `get_table_extractor()`（`.env` `TABLE_EXTRACTOR`），默认 pdfplumber，可换 camelot/marker/mineru。
- **跨页特征（§11.4/#5）**：`prev_type=="table"` 时额外记录表头相似度与列数对齐到 eval 日志，供合并策略探究。

#### `src/parser/mixed.py` - 图文混排

- `extract_and_describe_images(page, task_id, page_num, doc) -> list[Block]`
  - 遍历 `page.get_images(full=True)`，取 `xref`，`image_bytes = doc.extract_image(xref)["image"]`
  - `bbox` 通过 `page.get_image_bbox(img)` / `page.get_image_rects(xref)` 获取（附录 B.3 用 `img[1]` 系占位简化，实现取真实矩形）
  - `desc = vlm.vlm_describe(image_bytes)`；将 `image_bytes` 写入 `image_cache.put(task_id, page_num, index, bytes)`
  - 组装 `Block{type:image, bbox, page_type:"mixed", order, image=ImageData{description:desc, image_url:f"/api/v1/tasks/{task_id}/images/{page_num}/{index}"}, content:desc, image_url=f"/api/v1/tasks/{task_id}/images/{page_num}/{index}"}`（S4：带 bbox + page_type；image 为结构化真相源，content 为派生视图）
  - **X2 兜底**：VLM 失败 -> `Block{content:"图片未识别（VLM 调用失败）", image_url:...}` + `progress_service.add_error(task_id, page_num, "VLM timeout")`，继续处理其余图片
- `process_mixed_page(page, task_id, page_num, doc) -> list[Block]`
  - `text_blocks` = `extract_text(page, "mixed")`（每段文本带 bbox + page_type，S4）
  - `image_blocks` = `extract_and_describe_images(...)`（每个图片带 bbox + page_type）
  - 合并 text_blocks + image_blocks，调用共享 `utils.column_detection` 栏检测后按多栏规则排序设置 `order`（阅读顺序拼接，附录"更精细路由"）

> 说明：§13.1 称 `vlm.py` 实现 `extract_and_describe_images`。本设计为保持 `vlm.py` 为「无 fitz 依赖的纯 VLM 客户端」的清晰分层，将 `extract_and_describe_images`（页面图片抽取+描述编排，强依赖 fitz）置于 `mixed.py`，由 `process_mixed_page` 调用；`vlm.py` 提供底层 `vlm_describe` / `vlm_ocr`。此为对 §13.1「三函数归 vlm.py」的显式分层精炼，三个占位行为（describe / extract_and_describe / ocr）均已实现，位置见本节。

#### `src/parser/scan.py` - 扫描件

- `process_scan_page(page, task_id, page_num) -> list[Block]`
  - `pix = page.get_pixmap(dpi=200)`；`image_bytes = pix.tobytes("png")`（附录 B.4）
  - `text = vlm.vlm_ocr(image_bytes)`
  - 返回 `[Block{type:text, bbox:[0,0,page.rect.width,page.rect.height], page_type:"scan", order:0, text:text, content:text}]`（S4：带 bbox + page_type；text 为结构化真相源，content 为派生视图）
  - **X2 兜底**：VLM 失败 -> `content:"扫描件未识别（VLM 调用失败）"` + 记 error，status 置 partial
  - scan 页不产生 `image_url`（结果为文本，非图片块）

#### `src/parser/vlm.py` - OpenAI 兼容 VLM 客户端（同步 httpx）

- `_call_vlm(image_bytes, prompt, model_name=None) -> str`（内部）：按 `model_name` 从 `vlm_models` 注册表（§11.10）解析 `ModelConfig`（默认 `VLM_DEFAULT_MODEL`），用其 base_url/key/model 调用；`VlmCallMetric.model` 记实际模型名
  - base64 编码图片，构造 OpenAI `chat/completions` 载荷：`messages=[{role:"user", content:[{type:"text", text:prompt}, {type:"image_url", image_url:{url:"data:image/png;base64,..."}}]}]`
  - `httpx.Client(timeout=60)` POST `{cfg.base_url}/chat/completions`，Header `Authorization: Bearer {cfg.api_key}`，body `model={cfg.model}`
  - **重试 1 次 + 退避**（§10/X2）：遇 `httpx.TimeoutException` / 429 / 5xx -> `sleep(2)` 重试一次；仍失败抛异常
  - 解析 `response.choices[0].message.content`；**X3**：内容空/格式错 -> 抛异常（由 mixed/scan 捕获兜底）
  - 累计 `cost_usd`（从 `response.usage` 估算，无则 0）
- `vlm_describe(image_bytes, model_name=None) -> str`：prompt「请描述这张图片的内容…」
- `vlm_ocr(image_bytes, model_name=None) -> str`：prompt「请对这张扫描件图片进行 OCR，输出可读文字…」
- 配置来自 `src/utils/vlm_models.py` 注册表（`models.json`，§11.10）+ `src/utils/env.py`（默认/回退 `VLM_BASE_URL`/`VLM_API_KEY`/`VLM_MODEL`）

#### `src/parser/pipeline.py` - 分派路由（附录 B.4）

- `dispatch_page(page, page_type, task_id, page_num, doc, prev_type=None) -> tuple[list[Block], PageFeatures]`
  - 先调 `classify.classify_features(page)` 取特征向量 `features`（含 `columns=1` 初始值）；按 `page_type` 分派：
    - `text`  -> `extract_text(page, "text")`（已为 list[Block]，每个带 bbox + page_type）
    - `table` -> `extract_table.extract_tables(page, "table", doc.name, page_num, prev_type)`（每表一个 Block，带 TableData + bbox + page_type；跨页标注见 extract_table）
    - `mixed` -> `mixed.process_mixed_page(...)`
    - `scan`  -> `scan.process_scan_page(...)`
  - **columns 回填**：text / mixed 分支完成后，用 `utils.column_detection` 共享栏检测函数对返回 blocks 重新检测栏数，覆盖 `features.columns`（保持 `features` 为单数据源，避免 extract_text 无法回写已返回对象的歧义）。
  - 最终返回 `(blocks, features)`；所有 Block 均**带 bbox + page_type**（S4）；`prev_type` 用于跨页表格标注（S5）

#### `src/store/task_store.py` - 内存任务存储

- 模块级 `_store: dict[str, ParseResult] = {}` + `threading.Lock`（后台线程写、请求线程读，需线程安全）
- `get(task_id)` / `create(task_id, result)` / `update_status` / `update_progress` / `append_page` / `append_error` / `add_cost` / `set_finished`
- **进程重启即清空**（模块级 dict，不落盘）

#### `src/store/image_cache.py` - 裁剪图 bytes 缓存

- `_cache: dict[str, dict[int, dict[int, bytes]]]`（task_id -> page -> index -> bytes）+ `Lock`
- `put(task_id, page, index, bytes)` / `get(task_id, page, index) -> bytes | None`
- 供 `image_controller` 返回裁剪图（F10 / O2）

#### `src/task_manager/progress_service.py` - 进度回写 API

- `mark_parsing(task_id)` / `update_page_done(task_id, page, page_type, blocks, features: Optional[PageFeatures]=None)` / `add_error(task_id, page, msg)` / `add_cost(task_id, cost)` / `set_metrics(task_id, metrics: TaskMetrics)` / `finish(task_id, status)`
- 委托 `task_store` 写内存；`parser` -> `progress_service` 允许，反向禁止（backend agent 依赖方向）

#### `src/task_manager/task_service.py` - 编排

- `create_task(file, vlm_model=None) -> (CreateTaskResponse, pdf_path)`：校验（`pdf_utils`）-> 保存临时文件 -> `fitz.open` 取页数 -> `unique_id` 生成 task_id -> `task_store.create(status=pending)` -> 返回
- `run_parse(task_id, pdf_path)`（同步，BackgroundTask 线程池执行）：见 §6.1 流程；X1（`fitz.open` 失败）-> `finish(failed)` + `add_error`；按 `errors` 拼装 `completed`/`partial`/`failed`；解析后可删除临时 PDF（`image_cache` 保留供 F10）

---

## 7. 异步任务与进度

### 7.1 后台执行

- `POST /api/v1/parse` 的 controller 调 `task_service.create_task(...)` 得 `(response, pdf_path)`，再 `background_tasks.add_task(task_service.run_parse, response.task_id, pdf_path)`，立即返回 `task_id`（E1）。
- `run_parse` 为同步 `def`，FastAPI/Starlette 将其投入线程池执行（不阻塞事件循环；适配 PyMuPDF/pdfplumber/httpx 阻塞调用）。
- 每完成一页调 `progress_service.update_page_done` 更新内存 store 的 `status=parsing`、`progress`、`pages[]`（E2）。
- 全部页处理完毕调 `progress_service.finish`，按 errors 拼装终态 `completed`/`partial`/`failed`，写 `finished_at`（E3）。

### 7.2 前端轮询

- Pinia store `upload(file)` 调 `createParseTask` 拿 `task_id`，随后 `startPolling(task_id)`：每 ~1.5s 调 `getTask(task_id)` 刷新 `ParseResult`。
- 当 `status` ∈ {`completed`,`partial`,`failed`} 时 `stopPolling`。
- 状态机：`pending` -> `parsing` -> `completed`/`partial`/`failed`；`StatusBar` 实时显示进度百分比与「已处理 X / 共 Y 页」（US5）。
- 解析中禁用重复上传（`Uploader` 置禁用，§6.2 交互边界）。

---

## 8. 配置

### 8.1 `.env` 变量

| 变量 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `VLM_BASE_URL` | 是 | - | OpenAI 兼容接口端点（如智谱 `https://open.bigmodel.cn/api/paas/v4`、通义、DeepSeek、OpenAI） |
| `VLM_API_KEY` | 是 | - | VLM API Key |
| `VLM_MODEL` | 是 | - | 多模态模型名（如 `glm-4v` / `qwen-vl-max` / `deepseek-vl`） |
| `VLM_MODELS_FILE` | 否 | models.json | VLM 模型注册表路径（多模型对比，#7 扩展/§11.10） |
| `VLM_DEFAULT_MODEL` | 否 | - | 默认 VLM 模型名（未传 vlm_model 时用） |
| `MAX_FILE_MB` | 否 | 50 | 上传大小上限（U2） |
| `HOST` | 否 | 0.0.0.0 | 服务监听地址 |
| `PORT` | 否 | 8082 | 服务端口（backend agent 约定） |
| `CLS_LINE_COUNT_TABLE` | 否 | 20 | table 判定线数阈值（#1） |
| `CLS_TEXT_BLOCKS_MIN` | 否 | 4 | table 判定文本块数下限（#1） |
| `CLS_LINE_COUNT_TEXT` | 否 | 10 | text 判定线数上限（#1） |
| `CLS_AREA_RATIO_MIN` | 否 | 0.15 | 表格线密集区面积占比下限（Logo 过滤，#3） |
| `CLS_DRAWINGS_PATH_MIXED` | 否 | 200 | 矢量图判定 drawings 路径数阈值（#3） |
| `TABLE_EXTRACTOR` | 否 | pdfplumber | 表格提取后端 pdfplumber/camelot/marker/mineru（#4） |
| `FORMULA_MODE` | 否 | annotate | 公式处理 annotate/latex/model（#8） |
| `VLM_OCR_DPI` | 否 | 200 | scan 渲染 DPI（#7） |
| `VLM_DESC_DPI` | 否 | 200 | mixed 图片裁剪 DPI（#7） |
| `VLM_RESPONSE_CACHE` | 否 | off | VLM 响应缓存 on/off（#7） |
| `EVAL_SAMPLES_DIR` | 否 | samples | 评测样本集目录（#10） |

### 8.2 `.env.example`

```ini
# VLM (OpenAI 兼容接口，可切换通义/智谱/DeepSeek/OpenAI)
VLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
VLM_API_KEY=your-api-key-here
VLM_MODEL=glm-4v
# VLM 模型注册表（多模型对比，#7 扩展/§11.10）
VLM_MODELS_FILE=models.json
VLM_DEFAULT_MODEL=glm-4v

# 上传限制
MAX_FILE_MB=50

# 服务
HOST=0.0.0.0
PORT=8082

# 分类阈值（探究/调优，#1/#3）
CLS_LINE_COUNT_TABLE=20
CLS_TEXT_BLOCKS_MIN=4
CLS_LINE_COUNT_TEXT=10
CLS_AREA_RATIO_MIN=0.15
CLS_DRAWINGS_PATH_MIXED=200

# 探究层
TABLE_EXTRACTOR=pdfplumber
FORMULA_MODE=annotate
VLM_OCR_DPI=200
VLM_DESC_DPI=200
VLM_RESPONSE_CACHE=off
EVAL_SAMPLES_DIR=samples
```

`src/utils/env.py` 用 `python-dotenv` 读取并暴露为模块级常量，供 `vlm.py` / `pdf_utils.py` / `server.py` 使用。

---

## 9. 边界场景技术处理（§10）

| 场景 | 检测/处理策略 | 落点 |
|------|--------------|------|
| 扫描件含隐形文本层 | `get_text("blocks")` 读到字但坐标异常密集/重叠，且图片为主 -> 判 `scan`（整页渲染走 VLM OCR） | `classify.py` |
| 矢量 Logo 误判为表格 | 表格判定加**面积过滤**：`line_count>20 and text_blocks>=4` 之外，要求线密集区域占页面面积达阈值，过滤小 Logo | `classify.py` |
| 图片是矢量图 | `get_images()` 空但 `get_drawings()` 路径极多（复杂度高）-> 按 `mixed` 处理 | `classify.py` |
| 表格跨页（S5） | 上下文记忆：`classify_page` 接收 `prev_type`，上一页为 `table` 则当前页偏向 `table`；`extract_table` 据 `prev_type`，若 `prev_type=="table"` 则当前表 `cross_page=True` 并在 `content` 标注"（跨页续表）"，避免行断裂丢结构 | `classify.py` + `extract_table.py` + `run_parse` 传 `prev_type` |
| 多栏排版（#6） | 栏检测：文本块 `bbox[0]` 聚类判栏数；单栏 y 排序，多栏栏内 y + 栏间 x；栏数写入 `PageFeatures.columns`，多栏页标注 | `extract_text.py` + `mixed.py` |
| 公式识别 | `extract_text` 轻量标注疑似 LaTeX 碎片为公式块（Demo 仅标注，不深究） | `extract_text.py` |
| VLM 超时/限流 | `_call_vlm` 重试 1 次 + 退避（`sleep(2)`）；仍失败按 X2 标记「未识别」，status=partial | `vlm.py` + `mixed.py`/`scan.py` |
| VLM 返回异常（空/格式错） | X3：抛异常 -> 捕获后记 error 跳过该块，不影响其他页 | `vlm.py` + `mixed.py`/`scan.py` |
| 超大 PDF | `fitz.open` 懒加载；逐页 `get_pixmap` 按需渲染，**不一次性载入全部位图**；前端进度条 | `run_parse` + `scan.py`/`mixed.py` |
| 并发上传 | Demo 不要求并发，单进程串行处理；内存 dict 索引，进程重启即清空 | `task_store.py` |
| 文件损坏（X1） | `fitz.open` 失败 -> `finish(failed)` + 可读 error | `run_parse` |

---

## 10. 前后端联调

### 10.1 端口规划与代理

- 后端：`http://localhost:8082`（`uv run python -m src.server`）
- 前端 dev：`http://localhost:5173`（Vite）
- Vite proxy（`frontend/vite.config.ts`）：
  ```ts
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://localhost:8082', changeOrigin: true } }
  }
  ```
- 前端 axios `baseURL: '/api/v1'`，经 proxy 转发至后端，避免跨域。

### 10.2 CORS

- 后端 `server.py` 加 `CORSMiddleware`，`allow_origins=["http://localhost:5173"]`，`allow_methods=["*"]`，`allow_headers=["*"]`（dev 兜底；生产可同源收紧）。

### 10.3 图片块 `image_url` 回传裁剪图

- `mixed.extract_and_describe_images` 抽取每张图片 bytes 时，同步 `image_cache.put(task_id, page_num, index, bytes)` 缓存裁剪图原图。
- `image` 块 `image_url = f"/api/v1/tasks/{task_id}/images/{page_num}/{index}"`。
- 前端 `ImageBlock.vue` 直接 `<img :src="block.image_url">`（经 proxy 命中 `image_controller`）。
- `image_controller` 从 `image_cache.get` 取 bytes，`Response(content=bytes, media_type="image/png")` 返回；不存在 -> 404 `IMAGE_NOT_FOUND`。
- scan 页不缓存整页渲染图（结果为文本），无 `image_url`。

### 10.4 联调要点

- `POST /api/v1/parse` 返回 `task_id` 后前端即开始轮询 `GET /api/v1/tasks/{task_id}`。
- 导出按钮在 `status` 为终态时启用，调 `GET /export?format=` 触发文件下载（`responseType: 'blob'`）。
- 表格块「复制 Markdown」直接复制 `block.content`。

---

## 11. 探究/评测层（Investigation & Evaluation）

支撑需求方 10 项探究（分类阈值/隐形文本层/矢量图区分/表格工具对比/跨页合并/多栏阅读顺序/VLM 成本效果/公式/IR/端到端评测）。本层使 Demo 从「跑通流程的管线」升级为「可实验的探针平台」。IR 已由 §5 精度优先 Block 模型满足（#9），其余 9 项由本层支撑。

### 11.1 可配置化（#1/#7）
分类阈值与 VLM 参数全部从 `.env` 读取（见 §8.1），告别硬编码，支持回归调优。

### 11.2 classify 特征埋点（#2/#3）
- `src/parser/classify.py` 新增 `classify_features(page) -> PageFeatures`：提取可观测特征向量；`classify_page(page, prev_type)` 改为先取 features 再按**可配置阈值**判定，返回 `PageType`；另提供 `classify_features(page) -> PageFeatures`，由 pipeline 写入 `PageResult.features` 供 eval 分析。
- `PageFeatures` 字段：`line_count` / `text_blocks_count` / `images_count` / `drawings_path_count` / `area_ratio`(线密集区/页面) / `overlap_rate`(文本块 bbox 重叠率) / `char_density`(字符/面积) / `font_flags`(隐形层特征字体) / `orthogonality`(线条正交性 0-1) / `columns`(栏数)。
- 隐形文本层（#2）：`overlap_rate` 高 + `char_density` 异常 + `font_flags` -> 量化判 `scan`。
- 矢量图/表格/Logo（#3）：`line_count` + `area_ratio` + `orthogonality`（表格线正交、Logo/插图路径杂乱）+ `drawings_path_count` 联合判定。

### 11.3 可插拔表格提取器（#4）
- `src/parser/table_extractor.py`：抽象 `TableExtractor.extract(page, pdf_path, page_num) -> list[TableData]`。
- 实现：`PdfplumberExtractor`（默认，find_tables + 合并单元格）、`CamelotExtractor`（可选，camelot-py）、`MarkerExtractor` / `MinerUExtractor`（可选 stub，外部进程）。
- `.env` `TABLE_EXTRACTOR` 选择；工厂 `get_table_extractor()` 返回。`extract_table.py` 改为委托当前 extractor。
- eval 可遍历多 backend 在表格样本集对比准确率/耗时（#4）。

### 11.4 跨页表格特征（#5）
- `extract_table` 在 `prev_type=="table"` 时，除标 `cross_page=True` 外，计算并记录：**表头相似度**（首行与上页末表首行 token 重合率）、**列数对齐**（n_cols 是否一致），写入 eval 日志。
- Demo 不做 in-place 行合并（避免污染已回写上页），但暴露合并可行性信号供策略探究。

### 11.5 多栏阅读顺序（#6）
- `extract_text` / `mixed` 排序前先**栏检测**：对文本块 `bbox[0]`(x0) 聚类（简单阈值/DBSCAN）判栏数。
  - 单栏：按 y 排序（现状）。
  - 多栏：栏内按 y 排序，栏间按 x 排序，左->右。
- 栏数写入 `PageFeatures.columns`；多栏页标注（暴露边界，不深解复杂版式）。

### 11.6 公式探究（#8）
- `src/parser/formula.py`：`probe_latex(page)` 验证 `get_text("latex")` 可用性与返回（记 eval）；`FormulaRecognizer` 抽象接口（默认 `AnnotateRecognizer` 轻标注，可插专用模型）。
- `.env` `FORMULA_MODE=annotate|latex|model`。

### 11.7 VLM 成本/效果埋点（#7）
- `src/utils/metrics.py`：`VlmCallMetric{kind, model, latency_ms, tokens, cost_usd, retry, success}`，每次调用记录；task 级 `TaskMetrics` 汇总写入 `ParseResult.metrics`。
- `.env` `VLM_OCR_DPI`（默认 200，探究 DPI 对 OCR 准确率/成本影响）、`VLM_DESC_DPI`、`VLM_RESPONSE_CACHE=on|off`（按 image bytes hash 缓存响应，避免重复调用）、`VLM_BATCH`（预留批量）。

### 11.8 评测 harness（#10，支撑 #1/#2/#3/#4）
- `src/eval/sample_set.py`：加载标注集，约定 `samples/<name>.pdf` + `samples/<name>.label.json`（每页期望 type、可选期望 blocks）。
- `src/eval/runner.py`：遍历样本集调 `run_parse`，收集结果 + features + metrics；CLI `uv run python -m src.eval.runner --samples-dir samples --report report.json`。
- `src/eval/metrics.py`：
  - 分类准确率（总体 + 各类型 P/R/F1）+ 混淆矩阵（#1/#10）。
  - 特征分布（#2/#3）：按类型聚合 `PageFeatures`，输出可分析特征向量表。
  - 表格 backend 对比（#4）：同表格样本跑多 backend，对比行列准确率/合并单元格召回/耗时。
  - VLM 成本/耗时聚合（#7）。
  - 输出 diff：结构化 Block vs 期望 blocks（文本相似度、表格单元格匹配）。
- 输出 `report.json` + 可读 `report.md`（混淆矩阵、特征分布、badcase）；回归：改阈值/换 backend 后重跑对比。

### 11.9 前端探究面板（可选）
- `PageCard` 展示 `page_type` + 关键特征（line_count/area_ratio/columns）+ VLM 成本；提供「查看 PageFeatures JSON」。
- 导出含 `metrics`。

### 11.10 VLM 模型选型对比（#7 扩展）
- **模型注册表** `src/utils/vlm_models.py` + `models.json`：命名模型注册表，每项 `{base_url, api_key, model}`（如 `glm-4v` / `qwen-vl-max` / `deepseek-vl`，可跨通义/智谱/DeepSeek/OpenAI）。`get_model(name) -> ModelConfig`、`list_models() -> list[str]`。向后兼容：无 `models.json` 时回退 `.env` 单组 `VLM_BASE_URL/VLM_API_KEY/VLM_MODEL` 作默认模型。
- **vlm.py**：`_call_vlm(image_bytes, prompt, model_name=None)` 按 name 解析 `ModelConfig`（默认 `VLM_DEFAULT_MODEL`），用其 base_url/key/model 调用；`VlmCallMetric.model` 记实际模型名。单任务指定单一模型，对比通过 eval 多次跑。
- **API**：`POST /api/v1/parse` 的 `vlm_model` 从注册表选；新增 `GET /api/v1/models -> {models:[...], default:...}` 供前端下拉 + 对比选择。
- **eval 模型对比**：`runner.py --compare-vlm glm-4v,qwen-vl-max,deepseek-vl` 对同一标注样本集每模型跑一遍（mixed/scan 页走该模型），`metrics.py` 产**模型对比表**（per model：mixed 图片描述与期望相似度、scan OCR 与期望文本相似度、cost_usd、latency_ms、tokens、调用数）；report 加「VLM 模型对比」章节。

---

## 12. 里程碑对齐（§13.3 M1–M6）

| 里程碑 | 范围 | 对应模块/文件 |
|--------|------|--------------|
| **M1 后端跑通** | FastAPI + 分类 + 文本/表格，单页 `/api/v1/parse` 同步返回 | `server.py`、`controller/parse_controller.py`、`parser/classify.py`、`parser/extract_text.py`、`parser/extract_table.py`、`parser/pipeline.py`、`models/schemas.py`、`utils/env.py`、`utils/pdf_utils.py` |
| **M2 异步+进度** | BackgroundTasks + 状态接口，前端轮询进度 | `task_manager/task_service.py`、`task_manager/progress_service.py`、`store/task_store.py`、`controller/task_controller.py`、前端 `stores/parser.ts`、`services/parse.ts`、`StatusBar.vue` |
| **M3 图文混排 + VLM** | 接云端多模态，mixed/scan 走 VLM | `parser/vlm.py`、`parser/mixed.py`、`parser/scan.py`、`store/image_cache.py`、`controller/image_controller.py` |
| **M4 前端体验** | 分块预览、图片块、表格复制、导出 | `views/ParserView.vue`、`components/*`（PageCard/BlockView/TextBlock/ImageBlock/TableBlock/ExportBtn）、`controller/export_controller.py` |
| **M5 边界与坑点** | 隐形文本层、矢量 Logo、跨页表格、VLM 重试兜底 | `classify.py`（面积过滤/隐形层/跨页/矢量图）、`vlm.py`（重试退避超时）、`extract_text.py`（公式标注） |
| **M6 评测/探究层** | eval harness + 配置化 + 特征埋点 + 可插拔提取器 + 多栏 + 公式探究 | `eval/`、`utils/metrics.py`、`parser/table_extractor.py`、`parser/formula.py`、`classify.py`(features)、`extract_text.py`(多栏) |

---

## 附：启动与依赖速查

```bash
# 后端
uv sync                                   # 安装依赖（pyproject.toml）
uv run python -m src.server               # 启动 http://localhost:8082
uv run pytest src/test/                   # 测试

# 前端
cd frontend && npm install
npm run dev                               # http://localhost:5173
```

后端依赖（`pyproject.toml`）：`fastapi`、`uvicorn`、`pymupdf`、`pdfplumber`、`httpx`、`python-multipart`、`pydantic`、`python-dotenv`；dev：`pytest`。

前端依赖（`package.json`）：`vue`、`element-plus`、`pinia`、`vue-router`、`axios`、`markdown-it`；dev：`vite`、`@vitejs/plugin-vue`、`typescript`、`sass`。

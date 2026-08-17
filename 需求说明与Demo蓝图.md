# PDF 图文混排解析 — 需求说明与 Demo 蓝图

> 文档定位：在原有《pdf图文混排解析》技术方案（分层路由架构）基础上，补全产品需求侧内容，并给出「前端 + 后端」Demo 的落地蓝图。
> 适用阶段：需求规划 / PRD 撰写 → 研发评审。
> 当前结论状态：需求草稿（Demo 范围），部分决策点见文末「待确认问题」。

---

## 0. 现状与本文档的关系

原文档已沉淀了**核心技术方案**（价值很高，予以保留并纳入本文第 5、10 节）：

- 分层路由架构：PDF → PyMuPDF 页面分类 → 按 `text / table / mixed / scan` 分派引擎；
- 原则：**不整页喂多模态模型**，而是拆区域，每块走最适合的引擎；
- 页面分类、表格提取、图文混排切图、各类坑点的代码与对照表。
- **原文档 4 段核心 Python 代码（classify_page / extract_tables / process_mixed_page / process_pdf）已逐段对照收录于文末「附录 B」，方案与技术实现一一对应。**

原文档**缺失**的部分（即本文补全的内容）：

- 目标用户、使用场景、成功标准；
- 前端交互与功能边界；
- 后端接口契约、数据模型、输出格式；
- 验收标准（EARS）、异常/边界、埋点与指标；
- Demo 技术栈与目录结构。

---

## 1. 背景

PDF 是信息密度最高、但机器解析最难的文档格式之一：同一页里常混合**正文、表格、插图、公式、扫描图片**。

当前团队/业务面对的典型困境：

1. **纯规则引擎**（PyMuPDF / pdfplumber）对图文混排、无边框表格、公式无力，丢内容、错顺序；
2. **无差别整页喂多模态大模型**（VLM）虽然"能懂"，但成本高、速度慢、token 爆炸，且失去结构化；
3. 缺乏一个**可跑、可看、可验证**的载体，研发只能写脚本零散试，无法直观对比各页面类型的解析效果。

**本文方案**（沿用原文档）：采用**分层路由架构**——先不渲染、只读页面内部对象做类型判断，再按类型把每块内容分派到最合适、最便宜的引擎。文字走原生抽取，表格走专用工具，图片区域裁剪后送 VLM 理解，扫描件整页渲染做 OCR。

---

## 2. 目标与边界

### 2.1 目标（Goals）

- **G1**：实现一个**前端 + 后端**的可运行 Demo，覆盖 PDF 四类页面的解析：纯文本、表格、图文混排、扫描件。
- **G2**：让研发能**上传 PDF → 看到逐页分类结果 → 分块预览解析内容 → 导出结构化结果**，直观验证分层路由效果。
- **G3**：图片区域理解接入**云端多模态 API**（OpenAI 兼容接口，可切换通义/智谱等），做到"真理解"而非 mock。
- **G4**：接口与数据模型设计清晰，便于后续从 Demo 演进为真实服务（可替换 VLM、加队列、加权限）。

### 2.2 非目标（Non-Goals，本次 Demo 不做）

- ❌ 不追求生产级并发 / 高可用 / 多租户；
- ❌ 不做用户账号体系、鉴权（内部工具，Demo 阶段可无登录）；
- ❌ 不做海量 PDF 批处理管道（仅支持单文件解析，可串行多页）；
- ❌ 不内置本地 VLM 部署（VLM 走云端 API，可后续替换）；
- ❌ 不承诺 100% 解析准确率（Demo 目标是跑通流程 + 暴露效果边界）；
- ❌ 不做结果持久化（结果存内存 dict，按 task_id 索引，进程重启即清空）。

---

## 3. 用户与场景

### 3.1 用户画像

| 角色 | 说明 | 核心诉求 |
|------|------|----------|
| 内部研发/算法同学（主用户） | 负责解析管线研发 | 快速验证各页面类型解析效果、对比不同 VLM、定位 badcase |
| Tech Lead / 评审人 | 看 Demo 决策是否投入 | 直观看到能力边界与成本 |

### 3.2 用户故事（User Stories）

- **US1**：作为研发，我上传一份含图表混排的 PDF，希望能看到**每一页被判定为 text/table/mixed/scan 的类别**，确认分类逻辑是否准确。
- **US2**：作为研发，我希望图文混排页能**把文字和图片描述分别展示**，并知道图片在页面中的位置和顺序。
- **US3**：作为研发，我希望表格页能拿到**结构化表格**（可复制的 Markdown/CSV），而不是图片。
- **US4**：作为研发，我希望扫描件页能**走 OCR + 理解**，得到可读文字。
- **US5**：作为研发，我希望在解析**长文档**时能**看到进度**（第几页 / 各页类型），而不是卡住干等。
- **US6**：作为研发，我希望能把最终结果**导出为 Markdown 或 JSON**，方便贴到笔记/IM/其他系统继续用。

---

## 4. 功能清单

| 编号 | 功能 | 说明 | 优先级 | Demo 是否含 |
|------|------|------|--------|-------------|
| F1 | PDF 上传 | 选择/拖拽 PDF，触发解析；前端做大小/类型预校验 | P0 | ✅ |
| F2 | 页面类型分类 | 后端用 PyMuPDF 判断每页类型，返回分类结果 | P0 | ✅ |
| F3 | 纯文本抽取 | `get_text("markdown")` 原生抽取 | P0 | ✅ |
| F4 | 表格提取 | pdfplumber 提取结构化表格 | P0 | ✅ |
| F5 | 图文混排解析 | 文字原生 + 图片区域裁剪送 VLM 得到描述 | P0 | ✅ |
| F6 | 扫描件 OCR+理解 | 整页渲染送 VLM 做 OCR 与理解 | P1 | ✅（依赖 VLM key） |
| F7 | 解析进度/状态 | 逐页进度、各页类型、整体状态 | P0 | ✅ |
| F8 | 结果分块预览 | 按页/按块展示文字、图片描述、表格 | P0 | ✅ |
| F9 | 结果导出 | 导出 Markdown / JSON | P1 | ✅ |
| F10 | 裁剪图查看 | 点击图片块查看原图/裁剪区域 | P2 | 可选 |

---

## 5. 核心流程（后端解析管线）

```
PDF 上传
  │
  ▼
[任务创建] 生成 task_id，状态=pending，后台异步解析
  │
  ▼
逐页循环:
  ├─ PyMuPDF 页面分类 ──► text  → 原生抽取 markdown
  │                      table → pdfplumber 提取表格
  │                      mixed → 文字原生 + 图片区域裁剪 → VLM 描述
  │                      scan  → 整页渲染 → VLM OCR+理解
  │
  ▼
[进度更新] 每完成一页更新 status/progress（前端轮询）
  │
  ▼
[完成] 拼装 ParseResult，状态=completed（部分失败=partial）
  │
  ▼
前端分块预览 / 导出
```

> 分类与分派逻辑见原文档（PyMuPDF `classify_page`、表格/图文混排处理代码），本文直接沿用，并约束为上述四类路由。

**重要架构原则（精度优先）**：本项目目标是**精确还原图文混排内容**，因此必须区分两个层次——

- **抽取层（唯一真相源）**：分类结果、原生文字、表格单元格、图片 VLM 描述、每个 block 的页面坐标 `bbox` 与 `page_type` 标签，全部以**结构化**形式保留在 `ParseResult / PageResult / Block` 中（内存存储，见 §8）。这是精度所在，绝不可丢弃。
- **呈现层（派生视图）**：`markdown` 只是从结构化真相源**派生**出来的一个人读/LLM 友好视图，用于前端预览与导出。纯 markdown 会丢失合并单元格、bbox 坐标、图片在页内精确位置等信息，因此**导出必须同时提供 JSON 以保全精度**（见 F10 / O1）。

> 即：**结构化精确表示是源，markdown 是视图**。统一 markdown 只约束"默认对外展示/导出的可读格式"，不约束底层保留结构化精度。

---

## 6. 前端交互说明

### 6.1 页面与组件

- **上传区**：拖拽 / 点击选择 PDF；显示文件名、大小；前端预校验（类型=application/pdf，大小≤50MB）。
- **解析状态条**：显示整体状态（pending/parsing/completed/partial/failed）+ 进度百分比 + "已处理 X / 共 Y 页"。
- **分页结果列表**：每页一张卡片，头部标 `第 N 页 · 类型：mixed`；卡片内按阅读顺序列出 block。
- **Block 渲染**：
  - `text`：渲染 markdown 文本；
  - `image`：显示图片缩略图 + VLM 描述文字 + 位置 bbox 标注；
  - `table`：渲染为表格（Markdown 表格或 HTML `<table>`），提供"复制 Markdown"；
- **导出按钮**：导出当前结果 Markdown / JSON（下载文件）。

### 6.2 状态与交互边界

- 解析中禁用重复上传；
- 某页 VLM 失败：该 block 标记"图片未识别（VLM 调用失败）"，页面其余内容正常展示，整体状态置为 `partial`；
- 大文件：进度条 + 不阻塞 UI（轮询，不阻塞主线程）。

---

## 7. 后端接口契约（API Contract）

> Base：FastAPI，前缀 `/api/v1`，JSON 响应。VLM 调用为 OpenAI 兼容接口（base_url 可配，支持通义/智谱/DeepSeek 等）。

### 7.1 创建解析任务

```
POST /api/v1/parse
Content-Type: multipart/form-data
  file: <PDF 文件>
  (可选) vlm_model: string    # 不传用默认
响应 200:
{
  "task_id": "uuid",
  "filename": "report.pdf",
  "status": "pending",
  "total_pages": 12,
  "created_at": "2026-08-13T15:20:00+08:00"
}
```

### 7.2 查询任务状态与结果

```
GET /api/v1/tasks/{task_id}
响应 200:
{
  "task_id": "uuid",
  "status": "parsing | completed | partial | failed",
  "progress": 5, "total_pages": 12,
  "pages": [
    {
      "page": 1, "type": "mixed",
      "blocks": [
        {"type":"text","content":"...","bbox":[x0,y0,x1,y1],"order":0},
        {"type":"image","description":"一张柱状图，展示...","bbox":[...],"order":1, "image_url":"/api/v1/tasks/{id}/images/1/0"}
      ]
    }
  ],
  "cost_usd": 0.012,
  "errors": [{"page":7,"message":"VLM timeout"}]
}
```

### 7.3 导出

```
GET /api/v1/tasks/{task_id}/export?format=markdown|json
响应: 下载文件（.md / .json）
```

### 7.4 裁剪图（可选 F10）

```
GET /api/v1/tasks/{task_id}/images/{page}/{index}
响应: image/* （后端从解析时缓存的裁剪图返回）
```

---

## 8. 数据模型与输出格式

### 8.1 核心模型

```
TaskStatus   = pending | parsing | completed | partial | failed
PageType     = text | table | mixed | scan
BlockType    = text | image | table

Block {
  type: BlockType
  content: string        # 文本/图片描述/Markdown 表格
  bbox: [number,number,number,number]   # [x0,y0,x1,y1] 页面坐标
  order: int             # 同页阅读顺序
  image_url?: string     # 仅 image 块
}
PageResult {
  page: int
  type: PageType
  blocks: Block[]
}
ParseResult {
  task_id, filename, status, total_pages, progress
  pages: PageResult[]
  cost_usd?: number
  errors: { page?: int, message: string }[]
  created_at, finished_at?
}
```

### 8.2 Markdown 导出示例

```markdown
# report.pdf 解析结果

## 第 1 页（图文混排 mixed）

正文段落……

![图片1](image_url)
> 图片描述：一张柱状图，横轴为月份，纵轴为营收……

## 第 2 页（表格 table）

| 月份 | 营收(万) |
|------|----------|
| 1月  | 120      |
```

---

## 9. 验收标准（EARS）

**Ubiquitous（系统始终满足的约束）**

- **U1**：系统应仅接受 `application/pdf` 格式文件，拒绝其他格式并返回明确提示。
- **U2**：系统应对上传文件大小设上限（**50MB**），超限即拒绝并提示。
- **U3**：系统应在解析全程保持任务状态可追溯（pending→parsing→completed/partial/failed）。

**Event-driven（事件触发）**

- **E1**：当用户上传 PDF 并触发解析时，系统应创建任务并返回 `task_id`，随后在后台异步开始解析。
- **E2**：当某一页解析完成时，系统应更新该任务进度与对应页结果，使前端轮询可获取。
- **E3**：当全部页面处理完毕时，系统应将任务状态置为 `completed` 或 `partial`（存在失败页时）。

**Unwanted（异常/故障处理）**

- **X1**：如果文件损坏或无法被 PyMuPDF 打开，则系统应将任务置为 `failed` 并返回可读错误。
- **X2**：如果某页 VLM 调用失败/超时，则系统应将该图片块标记为"未识别"，继续处理其余内容，整体状态置 `partial`。
- **X3**：如果 VLM 返回内容异常（空/格式错），则系统应记录错误并跳过该块，不影响其他页。

**State-driven（特定状态下行为）**

- **S1**：当某页被分类为 `scan` 时，系统应整页渲染为图片并送 VLM 做 OCR + 理解。
- **S2**：当某页被分类为 `table` 时，系统应使用 pdfplumber 提取**结构化表格，并保留行列结构与合并单元格信息**（精度要求：不扁平化丢结构）。
- **S3**：当某页被分类为 `mixed` 时，系统应文字原生抽取 + 图片区域裁剪送 VLM。
- **S4**：当系统产出任一 block 时，应**保留该 block 的页面坐标 `bbox` 与 `page_type` 标签**于结构化结果中；markdown 视图可省略坐标，但 JSON 导出必须保留（精度要求：定位不丢）。
- **S5**：当检测到**跨页表格**时，系统应尝试将跨页断行合并为连续表格，或明确标注"跨页"边界，避免行断裂丢失结构（精度要求：跨页不丢行）。

**精度总约束**：结构化表示（`ParseResult/PageResult/Block`，含 bbox、表格单元格、VLM 描述）是**唯一真相源**；markdown 仅为其派生视图。判定解析"精确"以结构化 JSON 为准，而非 markdown 可读性。

**Optional（可选功能）**

- **O1**：当启用"导出 Markdown/JSON"时，系统应生成对应格式文件供下载。
- **O2**：当启用"裁剪图查看"时，系统应缓存并返回图片区域原图。

---

## 10. 边界场景与异常处理（含原文档坑点）

| 场景 | 现象 | Demo 处理 |
|------|------|-----------|
| 扫描件含隐形文本层 | OCR 后嵌入不可见文本，`get_text()` 读到字但位置乱 | 检测文本块坐标是否异常密集/重叠；若疑似隐形层且图片为主，按 `scan` 处理 |
| 矢量 Logo 误判为表格 | Logo 由大量矢量线组成，`line_count` 高 | 加面积过滤：表格占页面较大区域，Logo 较小 |
| 图片是矢量图 | `get_images()` 返回空但页面有图（SVG 风插图） | 检查 `get_drawings()` 复杂度，路径极多时按 `mixed` 处理 |
| 表格跨页 | 一页表格拆两页，单独处理断行 | 上下文记忆：上一页是表格则当前页优先按表格处理 |
| 公式识别 | LaTeX 公式在 PDF 里是碎片化字符 | 用 `get_text("latex")` 或标注为公式块（Demo 仅标注，不深究） |
| VLM 超时/限流 | 云端 API 慢或 429 | 重试 1 次 + 退避；仍失败按 X2 标记未识别 |
| 超大 PDF | 解析久、占用内存 | 前端进度条；后端分页流式处理，不一次性载入全部位图 |
| 并发上传 | 多用户同时解析 | Demo **不要求并发**（单进程串行处理）；结果存**内存 dict**（按 task_id 索引），进程重启即清空，无需持久化 |

---

## 11. 权限与埋点

- **权限**：Demo 阶段为内部工具，无登录鉴权；后续接公司 SSO / API Key。
- **埋点事件**（用于衡量效果与成本）：
  - `parse_started`（文件名哈希、页数）
  - `page_classified`（page、type）
  - `vlm_called`（image/scan、model、token、cost_usd、latency）
  - `parse_completed`（status、耗时、总成本）
  - `export`（format）
  - `error`（page、type、message）

---

## 12. 数据指标

| 指标 | 口径 | 目标（Demo 参考） |
|------|------|-------------------|
| 解析成功率 | completed+partial / 总任务 | —（暴露边界即可） |
| 分类准确率 | 抽样人工核对 text/table/mixed/scan | **硬性目标 ≥ 90%**（各类型分别统计，见 §14） |
| 单页平均耗时 | 各类型分别统计 | text<0.5s，table<2s，mixed/scan 取决于 VLM |
| 单页 VLM 成本 | cost_usd / 调用次数 | 控制 mixed/scan 才调用 VLM |
| 端到端耗时 | 创建任务到 completed | 12 页 < 60s（视 VLM） |

---

## 13. Demo 技术蓝图

### 13.1 技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 后端 | **FastAPI** + Uvicorn | 异步，BackgroundTasks 跑解析 |
| PDF | **PyMuPDF (fitz)** | 分类、文本、图片裁剪、渲染 |
| 表格 | **pdfplumber** | 结构化表格提取 |
| VLM | **OpenAI 兼容 SDK (httpx)** | base_url 可配，支持通义/智谱/DeepSeek |
| 前端 | **Vue 3 + Element Plus + Vite** | 管理后台风格 SPA，组件化清晰 |
| 存储 | 内存 dict | Demo 不要求并发/持久化，task_id → 结果存内存，进程重启即清空 |
| 配置 | `.env` | VLM_API_KEY / VLM_BASE_URL / VLM_MODEL / MAX_FILE_MB=50 |

> VLM 采用**公共参数（OpenAI 兼容接口）**：`.env` 预留 `VLM_BASE_URL` / `VLM_API_KEY` / `VLM_MODEL`，由你填写 key 与端点（可替换为通义/智谱/DeepSeek 等兼容服务）。后端 `vlm.py` 统一实现原文档的 `vlm_describe` / `extract_and_describe_images` / `vlm_ocr` 三个占位函数。
>
> **文本格式（决策 4 精确表述）**：底层抽取**始终保留结构化精确表示**（带 `bbox`、表格单元格、`page_type` 的 `Block`/`PageResult`）作为唯一真相源；对外**默认呈现/导出 `markdown` 视图**（人读 + LLM 友好）。因纯 markdown 会丢失合并单元格、坐标、跨页结构，故**导出同时提供 JSON 保全精度**（见 F10 / O1）。即"统一 markdown"约束的是展示格式，不约束底层精度保留。

### 13.2 建议目录结构

```
pdf-parser-demo/
├─ backend/
│  ├─ main.py            # FastAPI app + 路由
│  ├─ parser/
│  │  ├─ classify.py     # PyMuPDF 页面分类（原文档 classify_page）
│  │  ├─ extract_text.py # 文本抽取
│  │  ├─ extract_table.py# pdfplumber 表格
│  │  ├─ mixed.py        # 图文混排：切图 + VLM
│  │  ├─ scan.py         # 扫描件 OCR+理解
│  │  └─ vlm.py          # VLM 客户端（OpenAI 兼容，可配）
│  ├─ models.py          # ParseResult / PageResult / Block 等
│  ├─ store.py           # 任务状态存储
│  ├─ config.py          # 读 .env
│  └─ requirements.txt
├─ frontend/
│  ├─ src/
│  │  ├─ App.vue
│  │  ├─ api.js          # 调后端（axios）
│  │  ├─ components/     # Uploader / StatusBar / PageCard / BlockView / ExportBtn
│  │  └─ main.js         # 挂载 Vue + Element Plus
│  ├─ index.html
│  ├─ vite.config.js
│  └─ package.json       # vue / element-plus / axios / vite
├─ .env.example
└─ README.md
```

### 13.3 里程碑（建议）

1. **M1 后端跑通**：FastAPI + 分类 + 文本/表格，单页 `/api/v1/parse` 同步返回；
2. **M2 异步+进度**：BackgroundTasks + 状态接口，前端轮询进度；
3. **M3 图文混排 + VLM**：接云端多模态，mixed/scan 走 VLM；
4. **M4 前端体验**：分块预览、图片块、表格复制、导出；
5. **M5 边界与坑点**：隐形文本层、矢量 Logo、跨页表格、VLM 重试兜底。

---

## 14. 已确认决策（原待确认问题已拍板）

> 以下为已确认的产品/技术决策，替代原「待确认问题」。后续评审与研发以本表为准。

| # | 议题 | 决策 |
|---|------|------|
| 1 | VLM 供应商与 Key | 使用**公共参数（OpenAI 兼容接口）**：`.env` 预留 `VLM_BASE_URL` / `VLM_API_KEY` / `VLM_MODEL`，由你填写 key 与端点（可替换为通义/智谱/DeepSeek 等兼容服务）。后端 `vlm.py` 统一实现原文档的 `vlm_describe` / `extract_and_describe_images` / `vlm_ocr`。 |
| 2 | 上传上限 | **50MB**（见 EARS U2）。 |
| 3 | 并发与持久化 | **不要求并发**，单进程串行处理；结果存**内存 dict**（按 task_id 索引），进程重启即清空，无需落库。 |
| 4 | 文本抽取默认格式 | **底层结构化精确表示为唯一真相源**（保留 `bbox`、表格单元格、`page_type`）；对外**默认呈现/导出 `markdown` 视图**；因纯 md 会丢精度，**导出同时提供 JSON 保全精度**（见 §5 架构原则 / §13.1 注）。 |
| 5 | 前端形态 | **Vue 3 + Element Plus + Vite**（见 §13.1 / §13.2）。 |
| 6 | 验收口径 | **设定"分类准确率"硬性目标**：测试集每类 ≥ 20 页、人工标注核对，**分类准确率 ≥ 90%** 方视为 Demo 完成（见 §12）。 |

> 备注：决策 6 的 90% 为拟定门槛，具体阈值可在评审时按样本难度微调；badcase 仍需记录以便迭代。

---

## 附：原技术方案要点（保留摘录）

- 架构：`PDF → PyMuPDF 页面分类 → 纯文本：原生抽取 / 表格：pdfplumber·Marker / 图文混排：文字原生+图片裁出走 VLM / 扫描件：整页渲染走 VLM`
- 分类启发式：扫描件（无文本有图）、表格（矢量线多+多文本块，需加面积过滤避免 Logo 误判）、图文混排（有图有文）、纯文本（有文无图少线）。
- 更精细路由：`get_text("dict")` 拿每块 bbox → 文本块原生、图片块渲染后 VLM、按 y 坐标排序拼接。

---

## 附录 B：原技术方案代码原文（逐段对照）

> 以下 4 段代码均**逐字摘录**自原文档《pdf图文混排解析》，未做改写。每段标注其在原文档的位置与本需求文档的对应章节，做到「方案 ↔ 技术实现」一一对应。
> 注：原文档中 `vlm_describe(...)`、`extract_and_describe_images(...)`、`vlm_ocr(...)` 为 VLM 调用占位函数，本 Demo 由 §13.1 的 `vlm.py`（OpenAI 兼容客户端）统一实现。

### B.1 页面类型判断 — 对应原文档「一」、本需求 §5

> 用 PyMuPDF 不渲染、只读内容对象做分类，返回 `text | table | mixed | scan`。

```python
import fitz  # PyMuPDF

def classify_page(page: fitz.Page):
    text_blocks = page.get_text("blocks")  # 文本块
    images = page.get_images()             # 嵌入图片
    drawings = page.get_drawings()         # 矢量图形(表格边框、线条)

    # 1. 扫描件：没有文本层，只有图片
    if len(text_blocks) == 0 and len(images) > 0:
        return "scan"

    # 2. 表格：大量矢量线 + 多个文本块(粗略 heuristic)
    line_count = len([d for d in drawings if d['type'] in ('line', 'rect')])
    if line_count > 20 and len(text_blocks) >= 4:
        return "table"

    # 3. 图文混排
    if len(images) > 0 and len(text_blocks) > 0:
        return "mixed"

    # 4. 纯文本
    if len(text_blocks) > 0 and len(images) == 0 and line_count < 10:
        return "text"

    return "mixed"  # 兜底
```

### B.2 表格提取 — 对应原文档「二」、本需求 §5 / F4

> PyMuPDF 负责"发现"表格区域，结构化提取交给 pdfplumber。

```python
import pdfplumber

def extract_tables(pdf_path: str, page_num: int):
    with pdfplumber.open(pdf_path) as pdf:
        return pdf.pages[page_num].extract_tables()  # list of list，可直接转 DataFrame
```

### B.3 图文混排切图 — 对应原文档「三」、本需求 §5（mixed 路由）/ F5

> 文字走原生 `get_text("markdown")`，仅把图片区域裁出送 VLM 理解。

```python
def process_mixed_page(page: fitz.Page):
    text = page.get_text("markdown")  # PyMuPDF 1.23+ 支持 markdown

    image_descriptions = []
    for img_index, img in enumerate(page.get_images(full=True), start=1):
        xref = img[0]
        image_bytes = page.parent.extract_image(xref)["image"]
        desc = vlm_describe(image_bytes)  # 多模态 API
        image_descriptions.append({
            "index": img_index,
            "description": desc,
            "bbox": img[1],  # 图片在页面中的位置
        })

    return {"text": text, "images": image_descriptions}
```

### B.4 简化版流水线（总调度）— 对应原文档「五」、本需求 §5 / F2–F6

> 按页分类后分派到各分支，组装 `results`；`scan` 走整页渲染 + VLM OCR。

```python
import fitz
import pdfplumber

def process_pdf(pdf_path: str):
    doc = fitz.open(pdf_path)
    results = []

    for page_num, page in enumerate(doc):
        page_type = classify_page(page)

        if page_type == "text":
            content = page.get_text("markdown")

        elif page_type == "table":
            with pdfplumber.open(pdf_path) as pdf:
                tables = pdf.pages[page_num].extract_tables()
            content = {"tables": tables, "raw_text": page.get_text()}

        elif page_type == "mixed":
            content = {
                "text": page.get_text("markdown"),
                "image_descriptions": extract_and_describe_images(page),
            }

        elif page_type == "scan":
            pix = page.get_pixmap(dpi=200)
            content = vlm_ocr(pix.tobytes())

        results.append({"page": page_num + 1, "type": page_type, "content": content})

    return results
```

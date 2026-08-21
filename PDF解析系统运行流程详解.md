# PDF 解析系统运行流程详解

> 本文档详细描述 PDF Parser Demo 的完整运行机制，从上传 PDF 到最终输出 Markdown / JSON 的全过程。

---

## 一、系统架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         前端 (Vue 3 + Vite)                         │
│  上传 PDF → 轮询进度 → 查看结果 → 导出 Markdown/JSON/知识库           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTP (FastAPI)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         后端 (Python FastAPI)                        │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ 任务控制器    │  │ 解析控制器    │  │ 导出控制器    │              │
│  │ task_controller│ │parse_controller│ │export_controller│            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                 │                       │
│         ▼                 ▼                 ▼                       │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                   任务管理器 (task_service)               │       │
│  │  create_task → run_parse (后台线程) → progress_service  │       │
│  └─────────────────────────┬───────────────────────────────┘       │
│                            │                                        │
│                            ▼                                        │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                   页面调度器 (pipeline)                   │       │
│  │  classify_page → dispatch_page → extract_table/text/... │       │
│  └─────────────────────────┬───────────────────────────────┘       │
│                            │                                        │
│         ┌──────────────────┼──────────────────┐                    │
│         ▼                  ▼                  ▼                    │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ 表格提取     │  │ 文本提取      │  │ VLM 调用     │              │
│  │ table_extractor│ │extract_text  │  │ vlm.py       │              │
│  │ (pdfplumber + │  │ (PyMuPDF)    │  │ (OpenAI 兼容)│              │
│  │  camelot)    │  │              │  │              │              │
│  └─────────────┘  └──────────────┘  └──────────────┘              │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                   任务存储 (task_store)                   │       │
│  │  内存字典 + 持久化到 .task_store.json                     │       │
│  └─────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、完整运行流程（从上传到结果）

### 阶段 1：上传 PDF 并创建任务

**入口**: `POST /api/v1/parse`

```
前端上传 PDF + 选择 VLM 模型
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ parse_controller.parse()                                      │
│   1. 读取文件字节                                             │
│   2. 调用 task_service.create_task()                          │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ task_service.create_task()                                    │
│   1. pdf_utils.validate_upload()  → 校验文件类型/大小         │
│   2. unique_id.gen_task_id()      → 生成唯一任务 ID           │
│   3. pdf_utils.save_temp_pdf()    → 保存到 temp/{task_id}.pdf │
│   4. pdf_utils.get_page_count()   → 获取总页数                │
│   5. task_store.create()          → 创建 ParseResult 记录     │
│   6. 返回 CreateTaskResponse + pdf_path                       │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ background_tasks.add_task(task_service.run_parse, ...)        │
│   → 后台线程启动解析任务，前端立即返回 task_id                 │
└───────────────────────────────────────────────────────────────┘
```

**前端行为**: 拿到 `task_id` 后，轮询 `GET /api/v1/tasks/{task_id}` 获取进度。

---

### 阶段 2：后台解析（逐页处理）

**核心**: `task_service.run_parse()`

```
run_parse(task_id, pdf_path, vlm_model)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. progress_service.mark_parsing(task_id)                     │
│      → 状态改为 "parsing"                                     │
│ 2. metrics.new_task_metrics()                                 │
│      → 创建成本/延迟统计上下文                                │
│ 3. fitz.open(pdf_path)                                        │
│      → 用 PyMuPDF 打开 PDF                                    │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
        ┌───────────────────────────────────────┐
        │  for page_num in range(page_count):    │
        │       逐页处理，每页经过以下步骤：      │
        └───────────────────────────────────────┘
                        │
                        ▼
```

#### 阶段 2.1：页面分类 (`classify.classify_page`)

```
classify_page(page, prev_type, pdf_path, page_num, task_id, ctx)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. classify_features(page)                                    │
│      → 提取页面特征:                                          │
│        - line_count: 线条数量（表格网格线）                   │
│        - text_blocks_count: 文本块数量                        │
│        - images_count: 图片数量                               │
│        - area_ratio: 线条面积 / 页面面积                      │
│        - overlap_rate: 文本块重叠率                           │
│        - char_density: 字符密度                               │
│        - columns: 列数（通过 x0 聚类）                        │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. _classify_with_features(feats, prev_type)                  │
│      → 根据阈值判断页面类型:                                  │
│        - "scan": 无文本块 + 有图片                            │
│        - "table": 线条 > 阈值 + 文本块 >= 最小值 + 面积比达标 │
│        - "mixed": 图片 + 文本 / 大量矢量路径                  │
│        - "text": 有文本 + 少线条                              │
│        - 跨页上下文: 上一页是 table + 当前有线条 → table      │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 3. 探针兜底 (probe_trigger)                                   │
│      → 当规则分类不确定时，用 HybridExtractor 快速探测:       │
│        - 线条多但面积比不足                                   │
│        - 文本块远多于线条（稀疏表格布局）                     │
│      → 探测到表格 → 强制分类为 "table"                        │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 4. VLM 兜底 (_vlm_detect_table)                               │
│      → 分类为 "mixed" 且探针未检出时:                         │
│        - 渲染页面为图片                                       │
│        - 调用 VLM 判断是否含表格                              │
│        - 需开启 CLS_VLM_FALLBACK=on                           │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
                返回 (page_type, features)
```

**分类阈值**（可通过环境变量配置）：

| 环境变量 | 默认值 | 含义 |
|---------|--------|------|
| `CLS_LINE_COUNT_TABLE` | 20 | 判定为表格的最小线条数 |
| `CLS_TEXT_BLOCKS_MIN` | 4 | 表格页的最少文本块 |
| `CLS_AREA_RATIO_MIN` | 0.15 | 最小线条面积比 |
| `CLS_LINE_COUNT_TEXT` | 20 | 文本页的最大线条数 |
| `CLS_VLM_FALLBACK` | off | 是否启用 VLM 兜底 |

---

#### 阶段 2.2：页面调度 (`pipeline.dispatch_page`)

根据 `page_type` 调用不同的提取器：

```
dispatch_page(page, page_type, task_id, page_num, doc, ...)
        │
        ├── page_type == "text"  ──→  extract_text.extract_text()
        │                              → PyMuPDF get_text("dict")
        │                              → 多列阅读顺序排序
        │
        ├── page_type == "table" ──→  extract_table.extract_tables()
        │                              → HybridExtractor (pdfplumber + camelot)
        │                              → 跨页续表检测
        │
        ├── page_type == "mixed" ──→  mixed.process_mixed_page()
        │                              → 文本提取 + 图片提取
        │                              → VLM 描述图片
        │
        └── page_type == "scan" ──→  scan.process_scan_page()
                                       → 渲染整页为图片
                                       → VLM OCR 识别
```

---

#### 阶段 2.3：表格提取详解 (`HybridExtractor`)

这是最复杂的部分，也是第 24 页问题的核心：

```
HybridExtractor.extract(page, pdf_path, page_num)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. PdfplumberExtractor.extract()                              │
│      → pdfplumber.find_tables() 基于线条检测表格              │
│      → 检测合并单元格 (_detect_merged)                        │
│      → 输出: List[TableData]                                  │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. CamelotStreamExtractor.extract()                           │
│      → camelot.read_pdf(flavor="stream") 基于文本流检测       │
│      → 对无线表格/稀疏表格效果更好                            │
│      → 输出: List[TableData]                                  │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 3. _merge_fragmented_rows(t) 【新增修复】                     │
│      → 修复 camelot 错误拆分行的问题                          │
│      → 场景: Comfort（左列）和 Interior versatility（中列）   │
│        本应同行，但 camelot 分成两行                           │
│      → 检测: 一行只有左侧列 + 下一行有左侧+右侧列             │
│      → 合并: 把下一行左侧内容移到当前行空列                    │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 4. _merge_into(merged, candidate) 【双后端合并】              │
│      → 将 camelot 表合并到 pdfplumber 表列表中                │
│      → bbox 重叠时，保留更优的表格:                           │
│        - 评分更高 (_table_score: 填充率 0.8 + 对齐率 0.2)     │
│        - 或覆盖面积 >= 5 倍 (大表替换小表)                    │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
                返回 merged: List[TableData]
```

**bbox 重叠检测** (`_bbox_overlap`)：

```
判断两个表格是否重叠（满足任一）:
  1. a 的中心点落在 b 的 bbox 内
  2. b 的中心点落在 a 的 bbox 内
  3. IoU > 0.5（交集 / 并集）
  4. y 方向重叠 > 50% 且 x 方向相邻（容差 50pt）
```

---

#### 阶段 2.4：表格后处理 (`extract_table.extract_tables`)

```
extract_tables(page, page_type, pdf_path, page_num, prev_type, prev_header)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. 调用 HybridExtractor 获取原始表格列表                      │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. _has_content(t) 过滤空表格                                 │
│      → 至少 2 个非空单元格才保留                              │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 3. 跨页续表检测                                               │
│      → td.cross_page = (prev_type == "table")                 │
│      → _is_header_repeat() 检测续表行是否与上一页表头重复     │
│      → 重复则删除该行，标记 header_repeat = True              │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 4. tables_to_markdown(td) 转为 Markdown                       │
│      → _fill_merged_cells() 填充合并单元格                    │
│      → _pad_row() 补齐列宽                                    │
│      → 输出 | col1 | col2 | ... | 格式                       │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
                返回 blocks: list[Block]
```

---

#### 阶段 2.5：进度更新

每页处理完成后：

```
progress_service.update_page_done(task_id, page_num, page_type, blocks, features)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. 创建 PageResult(page, type, blocks, features)              │
│ 2. task_store.append_page(task_id, page_result)               │
│ 3. task_store.update_progress(task_id, page_num)              │
└───────────────────────────────────────────────────────────────┘
```

**前端轮询**: 每次轮询都能拿到最新的 `progress` 和已完成的 `pages`。

---

### 阶段 3：解析完成

```
所有页面处理完毕
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. progress_service.set_metrics(task_id, ctx)                 │
│      → 保存 VLM 调用次数、成本、延迟统计                      │
│ 2. progress_service.add_cost(task_id, ctx.total_cost)         │
│ 3. progress_service.finish(task_id, status)                   │
│      → status = "completed" / "partial" / "failed"           │
│ 4. pdf_utils.remove_temp_pdf(pdf_path)                        │
│      → 删除临时 PDF 文件                                      │
└───────────────────────────────────────────────────────────────┘
```

---

### 阶段 4：查看结果与导出

#### 4.1 获取解析结果

**入口**: `GET /api/v1/tasks/{task_id}`

```
task_controller.get_task(task_id)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ task_store.get(task_id) → ParseResult                         │
│   → 包含所有页面的 blocks（text/table/image）                 │
│   → 每个 block 有 content（Markdown 格式）                    │
└───────────────────────────────────────────────────────────────┘
```

#### 4.2 导出 Markdown

**入口**: `GET /api/v1/tasks/{task_id}/export?format=markdown`

```
export_controller.export(task_id, fmt="markdown")
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ _build_markdown(result)                                       │
│   → 遍历所有页面和 blocks                                     │
│   → 表格: _find_table_title() + tables_to_markdown()          │
│   → 文本/图片: 直接输出 content                               │
│   → 跨页续表: 添加 "> （跨页续表）" 标记                     │
└───────────────────────────────────────────────────────────────┘
```

#### 4.3 导出知识库优化版

**入口**: `GET /api/v1/tasks/{task_id}/export-kb?chunk_tokens=500&overlap_tokens=50`

```
kb_export_controller.export_kb(task_id, chunk_tokens, overlap_tokens)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. _build_segments(result)                                    │
│      → 将每页的 block 转为增强文本段                          │
│      → 表格添加标题、填充合并单元格                           │
│      → 每个 segment 带有 page/type 元数据                     │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. 按 token 大小切块 + overlap 重叠                           │
│      → 每块约 500 tokens                                      │
│      → 相邻块重叠 50 tokens 保持上下文连续                    │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
                返回 {filename, total_chunks, chunks: [...]}
```

---

## 三、数据存储结构

### 3.1 内存存储 (`task_store`)

```python
_store: dict[str, ParseResult] = {
    "task_id_1": ParseResult(
        task_id="...",
        filename="example.pdf",
        status="completed",
        total_pages=10,
        progress=10,
        pages=[
            PageResult(
                page=1,
                type="table",
                blocks=[
                    Block(type="table", content="| col1 | col2 |...", table=TableData(...)),
                    Block(type="text", content="正文内容..."),
                ],
                features=PageFeatures(line_count=30, ...)
            ),
            ...
        ],
        cost_usd=0.186,
        metrics=TaskMetrics(vlm_calls=[...], total_cost=0.186)
    ),
    ...
}
```

### 3.2 持久化

- 每次状态变更都写入 `.task_store.json`
- 启动时自动加载，恢复历史任务

### 3.3 临时文件

- 上传的 PDF 保存在 `temp/{task_id}.pdf`
- 解析完成后自动删除

---

## 四、VLM 调用机制

### 4.1 调用场景

| 场景 | 触发条件 | 功能 |
|------|---------|------|
| 图片描述 | `page_type == "mixed"` | 提取并描述页面中的图片 |
| 扫描件 OCR | `page_type == "scan"` | 整页 OCR 识别 |
| 表格探测兜底 | `CLS_VLM_FALLBACK=on` 且分类不确定 | 判断 mixed 页是否含表格 |

### 4.2 调用流程

```
vlm_describe(image_bytes, metrics_ctx, model_name)
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 1. vlm_models.get_model(model_name)                           │
│      → 从 models.json 加载模型配置                            │
│      → 配置: base_url, api_key, model                         │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. _call_vlm(image_bytes, prompt, metrics_ctx, model, kind)   │
│      → 检查缓存 (VLM_RESPONSE_CACHE=on 时)                    │
│      → base64 编码图片                                        │
│      → 构造 OpenAI 兼容请求                                   │
│      → POST {base_url}/chat/completions                       │
│      → 重试机制: 最多 2 次，退避 2 秒                         │
│      → 记录指标: latency, tokens, cost                        │
└───────────────────────┬───────────────────────────────────────┘
                        │
                        ▼
                返回识别文本
```

### 4.3 真实定价表

```python
_PRICING = {
    "deepseek-v4-pro":   (0.15, 4.5, 13.5),   # cache_hit, cache_miss, output (¥/百万 tokens)
    "MiniMax-M3":        (0.42, 2.10, 8.40),
    "kimi-k2.7-code":    (1.30, 6.50, 27.00),
}
```

成本计算：缓存命中按 25% 估算，其余按缓存未命中。

---

## 五、第 24 页问题修复详解

### 5.1 问题现象

原始 PDF 第 24 页是一个三列布局的对照表：

```
┌─────────────────┬──────────────────────┬─────────────────────────┬───────┐
│ 左侧列 (x≈70)   │ 中间列 (x≈162)       │ 右侧品牌 (x≈567)        │ 分数  │
├─────────────────┼──────────────────────┼─────────────────────────┼───────┤
│                 │ Driving position     │ BMW 5, Maserati, Porsche│ 8.7   │
│                 │ Quality of ride      │ Maserati                │ 8.8   │
│                 │ Ease of entry...     │ Avatr 5                 │ 8.8   │
│ Comfort         │ Interior versatility │ Avatr 5                 │ 8.7   │
│                 │ Accessibility...     │ Land Rover              │ 8.2   │
└─────────────────┴──────────────────────┴─────────────────────────┴───────┘
```

**camelot 错误**：把 Comfort（左列）单独分成一行，Interior versatility（中列）在下一行。

### 5.2 修复方案：`_merge_fragmented_rows`

```python
def _merge_fragmented_rows(t: TableData) -> TableData:
    # 遍历每一行
    for each row:
        # 检查：当前行只有左侧列有内容，无右侧列
        if left_has and not right_has:
            # 检查：下一行有左侧+右侧列内容
            if next_right_has and next_left_has:
                # 合并：把下一行左侧内容移到当前行空列
                merge_rows()
```

**修复效果**：

```
修复前:
  Row 5: ['Comfort', '', '', '', '', '', '', '', '']
  Row 6: ['Interior versatility', '', '', '', '', '', '', 'Avatr 5', '8.7']

修复后:
  Row 5: ['Comfort', 'Interior versatility', '', '', '', '', '', 'Avatr 5', '8.7']
```

### 5.3 辅助修复：`_merge_into` 面积替换

pdfplumber 会把右侧每一行单独检测为 1×2 小表（共 21 个），需要过滤：

```python
# 替换条件
if cand_score > existing_score or (cand_area >= 5 * existing_area and cand_score >= 0.3):
    replace()
```

camelot 大表（49×9，面积大）会替换 pdfplumber 小表（1×2，面积小）。

---

## 六、API 端点汇总

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/api/v1/parse` | 上传 PDF，创建解析任务 |
| GET | `/api/v1/tasks` | 获取任务历史列表 |
| GET | `/api/v1/tasks/{task_id}` | 获取任务详情（含解析结果） |
| DELETE | `/api/v1/tasks/{task_id}` | 删除任务 |
| GET | `/api/v1/tasks/{task_id}/export?format=json\|markdown` | 导出 JSON/Markdown |
| GET | `/api/v1/tasks/{task_id}/export-kb?chunk_tokens=500&overlap_tokens=50` | 导出知识库优化版 |
| GET | `/api/v1/tasks/{task_id}/images/{page}/{index}` | 获取页面图片 |
| GET | `/api/v1/models` | 获取可用 VLM 模型列表 |

---

## 七、目录结构

```
pdf-parsing/
├── src/
│   ├── server.py                    # FastAPI 入口
│   ├── controller/                  # API 控制器
│   │   ├── parse_controller.py      # 上传解析
│   │   ├── task_controller.py       # 任务管理
│   │   ├── export_controller.py     # 导出 Markdown/JSON
│   │   ├── kb_export_controller.py  # 知识库导出
│   │   ├── image_controller.py      # 图片获取
│   │   └── models_controller.py     # 模型列表
│   ├── parser/                      # 解析核心
│   │   ├── classify.py              # 页面分类
│   │   ├── pipeline.py              # 页面调度
│   │   ├── extract_table.py         # 表格提取入口
│   │   ├── table_extractor.py       # 多后端表格提取器
│   │   ├── extract_text.py          # 文本提取
│   │   ├── mixed.py                 # 混合页处理
│   │   ├── scan.py                  # 扫描件处理
│   │   ├── formula.py               # 公式检测
│   │   └── vlm.py                   # VLM 调用
│   ├── models/
│   │   └── schemas.py               # 数据模型
│   ├── store/
│   │   ├── task_store.py            # 任务存储
│   │   └── image_cache.py           # 图片缓存
│   ├── task_manager/
│   │   ├── task_service.py          # 任务编排
│   │   └── progress_service.py      # 进度管理
│   ├── utils/
│   │   ├── env.py                   # 环境变量
│   │   ├── errors.py                # 错误定义
│   │   ├── metrics.py               # 指标统计
│   │   ├── pdf_utils.py             # PDF 工具
│   │   ├── unique_id.py             # ID 生成
│   │   ├── vlm_models.py            # 模型配置
│   │   └── column_detection.py      # 列数检测
│   └── eval/                        # 评估模块
├── frontend/                        # Vue 3 前端
├── temp/                            # 临时 PDF 存储
├── .task_store.json                 # 任务持久化
└── models.json                      # VLM 模型配置
```

---

## 八、启动与运行

### 8.1 启动后端

```bash
cd /Users/lou/ai_agent/pdf-parsing
.venv/bin/python -m uvicorn src.server:app --host 0.0.0.0 --port 8000
```

### 8.2 启动前端

```bash
cd frontend
npm run dev
```

### 8.3 环境变量配置 (.env)

```env
# VLM 配置
VLM_BASE_URL=https://your-vlm-endpoint.com/v1
VLM_API_KEY=your-api-key
VLM_MODEL=your-model-name
VLM_DEFAULT_MODEL=MiniMax-M3

# 服务器
HOST=0.0.0.0
PORT=8000

# 分类阈值
CLS_LINE_COUNT_TABLE=20
CLS_AREA_RATIO_MIN=0.15
CLS_VLM_FALLBACK=off

# 表格提取器 (hybrid / camelot / camelot-stream / pdfplumber)
TABLE_EXTRACTOR=hybrid

# VLM 响应缓存
VLM_RESPONSE_CACHE=off
```

---

## 九、常见问题与调试

### 9.1 表格检测不准确

- 调整 `CLS_LINE_COUNT_TABLE` 和 `CLS_AREA_RATIO_MIN`
- 开启 `CLS_VLM_FALLBACK=on` 启用 VLM 兜底
- 检查 `TABLE_EXTRACTOR` 是否设为 `hybrid`

### 9.2 VLM 调用失败

- 检查 `models.json` 配置是否正确
- 确认 `VLM_BASE_URL` 和 `VLM_API_KEY` 有效
- 查看后端日志 `/tmp/backend.log`

### 9.3 行错位问题（如第 24 页）

- 已通过 `_merge_fragmented_rows` 修复
- 如果仍有问题，检查 PDF 实际布局（用 `page.extract_words()` 查看坐标）

---

*文档生成时间: 2026-08-18*

# PDF Parser Demo

PDF 图文混排解析 Demo：精度优先架构（JSON = 结构化真相源，Markdown = 派生视图）+ 可实验的探究/评测平台。

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
| `VLM_MODELS_FILE` | `models.json` | 多模型注册表（用于多模型对比） |
| `VLM_DEFAULT_MODEL` | `MiniMax-M3` | 默认选中模型 |
| `MAX_FILE_MB` | `50` | 上传上限 |
| `HOST` / `PORT` | `0.0.0.0` / `8082` | 监听地址 |

### 分类阈值（`CLS_*`，#1/#3 调优）

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CLS_LINE_COUNT_TABLE` | `20` | 行数 ≥ 该值判 table |
| `CLS_TEXT_BLOCKS_MIN` | `4` | text_blocks ≥ 该值判 text |
| `CLS_LINE_COUNT_TEXT` | `10` | 行数 ≥ 该值判 text |
| `CLS_AREA_RATIO_MIN` | `0.15` | 密集线面积比 ≥ 该值判 mixed |
| `CLS_DRAWINGS_PATH_MIXED` | `200` | 矢量路径数 ≥ 该值判 mixed |
| `CLS_VLM_FALLBACK` | `off` | 分类置信度低时 VLM 兜底 |

### 探究 / 评测层

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TABLE_EXTRACTOR` | `hybrid` | 表格后端：`pdfplumber` / `camelot` / `hybrid` |
| `FORMULA_MODE` | `annotate` | 公式处理：`annotate` / `vlm` |
| `FORMULA_VLM_RESTORE` | `off` | 图片公式 VLM 还原为 LaTeX |
| `VLM_OCR_DPI` | `200` | 扫描件 OCR DPI |
| `VLM_DESC_DPI` | `200` | 图片描述 DPI |
| `VLM_RESPONSE_CACHE` | `off` | VLM 响应缓存 |
| `EVAL_SAMPLES_DIR` | `samples` | 评测样本目录 |

## 端口

- 后端：8082（`PORT`）
- 前端 dev：5173（vite proxy `/api` -> 8082）

## API

| Method | Path | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/parse` | 上传 PDF，创建解析任务（`file`, 可选 `vlm_model`） |
| `GET` | `/api/v1/tasks` | 任务列表 |
| `GET` | `/api/v1/tasks/{task_id}` | 任务详情（完整 Block + 特征 + 成本） |
| `GET` | `/api/v1/tasks/{task_id}/export` | 导出 Markdown |
| `GET` | `/api/v1/tasks/{task_id}/images/{page}/{index}` | 获取页面渲染图 |
| `GET` | `/api/v1/models` | 可用模型列表 |

## 架构（精度优先）

```
┌─────────────────────────────────────────────────────┐
│ 前端 (Vue 3 + Vite)                                  │
│   结构化视图 / Markdown 视图 / 特征 JSON / 成本面板    │
└────────────────────┬────────────────────────────────┘
                     │ /api/v1
┌────────────────────▼────────────────────────────────┐
│ FastAPI 服务层                                       │
│   parse / task / export / image / models            │
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
│   extract_text / extract_table / mixed / scan        │
│   HybridExtractor / formula / VLM                    │
└─────────────────────────────────────────────────────┘
```

### 数据模型（IR）

- 抽取层（唯一真相源）：`text` / `table`（TableData: rows + n_rows + n_cols + merged + cross_page + header_repeat）/ `image`（ImageData）+ `bbox` + `page_type`
- 呈现层（派生视图）：`content`（由结构化字段派生）
- JSON 导出 = 完整 Block（保全精度）；Markdown 导出 = `content`（派生视图，丢失合并单元格 / 坐标 / 跨页结构）

### 目录结构

```
src/
├── server.py              # FastAPI 入口
├── controller/            # REST 控制器
│   ├── parse_controller.py
│   ├── task_controller.py
│   ├── export_controller.py
│   ├── image_controller.py
│   └── models_controller.py
├── models/schemas.py      # Pydantic 数据模型
├── parser/                # 解析核心
│   ├── pipeline.py        # 页面分发
│   ├── classify.py        # 分类 + 特征提取
│   ├── extract_text.py    # 文本抽取
│   ├── extract_table.py   # 表格抽取 + 跨页合并
│   ├── table_extractor.py # pdfplumber / camelot / HybridExtractor
│   ├── mixed.py           # 图文混排页
│   ├── scan.py            # 扫描件 OCR
│   ├── formula.py         # 公式检测 / VLM 还原
│   └── vlm.py             # VLM 调用 + 真实定价
├── task_manager/          # 任务调度 / 进度
├── store/                 # 任务持久化 / 图片缓存
├── eval/                  # 端到端评测
│   ├── runner.py          # CLI 评测入口
│   ├── metrics.py         # 准确率 / 混淆矩阵 / 成本
│   └── sample_set.py      # 样本加载
└── utils/                 # 配置 / 错误 / 指标 / PDF 工具
```

## 评测

```bash
# 基础评测
uv run python -m src.eval.runner --samples-dir samples --report report.json

# 多表格后端对比
uv run python -m src.eval.runner --samples-dir samples --table-backends "pdfplumber,camelot,hybrid"

# 多模型成本/效果对比
uv run python -m src.eval.runner --samples-dir samples --compare-vlm "MiniMax-M3,deepseek-v4-pro,kimi-k2.7-code"

# 覆盖分类阈值
uv run python -m src.eval.runner --samples-dir samples --cls-overrides "CLS_LINE_COUNT_TABLE=25,CLS_AREA_RATIO_MIN=0.2"
```

## 已验证能力（10/10 ✅）

| # | 能力 | 关键结果 |
| --- | --- | --- |
| 1 | 分类阈值调优 | 5 份 PDF 共 30 页，准确率 **100%（30/30）** |
| 2 | 隐形文本层检测 | `PageFeatures` 含 `overlap_rate` / `char_density` / `font_flags` |
| 3 | 矢量图/表格/Logo 区分 | `line_count` / `area_ratio` / `orthogonality` 等特征完整 |
| 4 | 表格工具选型对比 | HybridExtractor（pdfplumber + camelot 评分选优）自适应 |
| 5 | 跨页表格合并 | `cross_page=True` + `header_repeat=True`，续表表头自动去重 |
| 6 | 多栏阅读顺序 | `columns` 检测正常 |
| 7 | VLM 成本/效果权衡 | 真实定价：MiniMax-M3 ¥0.186（最低），kimi-k2.7-code ¥0.550（最高） |
| 8 | 公式与特殊内容 | Unicode 符号检测 + 图片公式 VLM 返回 LaTeX |
| 9 | 输出格式统一 (IR) | 每 Block 含 `bbox` / `page_type` / `type` / `content` |
| 10 | 端到端评测方案 | 输出准确率 / 混淆矩阵 / 特征分布 / VLM 成本 / 多模型对比 |

详细验证数据见 [探究能力验证报告（已验证）.md](探究能力验证报告（已验证）.md)，精简版见 [探究能力验证报告（精简版）.md](探究能力验证报告（精简版）.md)。

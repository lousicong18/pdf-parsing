# PDF 图文混排解析 Demo - 后端开发任务计划（plan_backend.md）

> 依据 `code_plan.md`（**探究/评测层升级版**：§2.1 后端目录树、§3 约定适配、§4 API 契约、§5 数据模型含 PageFeatures/VlmCallMetric/TaskMetrics、§6 解析管线含 classify_features/多栏/TableExtractor 委托/跨页特征、§7 异步进度、§8 配置含 CLS_*/TABLE_EXTRACTOR/FORMULA_MODE/VLM_*/EVAL_SAMPLES_DIR、§9 边界场景、§10 联调、**§11 探究/评测层**）拆分后端开发任务。
>
> **核心架构原则（精度优先 + 探究平台，决策 4 / §5 / §7.4 / §11）**：
> - **抽取层（唯一真相源）** = 结构化字段 `text` / `table`（TableData：rows + n_rows + n_cols + merged[MergedCell] + cross_page）/ `image`（ImageData：description + image_url + ...）+ `bbox` + `page_type`，始终保留（S4）。
> - **呈现层（派生视图）** = `content`：由结构化字段派生的 markdown（text->文本 / table->markdown 表格 / image->描述）。
> - **JSON 导出** = 完整 Block（含结构化真相源 + bbox + page_type + metrics）= 保全精度（S2/S4/S5）；**Markdown 导出** = `content` 派生视图。
> - **探究层（§11）**：可配置化（CLS_*/VLM_*/TABLE_EXTRACTOR/FORMULA_MODE/EVAL_SAMPLES_DIR）+ classify 特征埋点（PageFeatures）+ 可插拔 TableExtractor + 跨页表格特征 + 多栏阅读顺序 + 公式探究 + VLM 成本埋点（TaskMetrics）+ 评测 harness（src/eval/）。
>
> **全局约定（适用于所有任务，依据 §3）**：
> - **同步方法**：所有方法用 `def`，**禁止 `async def`**（含路由 handler、`run_parse` 后台任务、VLM 调用、eval runner、store 操作；FastAPI 自动投入线程池）。
> - **模块导入**：项目根为根，统一 `import src.xxx` / `from src.xxx import yyy`；**禁止 `from . import`**。
> - **无 DB / 无 mapper / 无 @Transaction**：不创建 `yo_mysql/`、`mapper/`，代码中**不出现**任何 SQL、`@Transaction`、`conn`、`get_conn`、`release_conn`；任务存储用内存 dict，进程重启即清空。
> - **uv 依赖管理**：`pyproject.toml`；启动 `uv run python -m src.server`；eval `uv run python -m src.eval.runner`。
> - **ID 用 string**：`task_id` 为 string，由 `src/utils/unique_id.py`（uuid4 hex）生成。
> - **依赖方向**：`parser -> task_manager.progress_service`（允许回写进度）；`eval -> parser/task_manager`（允许）；反向禁止。
> - **不构建测试任务**（eval harness 是工具模块，不是测试用例）。

---

## 大功能1：项目初始化与配置

- [x] 子功能1：创建 `pyproject.toml`（uv 依赖管理），声明运行依赖 `fastapi`、`uvicorn`、`pymupdf`、`pdfplumber`、`httpx`、`python-multipart`、`pydantic`、`python-dotenv`，dev 依赖 `pytest`；配置项目元信息与 Python>=3.11。
- [x] 子功能2：创建根目录 `.env.example` 与 `.env` 模板，**包含全部探究层配置项**（§8.2）：`VLM_BASE_URL` / `VLM_API_KEY` / `VLM_MODEL` / `MAX_FILE_MB=50` / `HOST=0.0.0.0` / `PORT=8082` / 分类阈值 `CLS_LINE_COUNT_TABLE=20` / `CLS_TEXT_BLOCKS_MIN=4` / `CLS_LINE_COUNT_TEXT=10` / `CLS_AREA_RATIO_MIN=0.15` / `CLS_DRAWINGS_PATH_MIXED=200` / `TABLE_EXTRACTOR=pdfplumber` / `FORMULA_MODE=annotate` / `VLM_OCR_DPI=200` / `VLM_DESC_DPI=200` / `VLM_RESPONSE_CACHE=off` / `EVAL_SAMPLES_DIR=samples` / `VLM_MODELS_FILE=models.json` / `VLM_DEFAULT_MODEL=glm-4v`（§11.10）。
- [x] 子功能3：创建 `src/server.py` 脚手架--FastAPI app 实例 + `CORSMiddleware`（`allow_origins=["http://localhost:5173"]`，`allow_methods=["*"]`，`allow_headers=["*"]`，§10.2）+ `/api/v1` 前缀路由注册（include 四个 controller router）+ `uvicorn.run(app, host=HOST, port=PORT)` 启动（端口 8082，host/port 读 `src/utils/env.py`）。
- [x] 子功能4：创建各包 `__init__.py` 占位（`src/__init__.py`、`src/controller/__init__.py`、`src/parser/__init__.py`、`src/task_manager/__init__.py`、`src/models/__init__.py`、`src/store/__init__.py`、`src/utils/__init__.py`、**`src/eval/__init__.py`**）。
- [x] 子功能5：创建根目录 `README.md`，记录启动命令（`uv sync` / `uv run python -m src.server` / `uv run python -m src.eval.runner`）、`.env` 配置说明（含 CLS_*/TABLE_EXTRACTOR/FORMULA_MODE/VLM_*/EVAL_SAMPLES_DIR）、端口与联调信息、精度优先架构说明（json=真相源 / markdown=派生视图）、探究层能力说明。

## 大功能2：数据模型（src/models/schemas.py，精度优先架构 + 探究层特征/埋点）

- [x] 子功能1：定义类型别名 `TaskStatus`（Literal: pending/parsing/completed/partial/failed）、`PageType`（Literal: text/table/mixed/scan）、`BlockType`（Literal: text/image/table）（§5.1）。
- [x] 子功能2：定义 `MergedCell(BaseModel)` 模型--`row:int` / `col:int` / `rowspan:int=1` / `colspan:int=1`，用于记录表格合并单元格信息（S2）。
- [x] 子功能3：定义 `TableData(BaseModel)` 模型--`rows:list[list[str]]`（行列结构真相源，不扁平化）/ `n_rows:int` / `n_cols:int` / `merged:list[MergedCell]=[]`（合并单元格 S2）/ `cross_page:bool=False`（跨页续表标记 S5）。
- [x] 子功能4：定义 `ImageData(BaseModel)` 模型--`description:str`（VLM 描述）/ `image_url:str` / `mime:str="image/png"` / `width:Optional[int]=None` / `height:Optional[int]=None`。
- [x] 子功能5：**定义 `PageFeatures(BaseModel)` 模型（§11.2 探究层特征向量）**--`line_count:int` / `text_blocks_count:int` / `images_count:int` / `drawings_path_count:int` / `area_ratio:float`（线密集区面积/页面面积）/ `overlap_rate:float`（文本块 bbox 重叠率）/ `char_density:float`（字符数/文本面积）/ `font_flags:list[str]=[]`（隐形层特征字体）/ `orthogonality:float`（线条正交性 0-1）/ `columns:int=1`（栏数 §11.5）。
- [x] 子功能6：**定义 `VlmCallMetric(BaseModel)` 模型（§11.7 VLM 埋点）**--`kind:str`（image/scan）/ `model:str` / `latency_ms:int` / `tokens:int=0` / `cost_usd:float=0.0` / `retry:int=0` / `success:bool`。
- [x] 子功能7：**定义 `TaskMetrics(BaseModel)` 模型（§11.7 task 级汇总）**--`vlm_calls:list[VlmCallMetric]=[]` / `total_cost:float=0.0` / `total_latency_ms:int=0` / `by_kind:dict[str,int]={}`。
- [x] 子功能8：定义 `Block(BaseModel)` 模型（精度优先，§5.1）--`type:BlockType` / `bbox:list[float]`（[x0,y0,x1,y1]，**始终保留** S4）/ `page_type:PageType`（**始终保留** S4）/ `order:int`；抽取层结构化真相源：`text:Optional[str]=None` / `table:Optional[TableData]=None` / `image:Optional[ImageData]=None`；呈现层派生视图：`content:str`；便利字段 `image_url:Optional[str]=None`。
- [x] 子功能9：**定义 `PageResult(BaseModel)` 模型（加 features）**--`page:int` / `type:PageType` / `blocks:list[Block]=[]` / `features:Optional[PageFeatures]=None`（classify 特征向量，探究/eval，§11.2）。
- [x] 子功能10：定义 `TaskError(BaseModel)` 模型--`page:Optional[int]=None` / `message:str`。
- [x] 子功能11：**定义 `ParseResult(BaseModel)` 模型（加 metrics）**--`task_id:str` / `filename:str` / `status:TaskStatus` / `total_pages:int` / `progress:int=0` / `pages:list[PageResult]=[]` / `cost_usd:float=0.0` / `errors:list[TaskError]=[]` / `metrics:Optional[TaskMetrics]=None`（VLM 成本/耗时埋点，§11.7）/ `created_at:str` / `finished_at:Optional[str]=None`。
- [x] 子功能12：定义 `CreateTaskResponse`（task_id/filename/status/total_pages/created_at）与 `ErrorResponse`（detail/code?）模型。

## 大功能3：工具模块（src/utils/：env.py 配置读取 + unique_id.py + pdf_utils.py + metrics.py VLM 埋点）

- [x] 子功能1：`src/utils/env.py`--用 `python-dotenv` 读取 `.env`，暴露模块级常量 `VLM_BASE_URL` / `VLM_API_KEY` / `VLM_MODEL` / `MAX_FILE_MB`(默认50) / `HOST`(默认0.0.0.0) / `PORT`(默认8082)，供 `vlm.py` / `pdf_utils.py` / `server.py` 使用（§8.1）。
- [x] 子功能2：**`src/utils/env.py` 扩展分类阈值常量（§11.1/#1）**--读取并暴露 `CLS_LINE_COUNT_TABLE`(默认20) / `CLS_TEXT_BLOCKS_MIN`(默认4) / `CLS_LINE_COUNT_TEXT`(默认10) / `CLS_AREA_RATIO_MIN`(默认0.15) / `CLS_DRAWINGS_PATH_MIXED`(默认200)，供 `classify.py` 可配置阈值判定（告别硬编码）。
- [x] 子功能3：**`src/utils/env.py` 扩展探究层配置常量（§11.1/#4/#7/#8/#10）**--读取并暴露 `TABLE_EXTRACTOR`(默认pdfplumber) / `FORMULA_MODE`(默认annotate) / `VLM_OCR_DPI`(默认200) / `VLM_DESC_DPI`(默认200) / `VLM_RESPONSE_CACHE`(默认off) / `EVAL_SAMPLES_DIR`(默认samples)，供 `table_extractor.py` / `formula.py` / `vlm.py` / `scan.py` / `mixed.py` / `eval/` 使用。
- [x] 子功能4：`src/utils/unique_id.py`--`gen_task_id() -> str` 生成 task_id（uuid4 hex，string 类型）。
- [x] 子功能5：`src/utils/pdf_utils.py`--`validate_upload(file) -> None` 校验上传文件类型（必须 PDF，否则抛 INVALID_FILE_TYPE）与大小（不超过 MAX_FILE_MB，否则抛 FILE_TOO_LARGE）（U1/U2）。
- [x] 子功能6：`src/utils/pdf_utils.py`--`save_temp_pdf(file, task_id) -> str` 将上传 PDF 保存到临时路径（如 `/tmp/pdf_parse_{task_id}.pdf`），返回路径。
- [x] 子功能7：`src/utils/pdf_utils.py`--`get_page_count(pdf_path) -> int` 用 `fitz.open` 打开取 `doc.page_count`，文件损坏时抛异常（供 X1 兜底捕获）。
- [x] 子功能8：`src/utils/pdf_utils.py`--`remove_temp_pdf(pdf_path) -> None` 安全删除临时 PDF（解析完成后调用，image_cache 保留）。
- [x] 子功能9：**`src/utils/metrics.py` VLM 成本/效果埋点（§11.7/#7）**--`record_vlm_call(metrics_ctx: TaskMetrics, kind: str, model: str, latency_ms: int, tokens: int, cost_usd: float, retry: int, success: bool) -> None` 将单次调用累加进传入的 `metrics_ctx`（**显式传参，禁模块级 task 上下文**；当前串行场景安全，未来并发需 contextvars）。
- [x] 子功能10：**`src/utils/metrics.py` task 级汇总（§11.7）**--`new_task_metrics() -> TaskMetrics` 构造独立的 task metrics 对象；`get_task_metrics(metrics: TaskMetrics) -> TaskMetrics` 返回同一对象供 `run_parse` 写入 `ParseResult.metrics`。`run_parse` 持有 `metrics_ctx` 并显式传给 `vlm._call_vlm` 的 `record_vlm_call`。
- [x] 子功能11：**`src/utils/vlm_models.py` VLM 模型注册表（§11.10/#7）**--`ModelConfig{name, base_url, api_key, model}`；`load_registry(path=env.VLM_MODELS_FILE) -> dict[str, ModelConfig]` 读 `models.json`（无文件回退 `.env` 单组为默认模型）；`get_model(name: str = None) -> ModelConfig`（name 空取 `env.VLM_DEFAULT_MODEL`）；`list_models() -> list[str]` 供 API/前端下拉 + eval 对比。
- [x] 子功能12：**`src/utils/column_detection.py` 共享栏检测（§11.5/#6，修复 columns 写入职责不清）**--`column_detection(blocks: list) -> int` 按文本块 `bbox[0]` 聚类判栏数；由 `classify_features` 直接调用写准 `PageFeatures.columns`，`extract_text` / `mixed` 仅用于排序，**不再回写 features**（features 为 classify 阶段单数据源）。

## 大功能4：内存任务存储与进度回写（src/store/ + src/task_manager/progress_service.py）

- [x] 子功能1：`src/store/task_store.py`--模块级 `_store: dict[str, ParseResult] = {}` + `threading.Lock`（后台线程写、请求线程读，需线程安全）；`create(task_id, result: ParseResult)` 写入初始 pending 记录。
- [x] 子功能2：`src/store/task_store.py`--`get(task_id) -> ParseResult | None` / `update_status(task_id, status)` / `update_progress(task_id, progress)` / `append_page(task_id, page_result)` / `append_error(task_id, task_error)` / `add_cost(task_id, cost)` / `set_finished(task_id, status, finished_at)` / **`set_metrics(task_id, metrics: TaskMetrics)`**（写入 ParseResult.metrics），均加锁。
- [x] 子功能3：`src/store/image_cache.py`--模块级 `_cache: dict[str, dict[int, dict[int, bytes]]]`（task_id -> page -> index -> bytes）+ `threading.Lock`；`put(task_id, page, index, bytes)` 与 `get(task_id, page, index) -> bytes | None`。
- [x] 子功能4：`src/task_manager/progress_service.py`--`mark_parsing(task_id)` 委托 `task_store.update_status(task_id, "parsing")`（依赖方向：parser -> progress_service 允许）。
- [x] 子功能5：`src/task_manager/progress_service.py`--`update_page_done(task_id, page, page_type, blocks, features: Optional[PageFeatures]=None)` 委托 `task_store.append_page`（构造 `PageResult{page, type:page_type, blocks, features}`，**写入 PageFeatures**）+ `update_progress(page+1)`。
- [x] 子功能6：`src/task_manager/progress_service.py`--`add_error(task_id, page, msg)` / `add_cost(task_id, cost)` / `set_metrics(task_id, metrics: TaskMetrics)`（委托 task_store.set_metrics）/ `finish(task_id, status)`（写 `set_finished` + `finished_at`=当前 ISO 时间）。

## 大功能5：VLM 客户端（src/parser/vlm.py，OpenAI 兼容，同步 httpx + DPI 可配 + 响应缓存 + VlmCallMetric 记录）

- [x] 子功能1：`_call_vlm(image_bytes, prompt, model_name=None, kind="image") -> str`（内部）--**按 `model_name` 从 `vlm_models.get_model` 解析 `ModelConfig`（默认 `env.VLM_DEFAULT_MODEL`，§11.10/#7）**；base64 编码图片，构造 OpenAI `chat/completions` 载荷（`messages=[{role:user, content:[{type:text,text:prompt},{type:image_url,image_url:{url:"data:image/png;base64,..."}}]}]`），`httpx.Client(timeout=60)` POST `{cfg.base_url}/chat/completions`，Header `Authorization: Bearer {cfg.api_key}`，body `model={cfg.model}`；**kind 参数区分 image/scan 供埋点**（§11.7）。
- [x] 子功能2：**`_call_vlm` 响应缓存（§11.7/#7）**--若 `env.VLM_RESPONSE_CACHE=="on"`，按 image bytes hash 缓存响应（模块级 `_vlm_cache: dict[str, str]`），命中直接返回缓存文本避免重复调用；关闭时不缓存。
- [x] 子功能3：`_call_vlm` 重试退避（§9/X2）--遇 `httpx.TimeoutException` / HTTP 429 / 5xx -> `time.sleep(2)` 重试 1 次；仍失败抛异常，由 mixed/scan 捕获兜底；**记录 retry 次数到 VlmCallMetric**。
- [x] 子功能4：`_call_vlm` 响应解析（X3）+ **VlmCallMetric 埋点（§11.7）**--解析 `response.choices[0].message.content`；内容空/格式错抛异常；从 `response.usage` 估算 `cost_usd`（无 usage 则 0）；**每次调用（成功/失败）调 `utils/metrics.record_vlm_call(metrics_ctx, ...)` 显式传参记录** `VlmCallMetric{kind, model, latency_ms, tokens, cost_usd, retry, success}`，供 task 级汇总写入 `ParseResult.metrics`。
- [x] 子功能5：`vlm_describe(image_bytes, model_name=None) -> str`--prompt「请描述这张图片的内容…」，调 `_call_vlm(image_bytes, prompt, model_name, kind="image")` 返回描述文本。
- [x] 子功能6：`vlm_ocr(image_bytes, model_name=None) -> str`--prompt「请对这张扫描件图片进行 OCR，输出可读文字…」，调 `_call_vlm(image_bytes, prompt, model_name, kind="scan")` 返回 OCR 文本。
- [x] 子功能7：prompt 模板规范--含 JSON 示例时若用 `.format()`/f-string 需转义花括号 `{{}}`（backend agent LLM Prompt 规范）。

## 大功能6：公式探究（src/parser/formula.py，§11.6/#8）

- [x] 子功能1：**`probe_latex(page) -> dict`（§11.6）**--调用 `page.get_text("latex")` 验证 LaTeX 输出可用性与返回内容；返回 dict（如 `{"available": bool, "sample": str, "length": int}`）；记录 eval 日志供公式策略探究；Demo 不深究，仅探针式验证。
- [x] 子功能2：**`FormulaRecognizer` 抽象接口（§11.6）**--定义抽象基类 `FormulaRecognizer`，方法 `recognize(page) -> list[dict]`（返回疑似公式块标注，含 bbox + latex 片段）。
- [x] 子功能3：**`AnnotateRecognizer(FormulaRecognizer)` 默认实现（§11.6）**--轻量标注实现：检测疑似 LaTeX 碎片字符（如 `\frac`、`\sum`、`^`、`_` 等模式），标注为公式块（不深究，仅标注），`FORMULA_MODE=annotate` 时启用。
- [x] 子功能4：**`get_formula_recognizer() -> FormulaRecognizer` 工厂（§11.6）**--据 `env.FORMULA_MODE`（annotate/latex/model）返回对应 recognizer：annotate->AnnotateRecognizer；latex/model -> 预留 stub（可插专用模型）。
- [x] 子功能5：公式标注接入文本抽取--`extract_text.py` 调 `formula.get_formula_recognizer()` 委托公式处理，将疑似公式片段在对应 text Block 的 `text`/`content` 中附加标注（不改变结构化字段语义）。

## 大功能7：可插拔表格提取器（src/parser/table_extractor.py，§11.3/#4）

- [x] 子功能1：**`TableExtractor` 抽象接口（§11.3）**--定义抽象基类 `TableExtractor`，方法 `extract(page, pdf_path, page_num) -> list[TableData]`（返回结构化 TableData 列表，含 rows/n_rows/n_cols/merged/cross_page）。
- [x] 子功能2：**`PdfplumberExtractor(TableExtractor)` 默认实现（§11.3）**--`pdfplumber.open(pdf_path)` -> `pg = pdf.pages[page_num]` -> `found = pg.find_tables()`；对每个 Table：`rows = table.extract()` 得行列文本；据 `table.cells` 与行列网格比对识别合并单元格记 `MergedCell{row,col,rowspan,colspan}`；组装 `TableData{rows, n_rows, n_cols, merged, cross_page=False}`（cross_page 由 extract_table.py 外层据 prev_type 设置）。
- [x] 子功能3：**`CamelotExtractor(TableExtractor)` 可选实现（§11.3）**--基于 camelot-py 的表格提取（若依赖可用），转换 camelot 结果为 TableData；暂作为可选 stub，依赖缺失时工厂抛明确错误。
- [x] 子功能4：**`MarkerExtractor(TableExtractor)` / `MinerUExtractor(TableExtractor)` 可选 stub（§11.3）**--预留外部进程调用接口（marker/mineru），实现为 stub（占位 + 明确未实现提示），供后续接入；依赖缺失时工厂抛明确错误。
- [x] 子功能5：**`get_table_extractor() -> TableExtractor` 工厂（§11.3）**--据 `env.TABLE_EXTRACTOR`（pdfplumber/camelot/marker/mineru）返回对应 extractor 实例；默认 pdfplumber；eval 可遍历多 backend 在表格样本集对比（§11.8）。

## 大功能8：PDF 页面分类（src/parser/classify.py，classify_features 特征提取 + CLS_* 可配置阈值判定）

- [x] 子功能1：**`classify_features(page) -> PageFeatures`（§11.2/#2/#3）**--入参 `fitz.Page`；提取可观测特征向量写入 `PageFeatures`：`line_count`（drawings 中 line/rect 计数）/ `text_blocks_count`（get_text("blocks") 数）/ `images_count`（get_images() 数）/ `drawings_path_count`（get_drawings() 路径总数）/ `area_ratio`（线密集区面积/页面面积）/ `overlap_rate`（文本块 bbox 重叠率）/ `char_density`（字符数/文本面积）/ `font_flags`（隐形层特征字体列表）/ `orthogonality`（线条正交性 0-1）/ `columns`（**直接调用共享 `utils.column_detection(text_blocks)` 算准栏数**，不再先填 1 后回填）。
- [x] 子功能2：**`classify_page(page, prev_type=None) -> PageType` 主入口（改为先取 features 再按可配置阈值判定，§11.2）**--入参 `fitz.Page`；先调 `classify_features(page)` 取特征向量，再按 **`env.CLS_*` 可配置阈值** 判定（不再硬编码），返回 `PageType`；另提供 `classify_features` 供 pipeline 写入 `PageResult.features`。
- [x] 子功能3：scan 判定（含隐形文本层 §11.2/#2）--`text_blocks_count==0 and images_count>0`；**隐形文本层检测（§9 + §11.2 量化）**：`overlap_rate` 高 + `char_density` 异常 + `font_flags` 非空 -> 量化判 `scan`（文本块坐标异常密集/重叠且图片为主）。
- [x] 子功能4：table 判定（含矢量 Logo 面积过滤 §11.2/#3）--`line_count > env.CLS_LINE_COUNT_TABLE and text_blocks_count >= env.CLS_TEXT_BLOCKS_MIN` **加面积过滤**：要求 `area_ratio >= env.CLS_AREA_RATIO_MIN`（线密集区占页面面积达阈值），过滤小 Logo；**联合 orthogonality**（表格线正交、Logo/插图路径杂乱）辅助判定。
- [x] 子功能5：mixed 判定（含矢量图 §11.2/#3）--`images_count>0 and text_blocks_count>0`；**矢量图情形（§9）**：`get_images()` 空 but `drawings_path_count > env.CLS_DRAWINGS_PATH_MIXED`（路径极多）-> 判 `mixed`。
- [x] 子功能6：text 判定与跨页表格上下文（§9）--`text_blocks_count>0 and images_count==0 and line_count<env.CLS_LINE_COUNT_TEXT` 判 `text`；若 `prev_type == "table"`，当前页偏向按 `table` 处理；兜底返回 `mixed`。

## 大功能9：纯文本抽取（src/parser/extract_text.py，get_text("dict") 逐块 + 多栏检测栏内y/栏间x + 公式 formula.py 委托）

- [x] 子功能1：`extract_text(page, page_type) -> list[Block]` 主入口（**改为返回 list[Block]，不用 get_text("markdown")**）--`page.get_text("dict")` 遍历 `dict["blocks"]`，对每个文本块（`block["type"]==0`）拼接其 `lines[].spans[].text` 得文本，取 `block["bbox"]` 作为该块坐标（§6.2 extract_text.py）。
- [x] 子功能2：组装 text Block（精度优先）--对每个文本块组装 `Block{type:"text", bbox=block["bbox"], page_type=page_type, order=<待排序>, text=<拼接文本>, content=<拼接文本>}`；`content` 为派生视图 = `text`（决策 4：markdown 须从结构化真相源派生，避免双表示不一致）。
- [x] 子功能3：**多栏阅读顺序检测（§11.5/#6）**--排序前先调用共享 `utils.column_detection(blocks)` 栏检测；单栏：按 y 坐标（`bbox[1]`）排序；**多栏：栏内按 y 排序，栏间按 x 排序，左->右**；**栏数不写入 `PageFeatures`**（features.columns 已在 classify 阶段由共享函数算准，extract_text 仅排序用，避免"已返回对象无法回写"歧义）。
- [x] 子功能4：阅读顺序排序设置 order--收集所有 text Block 后按多栏规则排序，依序设置 `order`（0,1,2,...）；多段文本产出多个 text Block，**每个均带 bbox + page_type**（S4）。
- [x] 子功能5：**公式标注委托 formula.py（§11.6/#8）**--调 `formula.get_formula_recognizer()` 委托公式处理（据 `env.FORMULA_MODE`），将疑似 LaTeX 碎片在对应 text Block 的 `text`/`content` 中附加标注（不改变结构化字段语义，Demo 仅标注）。
- [x] 子功能6：空页兜底--若 `get_text("dict")` 无文本块，返回空 `list[Block]`（由上层 dispatch_page / progress_service 处理空页）。

## 大功能10：表格提取（src/parser/extract_table.py，委托 TableExtractor + 跨页特征表头相似度/列对齐，TableData 为真相源）

- [x] 子功能1：**`extract_tables(page, page_type, pdf_path, page_num, prev_type=None) -> list[Block]` 主入口（改为委托 TableExtractor，§11.3/#4）**--调 `table_extractor.get_table_extractor()` 取当前 extractor（据 `env.TABLE_EXTRACTOR`），委托 `extractor.extract(page, pdf_path, page_num)` 得 `list[TableData]`（§6.2 extract_table.py）。
- [x] 子功能2：跨页续表标注（S5）--对每个 TableData：`cross_page = (prev_type == "table")`；若 `cross_page=True`，在 `content` 前置 "> （跨页续表）" 标注（best-effort 标注，不做跨页 in-place 行合并以避免污染已回写上页结果）。
- [x] 子功能3：**跨页表格特征记录（§11.4/#5）**--`prev_type=="table"` 时额外计算并记录：**表头相似度**（当前表首行与上页末表首行 token 重合率）、**列数对齐**（n_cols 是否一致），写入 eval 日志（供合并策略探究，Demo 不做 in-place 行合并但暴露合并可行性信号）。
- [x] 子功能4：组装 table Block--`content = tables_to_markdown(TableData)`（派生视图）；`bbox` 取 `table.bbox`（由 extractor 返回或回查 pdfplumber Table.bbox）；组装 `Block{type:"table", bbox, page_type, order=<按表顺序>, table=TableData, content}`，每表一个 Block（S4：带 bbox + page_type）。
- [x] 子功能5：`tables_to_markdown(table: TableData) -> str`（**改为接收 TableData，派生视图**）--由 `TableData.rows` 渲染 Markdown 表格（含表头分隔行 `|---|`）；合并单元格信息在 md 中退化为普通表格（精度丢失由 JSON 导出保全）；跨页时前置 "> （跨页续表）"；多表用分隔符拼接。
- [x] 子功能6：无表格兜底--若 extractor 返回空，返回空 `list[Block]`（由上层处理）。

## 大功能11：图文混排解析（src/parser/mixed.py，text_blocks + image_blocks 多栏排序，均带 bbox + page_type）

- [x] 子功能1：`extract_and_describe_images(page, task_id, page_num, doc) -> list[Block]`--遍历 `page.get_images(full=True)` 取 `xref`，`image_bytes = doc.extract_image(xref)["image"]`；bbox 通过 `page.get_image_bbox(img)` / `page.get_image_rects(xref)` 取真实矩形（附录 B.3）。
- [x] 子功能2：`extract_and_describe_images` 描述与缓存（精度优先）--调 `vlm.vlm_describe(image_bytes)`；`image_cache.put(task_id, page_num, index, image_bytes)`；组装 `Block{type:"image", bbox, page_type:"mixed", order=<待排序>, image=ImageData{description:desc, image_url:f"/api/v1/tasks/{task_id}/images/{page_num}/{index}"}, content:desc, image_url:f"/api/v1/tasks/{task_id}/images/{page_num}/{index}"}`（image 为结构化真相源，content 为派生视图，S4：带 bbox + page_type）。
- [x] 子功能3：`extract_and_describe_images` X2 兜底（§9/X2）--VLM 失败 -> `Block{type:"image", bbox, page_type:"mixed", image=ImageData{description:"图片未识别（VLM 调用失败）", image_url:...}, content:"图片未识别（VLM 调用失败）", image_url:...}` + `progress_service.add_error(task_id, page_num, "VLM timeout/failed")`，继续处理其余图片。
- [x] 子功能4：`process_mixed_page(page, task_id, page_num, doc) -> list[Block]`--`text_blocks = extract_text(page, "mixed")`（每段文本带 bbox + page_type，S4）；`image_blocks = extract_and_describe_images(...)`（每个图片带 bbox + page_type）；合并 text_blocks + image_blocks。
- [x] 子功能5：**多栏阅读顺序排序（§11.5/#6）**--合并后调用共享 `utils.column_detection` 栏检测，按多栏规则排序（栏内 y + 栏间 x），设置 `order`（阅读顺序拼接，§6.2 mixed.py）。

## 大功能12：扫描件 OCR（src/parser/scan.py，DPI 可配）

- [x] 子功能1：`process_scan_page(page, task_id, page_num) -> list[Block]`--`pix = page.get_pixmap(dpi=env.VLM_OCR_DPI)`（**DPI 可配，§11.7/#7**），`image_bytes = pix.tobytes("png")`（附录 B.4）。
- [x] 子功能2：`process_scan_page` OCR（精度优先）--调 `vlm.vlm_ocr(image_bytes)`；返回 `[Block{type:"text", bbox:[0,0,page.rect.width,page.rect.height], page_type:"scan", order:0, text:<OCR文本>, content:<OCR文本>}]`（text 为结构化真相源，content 为派生视图，S4：带 bbox + page_type）；scan 页不产生 `image_url`（结果为文本，非图片块）。
- [x] 子功能3：`process_scan_page` X2 兜底--VLM 失败 -> `Block{type:"text", bbox:[...], page_type:"scan", order:0, text:"扫描件未识别（VLM 调用失败）", content:"扫描件未识别（VLM 调用失败）"}` + `progress_service.add_error(...)`，status 置 partial（§6.2 scan.py）。

## 大功能13：解析管线分派（src/parser/pipeline.py，dispatch_page 带 prev_type，所有 block 带 bbox + page_type，写 PageResult.features）

- [x] 子功能1：`dispatch_page(page, page_type, task_id, page_num, doc, prev_type=None) -> tuple[list[Block], PageFeatures]` 主入口（**与 code_plan.md 统一：返回 tuple**）--调 `classify.classify_features(page)` 取 `features`（含已算准的 `columns`）；按 `page_type` 分派（附录 B.4 路由）；所有分支返回的 Block 均**带 bbox + page_type**（S4）；`prev_type` 用于跨页表格标注（S5）；返回 `(blocks, features)` 供 `progress_service.update_page_done` 写入 `PageResult.features`（§11.2）。
- [x] 子功能2：text 分支--返回 `extract_text(page, "text")`（已为 list[Block]，每个带 bbox + page_type + text + content）。
- [x] 子功能3：table 分支--返回 `extract_table.extract_tables(page, "table", doc.name, page_num, prev_type)`（每表一个 Block，带 TableData + bbox + page_type；跨页标注由 extract_table 据 prev_type 处理）。
- [x] 子功能4：mixed 分支--调 `mixed.process_mixed_page(page, task_id, page_num, doc)`。
- [x] 子功能5：scan 分支--调 `scan.process_scan_page(page, task_id, page_num)`。

## 大功能14：异步任务调度（src/task_manager/task_service.py，run_parse 传 prev_type + 收集 metrics）

- [x] 子功能1：`create_task(file, vlm_model=None) -> (CreateTaskResponse, pdf_path)`--`pdf_utils.validate_upload` -> `save_temp_pdf` -> `get_page_count` -> `unique_id.gen_task_id` -> `task_store.create(task_id, ParseResult(status=pending, ...))` -> 返回 `CreateTaskResponse` 与 pdf_path（§4.1 行为）。
- [x] 子功能2：`run_parse(task_id, pdf_path)` 主循环（同步，BackgroundTask 线程池执行，§7.1）--`progress_service.mark_parsing` -> `metrics_ctx = utils.metrics.new_task_metrics()` -> `doc = fitz.open(pdf_path)`（懒加载）-> `prev_type = None` -> `for page_num, page in enumerate(doc): page_type = classify.classify_page(page, prev_type); blocks, features = pipeline.dispatch_page(page, page_type, task_id, page_num, doc, prev_type); progress_service.update_page_done(task_id, page_num+1, page_type, blocks, features); prev_type = page_type`（**传递 prev_type 给 classify_page 与 dispatch_page + 写入 features**，§6.1）。`metrics_ctx` 显式传给 `vlm._call_vlm` 的 `record_vlm_call`，不依赖模块级上下文。
- [x] 子功能3：**`run_parse` 收集 metrics（§11.7）**--主循环结束后调 `progress_service.set_metrics(task_id, metrics_ctx)` 将 VLM 成本/耗时汇总写入 `ParseResult.metrics`（`metrics_ctx` 全程显式持有，无需 `get_task_metrics` 快照）。
- [x] 子功能4：`run_parse` X1 兜底（§9/X1）--`fitz.open` 失败（文件损坏/无法打开）-> `progress_service.add_error(task_id, None, "文件损坏...")` + `progress_service.finish(task_id, "failed")`。
- [x] 子功能5：`run_parse` 终态拼装（§4.5）--全部页处理完毕后按 errors 拼装：无 errors -> `completed`；存在页/块失败（errors 非空，X2/X3）-> `partial`；致命错误 -> `failed`；调 `progress_service.finish(task_id, status)`；解析后 `pdf_utils.remove_temp_pdf(pdf_path)`（image_cache 保留供 F10）。

## 大功能15：API 接口层（src/controller/，export json 真相源/markdown 派生视图 + 返回 metrics）

- [x] 子功能1：`parse_controller.py`--`POST /api/v1/parse`（`multipart/form-data`：`file` 必填 + `vlm_model` 可选），调 `task_service.create_task` 得 `(response, pdf_path)`，再 `background_tasks.add_task(task_service.run_parse, response.task_id, pdf_path)`，立即返回 `CreateTaskResponse`；400 `INVALID_FILE_TYPE` / `FILE_TOO_LARGE`（§4.1）。
- [x] 子功能2：`task_controller.py`--`GET /api/v1/tasks/{task_id}`，从 `task_store.get` 取 `ParseResult` 返回（含完整 Block 结构化真相源 text/table/image + bbox + page_type + **PageResult.features** + **ParseResult.metrics**）；不存在 -> 404 `TASK_NOT_FOUND`（§4.2）。
- [x] 子功能3：`export_controller.py` `format=json`（**保全精度，§4.3 决策 4**）--校验 format（非法 400 `INVALID_FORMAT`）、任务存在（404）、任务终态（pending/parsing 不可导出 409 `TASK_NOT_READY`）；`json` 导出直接序列化完整 `ParseResult`（含每个 Block 的结构化真相源 `text` / `table`（TableData：rows + n_rows + n_cols + merged + cross_page）/ `image`（ImageData）+ `bbox` + `page_type` + **PageResult.features** + **ParseResult.metrics**），`Content-Type: application/json`，`Content-Disposition: attachment; filename="<task_id>.json"`。
- [x] 子功能4：`export_controller.py` `format=markdown`（**派生视图，§4.3 决策 4**）--导出各 Block 的 `content`（派生视图）按页拼接（页面标题 `## 第 N 页 · 类型：xxx` + 块 content）；`Content-Type: text/markdown`，`Content-Disposition: attachment; filename="<task_id>.md"`；markdown 丢失合并单元格 / 坐标 / 跨页结构（精度由 json 保全）。
- [x] 子功能5：`image_controller.py`--`GET /api/v1/tasks/{task_id}/images/{page}/{index}`，从 `image_cache.get` 取 bytes，`Response(content=bytes, media_type="image/png")` 返回；不存在 -> 404 `IMAGE_NOT_FOUND`（§4.4/F10）。
- [x] 子功能6：统一错误信封--自定义异常处理器返回 `ErrorResponse{detail, code}`（§4.6），覆盖上述错误码与 500 兜底。
- [x] 子功能7：导出内容拼装辅助函数--`export_controller` 内 `_build_markdown(result: ParseResult) -> str`（按页/块顺序拼接 content 派生视图）与 `_build_json(result: ParseResult) -> str`（`result.model_dump_json()` 序列化完整结构化真相源 + features + metrics）。
- [x] 子功能8：**`models_controller.py` `GET /api/v1/models`（§4.7/§11.10/#7）**--从 `vlm_models.list_models()` 返回 `{"models": [...], "default": env.VLM_DEFAULT_MODEL}`，供前端模型下拉 + eval 对比选择；无注册表返回 `.env` 单模型。

## 大功能16：边界场景处理（§9，分布实现于各模块，此处为 hardening 任务清单）

- [x] 子功能1：**跨页表格记忆与标注（S5，§9/§11.4）**--`classify_page` 接收 `prev_type`，上一页为 `table` 则当前页偏向 `table`；`task_service.run_parse` 循环中传递 `prev_type` 给 `classify_page` 与 `dispatch_page`；`extract_table.extract_tables` 据 `prev_type` 设 `cross_page=True` 并在 `content` 标注"（跨页续表）"；**额外记录表头相似度 + 列对齐特征到 eval 日志**（§11.4/#5）。
- [x] 子功能2：**多栏阅读顺序（#6，§9/§11.5）**--`extract_text.py` 与 `mixed.py` 排序前先栏检测（`bbox[0]` 聚类判栏数）；单栏按 y 排序，多栏栏内按 y + 栏间按 x；栏数写入 `PageFeatures.columns`；多栏页标注（暴露边界，不深解复杂版式）。
- [x] 子功能3：隐形文本层检测（§9/§11.2/#2）--在 `classify.py` `classify_page` 的 scan 判定中实现：检测 `get_text("blocks")` 文本块坐标异常密集/重叠（`overlap_rate` 高 + `char_density` 异常 + `font_flags` 非空）且图片为主 -> 判 `scan`。
- [x] 子功能4：矢量 Logo 面积过滤（§9/§11.2/#3）--在 `classify.py` table 判定中实现：`line_count>CLS_LINE_COUNT_TABLE and text_blocks>=CLS_TEXT_BLOCKS_MIN` 之外，计算 `area_ratio`（线密集区占页面面积比例）过滤小 Logo + `orthogonality` 辅助。
- [x] 子功能5：矢量图判定（§9/§11.2/#3）--在 `classify.py` mixed 判定中实现：`get_images()` 空 but `drawings_path_count > CLS_DRAWINGS_PATH_MIXED`（路径极多）-> 判 `mixed`。
- [x] 子功能6：公式标注（§9/§11.6/#8）--`extract_text.py` 委托 `formula.py` 实现轻量后处理（`FORMULA_MODE=annotate`），检测疑似 LaTeX 碎片字符并标注为公式块（Demo 仅标注）。
- [x] 子功能7：VLM 兜底（§9/X2/X3）--`vlm.py` `_call_vlm` 重试 1 次 + 退避（`sleep(2)`）+ 响应缓存（`VLM_RESPONSE_CACHE`）+ VlmCallMetric 埋点；`mixed.py` / `scan.py` 捕获 VLM 异常按 X2/X3 记 error 跳过该块，status 置 partial。
- [x] 子功能8：超大 PDF 流式（§9）--`task_service.run_parse` 用 `fitz.open` 懒加载，逐页 `get_pixmap` 按需渲染，**不一次性载入全部位图**；前端进度条逐页递增。

## 大功能17：裁剪图缓存与回传（image_cache，§10.3）

- [x] 子功能1：`src/store/image_cache.py` `put` / `get` 线程安全实现（task_id/page/index -> bytes，见大功能4子功能3，此处确认作为 F10/O2 回传基础）。
- [x] 子功能2：`src/parser/mixed.py` `extract_and_describe_images` 抽取每张图片 bytes 时同步 `image_cache.put(task_id, page_num, index, bytes)` 缓存裁剪图原图（§10.3）。
- [x] 子功能3：image Block 的 `image_url` 拼装--`f"/api/v1/tasks/{task_id}/images/{page_num}/{index}"`（同时写入 `Block.image_url` 便利字段与 `Block.image.image_url` 结构化真相源字段），供前端 `<img :src>` 经 proxy 命中 `image_controller`（§10.3）。
- [x] 子功能4：`src/controller/image_controller.py` 从 `image_cache.get` 取 bytes 返回 `Response(content=bytes, media_type="image/png")`；不存在 -> 404 `IMAGE_NOT_FOUND`（§10.3，见大功能15子功能5）。
- [x] 子功能5：scan 页不缓存整页渲染图--`src/parser/scan.py` 结果为文本块（type=text），无 `image_url`，不写入 `image_cache`（§10.3）。

## 大功能18：评测/探究层（src/eval/，§11.8/#10，支撑 #1/#2/#3/#4/#7）

- [x] 子功能1：**`src/eval/sample_set.py` 标注集加载（§11.8/#10）**--`load_sample_set(samples_dir: str = None) -> list[Sample]` 加载标注集；约定 `samples/<name>.pdf` + `samples/<name>.label.json`（每页期望 type、可选期望 blocks）；默认目录取 `env.EVAL_SAMPLES_DIR`；定义 `Sample(BaseModel)`（pdf_path/label_path/expected_types/expected_blocks）。
- [x] 子功能2：**`src/eval/runner.py` CLI 入口（§11.8/#10）**--`main()` 解析 CLI 参数（`--samples-dir` 默认 env、`--report` 默认 report.json、`--table-backends` 可选多 backend 对比、`--compare-vlm` 可选多 VLM 模型对比（§11.10）、`--cls-overrides` 可选阈值覆盖）；遍历样本集调 `task_manager.task_service.run_parse` 收集结果 + features + metrics；写入 report。
- [x] 子功能3：**`src/eval/runner.py` CLI 命令**--支持 `uv run python -m src.eval.runner --samples-dir samples --report report.json`（§11.8）；支持 `--table-backends pdfplumber,camelot` 遍历多 backend 跑表格样本（§11.3/#4 对比）。
- [x] 子功能4：**`src/eval/metrics.py` 分类准确率与混淆矩阵（§11.8/#1/#10）**--`classification_accuracy(results) -> dict` 计算总体准确率 + 各类型 P/R/F1；`confusion_matrix(results) -> list[list[int]]` 生成 text/table/mixed/scan 混淆矩阵。
- [x] 子功能5：**`src/eval/metrics.py` 特征分布（§11.8/#2/#3）**--`feature_distribution(results) -> dict` 按 PageType 聚合 `PageFeatures`，输出可分析特征向量表（line_count/area_ratio/overlap_rate/char_density/orthogonality/drawings_path_count/columns 各类型统计）。
- [x] 子功能6：**`src/eval/metrics.py` 表格 backend 对比（§11.8/#4）**--`table_backend_compare(results_by_backend) -> dict` 同表格样本跑多 backend，对比行列准确率/合并单元格召回/耗时（基于 TableData.rows/n_rows/n_cols/merged 与期望比对）。
- [x] 子功能7：**`src/eval/metrics.py` VLM 成本/耗时聚合（§11.8/#7）**--`vlm_cost_aggregate(results) -> dict` 聚合 `ParseResult.metrics`（TaskMetrics：total_cost/total_latency_ms/by_kind），按 image/scan 分类统计。
- [x] 子功能8：**`src/eval/metrics.py` 输出 diff（§11.8/#10）**--`output_diff(actual_blocks, expected_blocks) -> list[DiffEntry]` 结构化 Block vs 期望 blocks 比对（文本相似度、表格单元格匹配），输出 badcase diff 列表。
- [x] 子功能9：**`src/eval/metrics.py` report 生成（§11.8/#10）**--`build_report(all_metrics) -> dict` 汇总为 `report.json` 结构（准确率/混淆矩阵/特征分布/表格对比/VLM 成本/diff/badcase）；`render_report_md(report: dict) -> str` 渲染可读 `report.md`（混淆矩阵表格、特征分布表、badcase 列表）。
- [x] 子功能10：**`src/eval/runner.py` 输出 report.json + report.md（§11.8/#10）**--运行完毕写 `report.json`（结构化）+ `report.md`（可读）；支持回归：改 CLS_* 阈值/换 TABLE_EXTRACTOR backend 后重跑对比。
- [x] 子功能11：**`src/eval/metrics.py` VLM 模型对比（§11.10/#7）**--`vlm_model_compare(results_by_model) -> dict` 对同一标注样本集多模型（`--compare-vlm glm-4v,qwen-vl-max`）跑结果，per model 输出：mixed 图片描述与期望相似度、scan OCR 与期望文本相似度、cost_usd、latency_ms、tokens、调用数；report 加「VLM 模型对比」章节。

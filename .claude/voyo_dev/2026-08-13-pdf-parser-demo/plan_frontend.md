# PDF 图文混排解析 Demo - 前端开发任务计划（plan_frontend.md）

> 基于**更新后**的 `code_plan.md`（精度优先架构：§2.2 前端目录树、§4 API 契约、§4.3 导出双格式、§5.2 TS interface 含 MergedCell/TableData/ImageData/Block 带 bbox+page_type+text?/table?/image?+content、§6 解析管线所有 block 带 bbox+page_type、§7.2 前端轮询、§10 联调；**新增 §11 探究/评测层**：§5.1/§5.2 新增 PageFeatures/VlmCallMetric/TaskMetrics，PageResult.features、ParseResult.metrics；§11.9 前端探究面板）与 `spec.md`（§6.1 表格按结构化渲染保留合并单元格/导出双格式、§7.4 S2/S4/S5 + 精度总约束、§11 研发探究能力）拆分前端开发任务。
>
> 架构核心：**抽取层（结构化真相源）= `text?`/`table?`/`image?` + `bbox` + `page_type`**，**呈现层（派生视图）= `content`（markdown）**。前端渲染：表格块按 `block.table` 结构化渲染为 HTML table（保留 `merged` 合并单元格 colspan/rowspan），文本块渲染 `block.content`（markdown），图片块缩略图 + `block.image.description` + bbox 标注；可展示 bbox/page_type。导出：JSON = 结构化真相源（含 metrics，保全精度），Markdown = 派生视图。
>
> 探究层核心：每页 `PageResult.features`（line_count/area_ratio/columns 等特征向量）+ 任务级 `ParseResult.metrics`（TaskMetrics：VLM 调用明细与成本汇总）。前端新增「探究面板」：PageCard 内展示关键特征 + VLM 成本、「查看 PageFeatures JSON」弹层、TaskMetrics 汇总展示；导出 JSON 含 metrics。
>
> 技术约定：Vue 3 Composition API + TypeScript、Element Plus、Pinia、vue-router、axios、markdown-it；样式优先使用 `style/variables.scss` + `common.scss` 公共样式，禁止组件私有样式（极特殊除外）；请求统一走 `services/` 层；关键交互节点加 `data-test` 属性。不构建测试任务。

---

## 大功能1：项目初始化与基础装配

- [x] 子功能1：脚手架初始化与依赖装配
  - 创建 `frontend/package.json`，声明运行依赖：`vue`、`element-plus`、`pinia`、`vue-router`、`axios`、`markdown-it`；dev 依赖：`vite`、`@vitejs/plugin-vue`、`typescript`、`vue-tsc`、`sass`、`@types/markdown-it`、`@types/node`。
  - 配置 `scripts`：`dev`（vite）、`build`（vue-tsc + vite build）、`preview`（vite preview）。
  - 端口约定：dev server 5173。

- [x] 子功能2：Vite 构建配置
  - 创建 `frontend/vite.config.ts`：注册 `@vitejs/plugin-vue`；`server.port = 5173`；配置 `server.proxy`，将 `/api` 代理至 `http://localhost:8082`（`changeOrigin: true`），与后端 §10.1 对齐；配置 `resolve.alias` `@` -> `src`；CSS 预处理器全局注入 `style/variables.scss`（`additionalData`），使所有组件可直接使用 SCSS 变量。

- [x] 子功能3：TypeScript 配置
  - 创建 `frontend/tsconfig.json`（及 `tsconfig.node.json`）：`target` ESNext、`module` ESNext、`moduleResolution` bundler；开启 `strict`、`jsx` preserve、`paths` 映射 `@/*` -> `src/*`；`include` src、vite.config.ts。

- [x] 子功能4：入口 HTML
  - 创建 `frontend/index.html`：`<div id="app">` 挂载点、引入 `/src/main.ts`、设置 `<title>` 为「PDF 图文混排解析」、lang zh-CN。

- [x] 子功能5：公共样式 variables.scss
  - 创建 `frontend/src/style/variables.scss`：定义颜色变量（`$color-primary:#409eff` / success / warning / danger / info / `$color-background:#ffffff` / `$color-background-secondary:rgb(250,250,250)` / `$color-text` / `$color-text-secondary` / `$color-text-placeholder` / `$color-border:#e4e7ed` / `$color-border-light` / `$color-border-lighter` / `$color-divider`）、阴影（`$shadow-card`）、尺寸（`$aside-width` / `$header-height` / `$border-radius` / `$border-radius-sm` / `$border-radius-lg`）、间距（`$spacing-xs/sm/md/lg/xl`）；Element Plus CSS 变量覆盖（`:root { --el-color-primary; --el-border-radius-base }`）。对齐 frontend agent 样式规范。

- [x] 子功能6：公共样式 common.scss
  - 创建 `frontend/src/style/common.scss`：先 `@use 'variables' as *;`，再定义公共类：`.page`（页面容器）、`.page-title`（页面标题）、`.card`（通用卡片：box-shadow + border + radius + 白底）、`.toolbar`（顶部工具栏）、`.filter-bar`、`.empty-state`（空状态）、`.upload-zone`（文件上传区）、`.action-bar`（按钮组）、`.detail-grid`（详情网格）、`.el-table-wrapper`（表格容器 border + radius）；后续随组件需要持续追加（如 `.status-bar`、`.page-card`、`.block-item`、`.block-meta`、`.struct-table`、`.features-bar`、`.metrics-panel`、`.json-viewer` 等）。所有值引用 variables.scss 变量。

- [x] 子功能7：main.ts 入口装配
  - 创建 `frontend/src/main.ts`：`createApp(App)`；注册 `ElementPlus`（含样式 `element-plus/dist/index.css`）、`Pinia`、`Router`；全局导入 `style/common.scss`；挂载 `#app`。可选注册 Element Plus 中文 locale。

---

## 大功能2：类型定义（精度优先架构 + 探究层特征/指标）

- [x] 子功能1：基础枚举与 MergedCell / TableData / ImageData interface（对齐后端 §5.1/§5.2）
  - 创建 `frontend/src/types/index.ts`：导出 `TaskStatus = 'pending'|'parsing'|'completed'|'partial'|'failed'`、`PageType = 'text'|'table'|'mixed'|'scan'`、`BlockType = 'text'|'image'|'table'`；导出 `interface MergedCell { row:number; col:number; rowspan:number; colspan:number }`（S2 合并单元格真相源）；导出 `interface TableData { rows:string[][]; n_rows:number; n_cols:number; merged:MergedCell[]; cross_page:boolean }`（行列结构 + 合并信息 + 跨页标记 S5）；导出 `interface ImageData { description:string; image_url:string; mime:string; width?:number; height?:number }`（VLM 描述真相源）。

- [x] 子功能2：探究层特征 PageFeatures / VlmCallMetric / TaskMetrics interface（对齐后端 §5.1/§11.2/§11.7）
  - 在 `frontend/src/types/index.ts` 续写探究层类型：
    - `interface PageFeatures { line_count:number; text_blocks_count:number; images_count:number; drawings_path_count:number; area_ratio:number; overlap_rate:number; char_density:number; font_flags:string[]; orthogonality:number; columns:number }`--classify 特征向量（§11.2），`area_ratio` 线密集区/页面面积、`overlap_rate` 文本块 bbox 重叠率（隐形层 #2）、`char_density` 字符/面积、`font_flags` 隐形层特征字体、`orthogonality` 线条正交性 0-1（矢量图/表格/Logo 区分 #3）、`columns` 栏数（多栏 §11.5）。
    - `interface VlmCallMetric { kind:string; model:string; latency_ms:number; tokens:number; cost_usd:number; retry:number; success:boolean }`--单次 VLM 调用埋点（§11.7），`kind` 为 `image`/`scan`。
    - `interface TaskMetrics { vlm_calls:VlmCallMetric[]; total_cost:number; total_latency_ms:number; by_kind:Record<string, number> }`--任务级 VLM 成本/耗时汇总（§11.7），`by_kind` 按 image/scan 统计调用次数。

- [x] 子功能3：Block / PageResult / ParseResult interface（抽取层 + 呈现层双字段 + 探究层挂载点）
  - 在 `frontend/src/types/index.ts` 续写：导出 `interface Block { type:BlockType; bbox:[number,number,number,number]; page_type:PageType; order:number; text?:string; table?:TableData; image?:ImageData; content:string; image_url?:string }`--其中 `bbox`+`page_type` 始终保留（S4），`text?`/`table?`/`image?` 为**抽取层结构化真相源**（按 type 取用），`content` 为**呈现层 markdown 派生视图**，`image_url?` 为便利字段=`image.image_url`；导出 `interface PageResult { page:number; type:PageType; blocks:Block[]; features?:PageFeatures }`--`features` 为该页 classify 特征向量（探究层 §11.2）；导出 `interface TaskError { page?:number; message:string }`；导出 `interface ParseResult { task_id:string; filename:string; status:TaskStatus; total_pages:number; progress:number; pages:PageResult[]; cost_usd?:number; errors:TaskError[]; metrics?:TaskMetrics; created_at:string; finished_at?:string }`--`metrics` 为任务级 VLM 成本/耗时汇总（探究层 §11.7），导出 JSON 须含此字段；导出 `interface CreateTaskResponse { task_id:string; filename:string; status:TaskStatus; total_pages:number; created_at:string }`；导出 `ExportFormat = 'markdown'|'json'` 供导出使用。字段与后端 `schemas.py` 一一对应，避免前后端模型漂移。

---

## 大功能3：API 服务层

- [x] 子功能1：axios 实例与拦截器（`services/request.ts`）
  - 创建 `frontend/src/services/request.ts`：`axios.create({ baseURL: '/api/v1', timeout: 30000 })`；响应拦截器统一解析错误信封（§4.6 `{ detail, code }`）：非 2xx 时提取 `error.response.data.detail` 与 `code`，通过 `ElMessage.error` 展示可读信息并 `reject`；导出封装后的实例。请求拦截器可预留 token 注入位（Demo 无鉴权，留空）。

- [x] 子功能2：解析任务 API 封装（`services/parse.ts`）
  - 创建 `frontend/src/services/parse.ts`，基于 `request.ts` 实现：
    - `createParseTask(file: File, vlmModel?: string): Promise<CreateTaskResponse>` - `POST /parse`，`multipart/form-data`，表单字段 `file` + 可选 `vlm_model`（§4.1）。
    - `getTask(taskId: string): Promise<ParseResult>` - `GET /tasks/{task_id}`，返回完整 `ParseResult`（§4.2），含每个 Block 的 `bbox`+`page_type`+结构化真相源 `text?`/`table?`/`image?`+派生 `content`，以及每页 `features?` 与任务级 `metrics?`。
    - `exportTask(taskId: string, format: ExportFormat): Promise<Blob>` - `GET /tasks/{task_id}/export?format=`，`responseType: 'blob'`，返回二进制供下载（§4.3：json=结构化真相源含 metrics 保全精度 / markdown=派生视图，§10.4、§11.9 导出含 metrics）。
    - `imageUrl(taskId: string, page: number, index: number): string` - 纯拼接函数，返回 `/api/v1/tasks/{task_id}/images/{page}/{index}`，供 `<img :src>` 直接使用（§4.4、§10.3）。
    - `getModels(): Promise<{ models: string[]; default: string }>` - `GET /models`，返回可用 VLM 模型列表 + 默认模型，供上传区模型下拉选择（§4.7/§11.10/#7）。

---

## 大功能4：状态管理（Pinia store）

- [x] 子功能1：store state 定义（`stores/parser.ts`）
  - 创建 `frontend/src/stores/parser.ts`（Composition API 风格 `defineStore`）：`ref` 持有 `result: ParseResult | null`、`isUploading: boolean`、`uploadError: string | null`；`computed`：`isParsing`（status 为 pending/parsing）、`isTerminal`（status 为 completed/partial/failed）、`isExportReady`（isTerminal && status !== failed）、`uploadDisabled`（isParsing || isUploading）、`progressPercent`（`progress/total_pages*100`）、`processedPages`（`result?.pages.length`）、`statusText`（状态中文文案映射）、`metrics`（`result?.metrics ?? null`，供探究面板消费 TaskMetrics）、`totalVlmCost`（`result?.metrics?.total_cost ?? result?.cost_usd ?? 0`，VLM 成本汇总）。

- [x] 子功能2：upload action
  - `async upload(file: File, vlmModel?: string)`：置 `isUploading=true`、`uploadError=null`；调 `createParseTask`；成功后 `result = { ...response, progress:0, pages:[], errors:[] }`，`startPolling(response.task_id)`；失败捕获并写 `uploadError`、`ElMessage.error`；`finally` 复位 `isUploading`。加 `data-test` 钩子由组件侧绑定。

- [x] 子功能3：轮询逻辑 startPolling / stopPolling（§7.2）
  - `startPolling(taskId)`：清旧定时器，`setInterval` 每 ~1500ms 调 `getTask(taskId)` 刷新 `result`（含 `pages[].features` 与 `metrics`，探究面板随轮询实时更新）；每次刷新时若 `isTerminal` 则 `stopPolling`。`stopPolling()`：`clearInterval` 并置空 timer 引用。组件 `onUnmounted` 时调 `stopPolling` 防泄漏。轮询不阻塞 UI（异步，界面始终可交互，§6.2 边界）。

- [x] 子功能4：导出与重置 action（双格式，精度区分，含 metrics）
  - `async exportResult(format: ExportFormat)`：调 `exportTask(result.task_id, format)` 拿 Blob，前端触发下载（`URL.createObjectURL` + `<a download>`，文件名 `{task_id}.md` / `{task_id}.json`）；`format='json'` 下载结构化真相源（含 `metrics` + bbox/合并单元格/page_type 精度，S2/S4 + §11.9 导出含 metrics），`format='markdown'` 下载派生视图（人读 + LLM 友好，丢失合并/坐标/跨页/metrics）；非终态时按钮应已禁用，此处仍做二次校验抛提示。`reset()`：`stopPolling` + 清空 `result/isUploading/uploadError`，供「重新上传」复用。

---

## 大功能5：上传组件（Uploader.vue）

- [x] 子功能1：拖拽 + 点击上传交互
  - 创建 `frontend/src/components/Uploader.vue`：基于 `el-upload`（`drag` 拖拽 + 点击触发），`auto-upload` 配合 store `upload`；拖入时高亮（`.upload-zone` 公共类 + Element Plus 自带）；展示选中文件名与大小（格式化 KB/MB）；`:disabled="parserStore.uploadDisabled"`（§6.2 解析中禁用重复上传）。根元素加 `data-test="uploader"`，拖拽区加 `data-test="upload-dropzone"`。

- [x] 子功能2：前端预校验（U1/U2）
  - `beforeUpload`/自定义校验函数：校验 `file.type === 'application/pdf'`，否则 `ElMessage.error('仅支持 PDF 格式')` 并 reject（U1）；校验 `file.size <= 50 * 1024 * 1024`，否则 `ElMessage.error('文件大小不能超过 50MB')` 并 reject（U2）；与后端 `pdf_utils` 双重保险。校验失败加 `data-test="upload-error"` 便于定位。

- [x] 子功能3：上传中与禁用态展示
  - `isUploading` 时显示 `el-button` loading 或上传进度提示；`uploadDisabled`（解析中）时上传区置灰并文案提示「解析进行中，请等待完成」。使用 Element Plus `disabled` 属性，不写私有样式。

- [x] 子功能4：VLM 模型选择下拉（§11.10/#7）
  - `Uploader.vue` 内 `el-select`（`data-test="vlm-model-select"`）绑定 `parserStore.vlmModel`，`onMounted` 调 `getModels()` 填充选项（默认选 `default`）；上传时 `createParseTask(file, parserStore.vlmModel)` 传所选模型；无模型（getModels 为空）时隐藏下拉用 `.env` 默认。前端单任务用单一模型，跨模型对比走后端 eval（`--compare-vlm`）。

---

## 大功能6：状态条组件（StatusBar.vue）

- [x] 子功能1：整体状态 + 进度 + 页数展示（US5/F7）
  - 创建 `frontend/src/components/StatusBar.vue`：消费 `parserStore`；显示整体状态文案（待处理/解析中/已完成/部分完成/失败，用 `el-tag` 不同 type 区分：pending=info、parsing=primary、completed=success、partial=warning、failed=danger）；`el-progress` 显示 `progressPercent`；文字「已处理 X / 共 Y 页」（X=`processedPages`，Y=`total_pages`）；终态时额外展示 `cost_usd`（如有）与 `finished_at`。空状态（无 result）不渲染或显示占位。根元素 `data-test="status-bar"`，进度条 `data-test="progress"`。

---

## 大功能7：分页结果卡片（PageCard + 关键特征展示）

- [x] 子功能1：PageCard 卡片头部与块列表（F8/spec §6.1）
  - 创建 `frontend/src/components/PageCard.vue`：`props: page: PageResult, taskId: string, metrics?: TaskMetrics`；卡片头部「第 N 页 · 类型：{type}」（type 用 `el-tag` 展示，mixed/scan/table/text 配色）；卡片正文按 `blocks` 的 `order` 升序排列后，逐个渲染 `<BlockView :block="b" :task-id="taskId" />`；使用 `.card` 公共类。根元素 `data-test="page-card"`，头部 `data-test="page-card-header"`。

- [x] 子功能2：PageCard 关键特征展示（§11.9 探究面板-页面级）
  - 在 `PageCard.vue` 头部下方渲染关键特征条（`.features-bar` 公共类）：当 `page.features` 存在时，以 `el-tag`/小标签形式展示三个关键字段--`line_count`（线条数）、`area_ratio`（线密集区占比，百分比格式化）、`columns`（栏数，>1 时高亮提示多栏 §11.5）；这些特征来自 `page.features`（PageFeatures，§11.2 classify 特征向量）。特征条加 `data-test="page-features-bar"`，各字段加 `data-test="feature-line_count"` / `data-test="feature-area_ratio"` / `data-test="feature-columns"`。`page.features` 缺失时（旧数据/解析中未回写）该条不渲染。

- [x] 子功能3：PageCard VLM 成本标注（§11.9 探究面板-VLM 成本）
  - 在 `PageCard.vue` 特征条区域展示 VLM 成本上下文：当 `page.type` 为 `mixed`/`scan`（这两类页调用 VLM，§6.2/S1/S3）时，显示「VLM」徽标提示该页产生 VLM 调用；同时从 `metrics`（TaskMetrics，任务级）取 `total_cost` 作为任务总成本上下文展示（标注为「任务 VLM 总成本」），因 `VlmCallMetric` 未带 page 字段，per-page 精确成本以任务级汇总为准。成本徽标加 `data-test="vlm-cost-badge"`。`metrics` 缺失时不渲染成本位。

---

## 大功能8：Block 渲染组件（精度优先：表格结构化 + 图片描述真相源 + 文本 markdown）

- [x] 子功能1：BlockView 块分发调度 + 元信息展示
  - 创建 `frontend/src/components/BlockView.vue`：`props: block: Block, taskId: string`；按 `block.type` 分发：`text` -> `<TextBlock>`、`image` -> `<ImageBlock>`、`table` -> `<TableBlock>`；无匹配类型走兜底（纯文本展示 content）。提供可折叠的块元信息区（`.block-meta` 公共类 + `el-collapse` 或 `el-popover`）：展示 `block.page_type` 标签与 `block.bbox` 坐标 `[x0,y0,x1,y1]`（S4：前端可展示 bbox/page_type），默认折叠避免干扰阅读。根元素 `data-test="block-view"`，按 type 加 `data-test="block-{type}"`，元信息区 `data-test="block-meta"`。

- [x] 子功能2：TextBlock 文本块 Markdown 渲染（F3/F8）
  - 创建 `frontend/src/components/TextBlock.vue`：`props: block: Block`；用 `markdown-it`（store 级单例或模块级实例，避免重复创建）将呈现层 `block.content`（markdown 派生视图）渲染为 HTML，`v-html` 输出（内容来自后端可信抽取，需注意 XSS 可后续加 sanitize）；结构化真相源 `block.text` 可在元信息区展示原文（可选）。样式用公共类，正文排版用 common.scss 统一。根元素 `data-test="text-block"`。

- [x] 子功能3：ImageBlock 缩略图 + VLM 描述 + bbox 标注（F5/F8/§10.3）
  - 创建 `frontend/src/components/ImageBlock.vue`：`props: block: Block, taskId: string`；`<img :src="block.image_url">`（或 `block.image?.image_url`）直接经 proxy 命中后端裁剪图接口（§10.3）；缩略图下方展示 VLM 描述--优先取结构化真相源 `block.image.description`，缺失时降级用派生视图 `block.content`；标注 bbox 坐标 `[x0,y0,x1,y1]`（小字/`el-descriptions` 或标签，来自 `block.bbox`）；点击图片触发裁剪图查看（见大功能11）。`image_url`/`block.image` 缺失时降级显示占位。根元素 `data-test="image-block"`，图片 `data-test="image-thumb"`，描述区 `data-test="image-desc"`。

- [x] 子功能4：TableBlock 结构化渲染 + 合并单元格 + 复制 Markdown（F4/F8/S2/§10.4）
  - 创建 `frontend/src/components/TableBlock.vue`：`props: block: Block`；**按结构化真相源 `block.table`（TableData）渲染为 HTML `<table>`**，而非渲染 `block.content` markdown：
    - 遍历 `block.table.rows`（`string[][]`）生成 `<tr>`/`<td>`；
    - **保留合并单元格**（S2）：依据 `block.table.merged`（`MergedCell[]`）为对应 `row`/`col` 单元格设置 `colspan`/`rowspan` 属性，被合并的从属单元格跳过渲染（避免重复占位）；
    - 跨页续表（S5）：`block.table.cross_page === true` 时在表格上方标注「跨页续表」提示（`el-alert` type=info 或标签）；
    - 表格容器用 `.el-table-wrapper` / `.struct-table` 公共类，保留边框与圆角。
  - 提供「复制 Markdown」按钮，点击调 `navigator.clipboard.writeText(block.content)`（复制派生视图 markdown）+ `ElMessage.success('已复制')`（§10.4）。根元素 `data-test="table-block"`，表格 `data-test="struct-table"`，复制按钮 `data-test="copy-markdown"`，跨页标注 `data-test="cross-page-tag"`。

- [x] 子功能5：TableBlock 合并单元格渲染辅助函数
  - 在 `TableBlock.vue` 内（或 `src/utils/table.ts` 工具模块）实现 `buildCellMatrix(table: TableData)` 辅助函数：将 `rows` + `merged` 转换为可直接 `v-for` 渲染的单元格矩阵--对每个 `(row, col)` 计算其 `colspan`/`rowspan` 与是否为被合并的占位格（占位格不渲染），供模板遍历；处理 `merged` 中 `rowspan`/`colspan` 默认为 1 的边界。确保 colspan/rowspan 正确还原原表格结构（S2 精度要求：不扁平化丢结构）。

---

## 大功能9：导出功能（ExportBtn.vue，Markdown 派生 + JSON 含 metrics）

- [x] 子功能1：导出 Markdown / JSON 下载（F9/§4.3/§10.4/§11.9）
  - 创建 `frontend/src/components/ExportBtn.vue`：消费 `parserStore`；两个按钮（或 `el-dropdown`）：**导出 JSON（结构化真相源）**、**导出 Markdown（派生视图）**；按钮文案/tooltip 注明精度差异--JSON 保全 bbox/合并单元格/page_type 且**含 `metrics`（TaskMetrics VLM 成本/耗时）**（S2/S4 + §11.9 导出含 metrics），Markdown 为人读派生视图会丢失合并/坐标/跨页结构/metrics；`:disabled="!parserStore.isExportReady"`（终态且非 failed 才启用，未完成时 409 `TASK_NOT_READY`）；点击调 `parserStore.exportResult('markdown'|'json')`，内部走 `services/parse.ts` `exportTask`（`responseType:blob`）并触发浏览器下载；失败由拦截器统一提示。根元素 `data-test="export-btn"`，各格式按钮 `data-test="export-markdown"` / `data-test="export-json"`。

---

## 大功能10：探究面板（PageFeatures JSON 弹层 + VLM 成本 + TaskMetrics 汇总）

- [x] 子功能1：PageFeatures JSON 查看弹层（§11.9「查看 PageFeatures JSON」）
  - 创建 `frontend/src/components/FeaturesJsonDialog.vue`：`props: visible: boolean, features: PageFeatures | null, page: number`；用 `el-dialog` 弹层展示该页完整 `PageFeatures` JSON（全部字段：line_count/text_blocks_count/images_count/drawings_path_count/area_ratio/overlap_rate/char_density/font_flags/orthogonality/columns）；JSON 用 `<pre>` + `.json-viewer` 公共类格式化高亮（或 `JSON.stringify(features, null, 2)`），辅以字段中文释义 tooltip（如 `overlap_rate`=文本块 bbox 重叠率、`orthogonality`=线条正交性）。在 `PageCard.vue` 特征条区放「查看特征 JSON」按钮（`el-button` text/mini），点击 emit 打开本弹层。弹层根 `data-test="features-json-dialog"`，按钮 `data-test="view-features-json"`，JSON 区 `data-test="features-json-content"`。

- [x] 子功能2：TaskMetrics 汇总展示组件（§11.7/§11.9 VLM 成本汇总）
  - 创建 `frontend/src/components/MetricsPanel.vue`：`props: metrics: TaskMetrics | null`；用 `.metrics-panel` 公共类 + `el-descriptions`/`el-statistic` 展示任务级 VLM 汇总：
    - 顶部汇总卡：`total_cost`（总成本 $）、`total_latency_ms`（总耗时，ms/s 格式化）、`vlm_calls.length`（调用次数）；
    - `by_kind` 分布：按 `image`/`scan` 调用次数展示（`el-tag` 或进度条比例）；
    - 明细表：`vlm_calls` 列表（`el-table`），列含 kind/model/latency_ms/tokens/cost_usd/retry/success（success 用 `el-tag` success/danger），支持滚动；
    - `metrics` 为 null（解析中未回写/无 VLM 调用）时显示占位「暂无 VLM 指标」。
  - 根元素 `data-test="metrics-panel"`，汇总卡 `data-test="metrics-summary"`，明细表 `data-test="vlm-calls-table"`。

- [x] 子功能3：探究面板在 ParserView 的集成（§11.9）
  - 在 `ParserView.vue`（大功能13）结果区上方/导出区旁放置 `<MetricsPanel :metrics="parserStore.metrics" />`，终态（completed/partial）时展示 TaskMetrics 汇总，让研发直观看到 VLM 成本/耗时/调用明细（支撑 #7 VLM 成本/效果权衡探究）；解析中 `metrics` 可能为 null，面板自行占位。`PageCard` 传入 `:metrics="parserStore.metrics"` 以驱动页面级 VLM 成本标注（大功能7 子功能3）。确保探究面板数据随轮询刷新（`getTask` 返回含 `metrics`）。

---

## 大功能11：裁剪图查看（F10 可选）

- [x] 子功能1：图片块点击查看原图/裁剪区域（F10/O2）
  - 在 `ImageBlock.vue` 中集成 `el-image` 的 `preview-src-list`（或 `el-image-viewer`）：点击缩略图弹出大图查看器，展示原图 `block.image_url`；查看器支持缩放/旋转。若 `image_url`/`block.image` 为空（VLM 失败块）则不启用预览。预览容器加 `data-test="image-preview"`。本功能优先级 P2，可按需裁剪为最小可用。

---

## 大功能12：交互边界与异常展示

- [x] 子功能1：解析中禁用重复上传（§6.2）
  - 在 `Uploader.vue` 通过 `parserStore.uploadDisabled`（isParsing||isUploading）禁用上传区；store `upload` action 入口二次判断，解析中直接 `ElMessage.warning` 拦截，避免并发干扰。

- [x] 子功能2：VLM 失败块标记「图片未识别」（X2/X3）
  - 在 `ImageBlock.vue`：当 `block.content`/`block.image.description` 为后端兜底文案「图片未识别（VLM 调用失败）」/「扫描件未识别…」时，以 `el-alert` type=warning 或灰色降级样式突出标注；`image_url`/`block.image` 缺失时显示占位图 + 提示，仍保留块位与 order 及 bbox/page_type 元信息。

- [x] 子功能3：整体 partial 状态展示（X2/E3）
  - `StatusBar.vue` 对 `partial` 状态用 warning 色 `el-tag` 文案「部分完成」；并在状态条下方或结果区展示 `result.errors[]` 列表（每条 `page?: 第N页` + `message`），用 `el-alert` 或列表呈现，让用户定位失败页/块。错误列表容器 `data-test="error-list"`。

- [x] 子功能4：大文件不阻塞轮询与界面（§6.2/§9）
  - 轮询为异步 `setInterval` + Promise，不阻塞主线程；`ParserView` 渲染 `pages[]` 时对大文档考虑 `v-for` + `key=page.page`，必要时用 `el-virtual` / 分段渲染避免一次性挂载过多卡片卡顿；进度条持续刷新保证界面可交互（US5）。确保 `getTask` 超时（30s）不卡死轮询循环--单次失败记日志后继续下一轮，不中断轮询。

- [x] 子功能5：空状态与失败态兜底
  - `ParserView` 无 `result` 时显示 `.empty-state`（引导上传）；`status === failed` 时状态条置 danger，结果区展示 `errors` 可读信息与「重新上传」入口（调 `parserStore.reset`）。

---

## 大功能13：根组件与路由

- [x] 子功能1：App.vue 根组件
  - 创建 `frontend/src/App.vue`：极简根，`<router-view />` 挂载主页面；如需全局布局（顶部标题栏）用公共类 `.page` 组合，不写私有样式。根元素 `data-test="app-root"`。

- [x] 子功能2：路由配置（`router/index.ts`）
  - 创建 `frontend/src/router/index.ts`：`createRouter` history 模式；路由表 `/` -> `ParserView`（name: 'parser'，**直接指向 ParserView，不使用 PlaceholderView**）；兜底重定向 `/`。导出 router 实例供 `main.ts` 注册。

- [x] 子功能3：ParserView 主页面组装（§6.1 全部交互整合 + 探究面板集成）
  - 创建 `frontend/src/views/ParserView.vue`：组合 `<Uploader>` + `<StatusBar>` + `<MetricsPanel :metrics="parserStore.metrics">`（探究面板 TaskMetrics 汇总，终态展示）+ 结果列表（`v-for` 渲染 `<PageCard :page="p" :task-id="result.task_id" :metrics="parserStore.metrics">`）+ `<ExportBtn>`；消费 `parserStore`；布局用 `.page` + `.toolbar` + `.card` 公共类，区域间用 `$spacing-md/lg`；按需响应式分栏。页面根 `data-test="parser-view"`，结果区 `data-test="result-list"`，探究面板区 `data-test="investigation-panel"`。确保上传、状态、结果、探究面板、导出五区联动且状态边界正确（解析中禁上传、终态启用导出与探究面板、partial 展示错误）；导出区文案体现 JSON 精度（含 metrics）/Markdown 派生的差异。

---

> 备注：所有组件统一使用 Vue 3 `<script setup lang="ts">` + Composition API；样式优先复用 `common.scss` 公共类与 `variables.scss` 变量，确需组件级样式时用 `<style scoped lang="scss">` 并引用变量；网络请求一律经 `services/` 层，不在组件内直连 axios；关键交互节点（上传区、进度条、导出按钮、错误列表、各 block、bbox/page_type 元信息、结构化表格、特征条、特征 JSON 弹层、metrics 面板）均加 `data-test` 以便后续测试流程定位。精度优先落点：TableBlock 按 `block.table` 结构化渲染并保留 `merged` 合并单元格（S2）、所有 block 可展示 `bbox`+`page_type`（S4）、导出 JSON 保全结构化真相源且含 `metrics`（S2/S4/S5 + §11.9）。探究层落点：PageCard 展示 `PageFeatures` 关键特征（line_count/area_ratio/columns）+ VLM 成本（§11.9）、FeaturesJsonDialog 查看完整 PageFeatures JSON、MetricsPanel 汇总 TaskMetrics（VLM 成本/耗时/调用明细，支撑 #7 探究）、导出 JSON 含 `metrics`。

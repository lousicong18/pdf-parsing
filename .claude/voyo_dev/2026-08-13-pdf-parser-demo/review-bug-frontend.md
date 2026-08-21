# Review Bug - frontend

> 状态：全部通过 ✅（1 轮修复后复查通过）

## 精度渲染 bug
- [x] 【低】TableBlock 在 `block.table` 缺失/为空时，降级渲染派生视图 `block.content`（`<pre>{{ block.content }}</pre>`），违反精度优先原则「TableBlock 不能渲染 block.content」——应改为占位提示而非渲染派生内容 | `frontend/src/components/TableBlock.vue:44-46` → 已改为 `el-alert`「无结构化表格数据」
- [x] 【高】错误列表 `result.errors[]` 完全未渲染：plan §12.3 明确要求「状态条下方或结果区展示 `result.errors[]` 列表」并加 `data-test="error-list"`，当前 ParserView / StatusBar 均无此区域，partial/failed 用户无法看到具体错误页/块 | `frontend/src/views/ParserView.vue`、`frontend/src/components/StatusBar.vue` → ParserView 新增 `error-list` 区域

## 探究面板 bug
- [x] 【低】FeaturesJsonDialog 的 JSON 区使用 `{{ jsonText }}` 文本插值，但未做语法高亮（plan 要求 `.json-viewer` 格式化高亮）；当前仅靠 `<pre>` 类公共样式的 `white-space: pre-wrap` 展示，无可视化高亮 | `frontend/src/components/FeaturesJsonDialog.vue:57` → 新增 `highlightJson` 函数

## 导出 bug
- 无问题。

## 交互边界 bug
- [x] 【中】轮询失败未记日志：plan §12.4 要求「单次失败记日志后继续下一轮，不中断轮询」，当前 store `catch (e) {}` 完全静默，不利排查 | `frontend/src/stores/parser.ts:80-82` → 已加 `console.error`
- [x] 【低】无组件在 `onUnmounted` 中调用 `stopPolling`：plan §4 子功能 3 要求「组件 onUnmounted 时调 stopPolling 防泄漏」；当前仅在 `reset()` / `startPolling()` 时清理 | `frontend/src/views/ParserView.vue` → 已加 `onUnmounted`
- [x] 【低】`services/parse.ts` 导出的 `imageUrl(taskId, page, index)` 工具函数在整个 `src/` 中未被任何组件调用（ImageBlock 直接使用 `block.image_url`），属于冗余定义 | `frontend/src/services/parse.ts:31-33` → 已删除

## 样式规范问题
- [x] 【低】MetricsPanel 的 `el-tag` 使用内联样式 `style="margin-right: 8px"`，未使用 `$spacing-sm` 变量 | `frontend/src/components/MetricsPanel.vue:38` → 改为 `.m-sm-r` class
- [x] 【低】ExportBtn 存在空的 `<style scoped lang="scss"></style>` 块，应移除避免混淆 | `frontend/src/components/ExportBtn.vue:32-33` → 已移除
- [x] 【低】ImageBlock 预览标记使用非标准属性 `data-test-preview="image-preview"`，与 plan 约定 `data-test="image-preview"` 不一致 | `frontend/src/components/ImageBlock.vue:43` → 已统一为 `data-test="image-preview"`

## TS 类型问题
- [x] 【中】`env.d.ts` 将 `markdown-it` 模块整体声明为 `any`（`const MarkdownIt: any`），使 TextBlock 中 `import MarkdownIt` 丧失类型检查；`package.json` 已声明 `@types/markdown-it`，不应被此覆盖 | `frontend/src/env.d.ts:9-12` → 已移除 `declare module` 块
- [x] 【低】多处 `any` 滥用：`PageCard.vue:46` 与 `StatusBar.vue:23` 的 `:type="xxx as any"`、`MetricsPanel.vue:53` formatter `(r: any) =>`、`Uploader.vue:11` `ref<any[]>`、`Uploader.vue:30` `handleChange(file: any)` | 各处 → 已改为 `TagType`/`VlmCallMetric`/`string[]` 等具体类型
- [x] 【低】`env.d.ts` 中 `DefineComponent<{}, {}, any>` 的 `any` 泛参 | `frontend/src/env.d.ts:5` → 保留（Vite 默认模板产物，不影响业务类型安全）

## 路由/结构问题
- [x] 【中】`vlmModel` 状态未按 plan 置于 store：plan §5.4 明确要求「`el-select` 绑定 `parserStore.vlmModel`」且 store 应暴露 `vlmModel`；当前实现为 Uploader 局部 `ref('')`，store 无此状态 | `frontend/src/components/Uploader.vue:12`、`frontend/src/stores/parser.ts` → store 已暴露 `vlmModel`，Uploader 已改用
- [x] 【中】MarkdownIt 未使用模块级单例：plan §8.2 明确要求「store 级单例或模块级实例，避免重复创建」；当前在 TextBlock `<script setup>` 顶层 `new MarkdownIt()`，每个 TextBlock 实例独立创建 | `frontend/src/components/TextBlock.vue:8` → 新建 `utils/markdown.ts` 单例
- [x] 【中】`buildCellMatrix` 未对 `MergedCell.rowspan/colspan` 做 ≤0 边界兜底（plan §8.5 要求「处理 rowspan/colspan 默认为 1 的边界」） | `frontend/src/utils/table.ts:17-24` → 已加 `Math.max(1, ...)` 兜底

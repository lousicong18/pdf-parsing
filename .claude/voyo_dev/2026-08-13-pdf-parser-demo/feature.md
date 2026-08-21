# Feature: PDF 图文混排解析 Demo

## 用户原始需求

需求文档：`/Users/lou/ai_agent/pdf-parsing/需求说明与Demo蓝图.md`

构建一个「前端 + 后端」可运行的 PDF 图文混排解析 Demo。核心采用分层路由架构：PyMuPDF 先对每页做类型分类（text / table / mixed / scan），再按类型分派到最合适的引擎——纯文本原生抽取、表格走 pdfplumber、图文混排裁剪图片送云端多模态 VLM（OpenAI 兼容接口）、扫描件整页渲染送 VLM OCR。前端 Vue3 + Element Plus：上传 PDF、轮询进度、分块预览、导出 Markdown/JSON。后端 FastAPI 异步任务 + 内存 dict 存储（无 DB、无持久化、不要求并发）。需覆盖四类页面解析、进度状态、边界坑点（隐形文本层、矢量 Logo、跨页表格、VLM 重试兜底）。

## 使用的 Agent

| 角色 | 选用 agent | subagent_type |
|------|-----------|---------------|
| 功能设计agent | 系统默认 | general-purpose |
| 前端agent | 项目自定义 | frontend |
| 后端agent | 项目自定义 | backend |
| 监管agent（开发） | xxl-supervisor | xxl-supervisor |
| review manager | xxl-review-manager | xxl-review-manager |
| test manager | xxl-test-manager | xxl-test-manager |

## 管理进度

本次开发为 PDF 图文混排解析 Demo（前端 Vue3 + Element Plus；后端 FastAPI + PyMuPDF + pdfplumber + OpenAI 兼容 VLM，分层路由架构，内存存储无 DB）。功能设计用系统默认 agent，前端用项目 frontend agent，后端用项目 backend agent（其 MySQL/mapper 约定对本次无 DB demo 不适用，code_plan 会跳过，仅保留同步方法/导入/结构规范）。

agent提醒: 注意阅读 `yo-dev-xxl` skill , 明确你当前的管理的进度位置。

- 管理进度1: [x]设计产品文档
- 管理进度2: [x]设计开发计划文档
- 管理进度3: [x]设计开发任务文档
- 管理进度4: [x]实现功能开发
- 管理进度5: [x]代码review
- 管理进度6: [x]功能测试

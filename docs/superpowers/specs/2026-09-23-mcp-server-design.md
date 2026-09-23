# MCP Server 设计文档

**日期：** 2026-09-23
**版本：** v1.0
**作者：** lou

---

## 1. 背景与目标

### 1.1 背景

现有系统是一个 PDF 图文混排解析平台，提供 REST API（FastAPI）和 Vue 前端。核心能力包括：
- 页面分类（text/table/mixed/scan）
- 混合解析（MinerU + VLM OCR）
- 知识库导出（Markdown 分块）
- 图片缓存与 OSS 上传（已实现但未接入导出流程）

### 1.2 目标

将后端解析能力暴露为 MCP（Model Context Protocol）服务器，供以下场景使用：

| 场景 | 描述 | 优先级 |
|------|------|--------|
| **场景 1** | IDE/编辑器集成（Claude Code、Cursor）—— AI 助手直接调用 PDF 解析 | P0 |
| **场景 2** | 自动化流水线 —— 作为数据处理管道的一环 | P1（后续扩展） |

### 1.3 设计原则

- **不修改现有 REST API 和前端** —— MCP 作为额外入口，零侵入
- **最大化复用** —— 核心解析逻辑、分块逻辑、OSS 上传全部复用现有代码
- **知识库优先** —— 输出格式面向 RAG 消费（Markdown 分块 + 图片）

---

## 2. 架构设计

### 2.1 总体架构

```
┌─────────────────────────────────────────────────────────┐
│  MCP Server (src/mcp_server.py)                         │
│                                                         │
│  传输层: stdio (mcp SDK FastMCP)                        │
│  工具层: 工具函数（同步解析 + 知识库导出）                │
│  核心层: 复用 task_service / pipeline / classify        │
│         复用 kb_export_controller（增强图片上传）       │
└─────────────────────────────────────────────────────────┘
          │                        │
          ▼                        ▼
┌──────────────────┐    ┌─────────────────────┐
│ 现有 FastAPI     │    │ task_store (JSON)   │
│ (不变)           │    │ + image_cache       │
│ + 增强 kb_export │    │ + oss_client        │
└──────────────────┘    └─────────────────────┘
```

### 2.2 传输方式

**stdio（标准输入输出）**

- IDE 集成首选，Claude Code / Cursor 通过 `npx @modelcontextprotocol/server-...` 启动 MCP 进程
- 延迟低，无需端口，无需 HTTP 服务
- 后续可扩展 HTTP + SSE（场景 2），工具函数无需修改

### 2.3 文件访问

- **本地文件路径**：调用方传 `/path/to/file.pdf`，MCP Server 直接读取
- 不处理远程 URL（场景 1 不需要）

---

## 3. 工具设计

### 3.1 场景 1（P0）：同步解析 + 知识库导出

#### `parse_pdf`

将 PDF 解析为知识库分块（Markdown + 图片），供 RAG 消费。

**输入：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | 是 | — | 本地 PDF 文件路径 |
| `vlm_model` | string | 否 | "" | VLM 模型名称（空=使用配置默认） |
| `chunk_tokens` | int | 否 | 500 | 每块目标 token 数 |
| `overlap_tokens` | int | 否 | 50 | 块间重叠 token 数 |
| `include_images` | bool | 否 | true | 是否上传图片到 OSS 并插入图片引用 |

**输出：**

```json
{
  "task_id": "abc123",
  "filename": "report.pdf",
  "status": "completed",
  "total_pages": 10,
  "chunks": [
    {
      "chunk_id": "abc123_000",
      "content": "# 报告标题\n\n...文字内容...\n\n![图表描述](https://oss.example.com/tasks/abc123/2_0.png)\n\n| 年份 | 数据 |\n|---|---|\n| 2024 | 100 |",
      "page_start": 1,
      "page_end": 2,
      "page_types": ["text", "mixed"],
      "token_estimate": 480
    }
  ],
  "metrics": {
    "vlm_calls": 3,
    "total_cost": 12.5,
    "total_latency_ms": 4500
  }
}
```

**内部流程：**

```
file_path
  → 读取文件 bytes
  → task_service.create_task() + task_service.run_parse()
  → ParseResult（完整结构化数据）
  → kb_export_controller._build_segments(include_images=True)
     → 对 image block: image_cache.get() → oss_client.upload_image() → 插入 ![desc](oss_url)
  → kb_export_controller._chunk_segments()
  → 返回 {task_id, chunks, metrics}
```

### 3.2 场景 2（P1，后续扩展）：异步任务管理

> 本阶段仅设计，不实现。工具函数预留接口，后续按需添加。

| 工具 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `create_parse_task` | file_path, vlm_model? | task_id | 提交异步解析任务 |
| `get_task_status` | task_id | {status, progress, total_pages} | 轮询任务状态 |
| `get_task_result` | task_id | ParseResult JSON | 获取完整解析结果 |
| `export_task` | task_id, format | str (json/md/kb) | 导出任务结果 |
| `list_tasks` | — | list[TaskSummary] | 列出历史任务 |
| `delete_task` | task_id | bool | 删除任务 |
| `clear_tasks` | — | count | 清空所有任务 |
| `list_models` | — | list[str] | 列出可用 VLM 模型 |

---

## 4. 图片上传方案

### 4.1 现状

| 组件 | 状态 | 说明 |
|------|------|------|
| `oss_client.upload_image()` | ✅ 已实现 | 上传图片到阿里云/S3/Minio，返回公网 URL |
| `image_cache` | ✅ 已实现 | 内存缓存图片 bytes |
| `kb_export._build_segments()` | ❌ 未接入图片 | 只输出 VLM 描述文本 |

### 4.2 改动

**增强 `kb_export_controller._build_segments`，新增 `include_images` 参数：**

```python
def _build_segments(result, chunk_tokens, overlap_tokens, include_images=False):
    segments = []
    for page in result.pages:
        prev_text = ""
        for block in page.blocks:
            if block.type == "text":
                # ... 现有逻辑 ...
            elif block.type == "table":
                # ... 现有逻辑 ...
            elif block.type == "image":
                text = (block.content or "").strip()
                if text:
                    segment = {"text": text, "page": page.page, "type": "image"}
                    if include_images and block.image and block.image.image_url:
                        # 上传图片到 OSS，插入图片引用
                        oss_url = _upload_image_to_oss(result.task_id, page.page, block)
                        if oss_url:
                            segment["text"] += f"\n\n![{text}]({oss_url})"
                    segments.append(segment)
    return segments
```

**新增辅助函数 `_upload_image_to_oss`：**

```python
def _upload_image_to_oss(task_id: str, page: int, block: Block) -> Optional[str]:
    """上传图片块到 OSS，返回公网 URL。失败返回 None。"""
    # 从 image_cache 获取图片 bytes（需要 page 和 index）
    # 调用 oss_client.upload_image(task_id, page, index, bytes)
    # 返回 OSS URL
```

### 4.3 影响范围

| 调用方 | 行为 |
|--------|------|
| REST API `GET /tasks/{id}/export-kb` | `include_images=false`（默认，向后兼容） |
| MCP `parse_pdf(include_images=True)` | `include_images=true`，块中包含图片 URL |

### 4.4 OSS 配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `OSS_ENABLED` | "off" | 是否启用 OSS 上传 |
| `OSS_PROVIDER` | "aliyun" | 云服务商（aliyun/aws/s3/minio） |
| `OSS_BUCKET` | "" | 存储桶名称 |
| `OSS_ENDPOINT` | "" | 服务端点 |
| `OSS_ACCESS_KEY` | "" | Access Key |
| `OSS_SECRET_KEY` | "" | Secret Key |
| `OSS_PREFIX" | "tasks/" | 对象键前缀 |

**OSS 未启用时：** `include_images` 参数降级为 `false`，行为与现有导出一致。

---

## 5. 复用关系

| MCP 工具 | 复用的现有代码 | 说明 |
|---------|---------------|------|
| `parse_pdf` | `task_service.create_task()` + `run_parse()` | 同步解析 |
| `parse_pdf` | `kb_export_controller._build_segments()` | 分块逻辑（增强图片） |
| `parse_pdf` | `kb_export_controller._chunk_segments()` | token 分块 |
| `parse_pdf` | `oss_client.upload_image()` | 图片上传 |
| `parse_pdf` | `image_cache.get()` | 图片缓存 |

**不新增任何解析逻辑**，MCP 层只做编排和格式转换。

---

## 6. 错误处理

### 6.1 错误策略

MCP 工具**永远不抛异常**，错误作为返回值的一部分：

```json
{
  "error": true,
  "error_code": "FILE_NOT_FOUND",
  "error_message": "文件不存在: /path/to/missing.pdf"
}
```

### 6.2 错误码

| 错误码 | 说明 |
|--------|------|
| `FILE_NOT_FOUND` | 文件路径不存在 |
| `FILE_TOO_LARGE` | 文件超过大小限制 |
| `INVALID_FILE_TYPE` | 非 PDF 文件 |
| `PARSE_FAILED` | 解析失败（文件损坏） |
| `TASK_NOT_FOUND` | 任务不存在 |
| `TASK_FAILED` | 任务解析失败 |
| `OSS_UPLOAD_FAILED` | 图片上传失败（降级为纯文本） |

### 6.3 降级策略

- **OSS 上传失败** → 图片块降级为 VLM 描述文本，不阻塞整体流程
- **VLM 调用失败** → 图片描述标记为"图片未识别"，继续处理其他块
- **MinerU 不可用** → 自动 fallback 到原提取器（现有逻辑）

---

## 7. 目录结构

```
mcp/
└── README.md               # MCP Server 使用文档（新建）

src/
├── mcp_server.py           # MCP Server 入口（新建）
├── mcp_tools.py            # 工具函数定义（新建）
├── controller/
│   ├── kb_export_controller.py  # 增强：_build_segments 加 include_images
│   └── ...                       # 其他不变
├── utils/
│   ├── oss_client.py       # 不变
│   └── ...
└── ...
```

---

## 8. 配置示例

### 8.1 MCP Client 配置（Claude Code）

```json
{
  "mcpServers": {
    "pdf-parser": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.mcp_server"],
      "cwd": "/Users/lou/ai_agent/pdf-parsing",
      "env": {
        "VLM_BASE_URL": "https://api.minimax.io/v1",
        "VLM_API_KEY": "your-api-key",
        "VLM_MODEL": "MiniMax-M3",
        "OSS_ENABLED": "on",
        "OSS_PROVIDER": "aliyun",
        "OSS_BUCKET": "your-bucket",
        "OSS_ENDPOINT": "oss-cn-beijing.aliyuncs.com",
        "OSS_ACCESS_KEY": "your-access-key",
        "OSS_SECRET_KEY": "your-secret-key"
      }
    }
  }
}
```

### 8.2 .env 配置

```bash
# VLM 配置
VLM_BASE_URL=https://api.minimax.io/v1
VLM_API_KEY=your-api-key
VLM_MODEL=MiniMax-M3

# OSS 配置（可选）
OSS_ENABLED=on
OSS_PROVIDER=aliyun
OSS_BUCKET=your-bucket
OSS_ENDPOINT=oss-cn-beijing.aliyuncs.com
OSS_ACCESS_KEY=your-access-key
OSS_SECRET_KEY=your-secret-key
```

---

## 9. 测试计划

### 9.1 单元测试

| 测试项 | 测试内容 |
|--------|---------|
| `parse_pdf` 基础解析 | 上传 PDF，验证返回 chunks 结构 |
| `include_images=true` | 验证图片上传 OSS 并插入 URL |
| `include_images=false` | 验证向后兼容（纯文本） |
| OSS 未启用 | 验证降级行为 |
| 错误处理 | 文件不存在、非 PDF、损坏文件 |

### 9.2 集成测试

| 测试项 | 测试内容 |
|--------|---------|
| Claude Code 调用 | 配置 MCP Server，验证工具发现与调用 |
| 知识库消费 | chunks → 向量化 → 检索，验证图片可访问 |

---

## 10. 实施计划

### Phase 1：核心功能（场景 1）

1. 新建 `src/mcp_server.py` + `src/mcp_tools.py`
2. 增强 `kb_export_controller._build_segments`（图片上传）
3. 实现 `parse_pdf` 工具
4. 单元测试
5. Claude Code 集成测试

### Phase 2：异步任务管理（场景 2）

1. 实现 `create_parse_task` / `get_task_status` / `get_task_result`
2. 实现 `export_task` / `list_tasks` / `delete_task`
3. 单元测试

---

## 附录：MCP Server README

### 文件位置

`mcp/README.md`

### 内容结构

```markdown
# PDF Parser MCP Server

PDF 图文混排解析 MCP 服务器，供 IDE（Claude Code、Cursor）和自动化流水线调用。

## 快速开始

uv run python -m src.mcp_server

## MCP Client 配置

Claude Code / Cursor 配置示例...

## 工具列表

- parse_pdf: 解析 PDF 并输出知识库分块（Markdown + 图片）

## 环境变量

VLM 配置、OSS 配置...

## 使用场景

解析 PDF → 知识库 → 向量化 → RAG 检索...
```

---

## 附录：现有 API 与 MCP 工具映射

| REST API | MCP 工具 | 说明 |
|----------|---------|------|
| `POST /api/v1/parse` | `parse_pdf` | 同步解析 |
| `GET /api/v1/tasks` | `list_tasks` | 任务列表 |
| `GET /api/v1/tasks/{id}` | `get_task_result` | 任务详情 |
| `DELETE /api/v1/tasks/{id}` | `delete_task` | 删除任务 |
| `GET /api/v1/tasks/{id}/export` | `export_task` | 导出 |
| `GET /api/v1/tasks/{id}/export-kb` | `parse_pdf(format="kb")` | 知识库导出 |
| `GET /api/v1/models` | `list_models` | 模型列表 |

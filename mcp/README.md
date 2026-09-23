# PDF Parser MCP Server

PDF 图文混排解析 MCP 服务器，供 IDE（Claude Code、Cursor）和自动化流水线调用。

## 快速开始

```bash
# 安装依赖
uv sync

# 启动 MCP Server（stdio 传输）
uv run python -m src.mcp_server
```

## MCP Client 配置

### Claude Code

在项目根目录创建 `.mcp.json`（注意：`.claude/settings.json` 不支持 `mcpServers` 键，写在那里会被静默忽略）：

```json
{
  "mcpServers": {
    "pdf-parser": {
      "command": "uv",
      "args": ["--directory", "/path/to/pdf-parsing", "run", "python", "-m", "src.mcp_server"],
      "env": {
        "VLM_BASE_URL": "https://api.minimaxi.com/v1",
        "VLM_API_KEY": "${VLM_API_KEY}",
        "VLM_MODEL": "MiniMax-M3"
      }
    }
  }
}
```

- MCP 配置不支持 `cwd` 键，用 uv 的 `--directory` 参数指定项目路径
- `${VLM_API_KEY}` 从启动 Claude Code 的 shell 环境展开，避免明文密钥随 `.mcp.json` 提交入库
- 首次使用需在 `/mcp` 面板批准，或在 `.claude/settings.local.json` 添加 `"enabledMcpjsonServers": ["pdf-parser"]`

私有配置（不入仓库）改用命令添加，存入 `~/.claude.json`：

```bash
claude mcp add pdf-parser -s local \
  -e VLM_BASE_URL=https://api.minimaxi.com/v1 \
  -e VLM_API_KEY=sk-xxx \
  -e VLM_MODEL=MiniMax-M3 \
  -- uv --directory /path/to/pdf-parsing run python -m src.mcp_server
```

### Cursor

项目级 `.cursor/mcp.json` 或全局 `~/.cursor/mcp.json`，服务器定义格式同上（`command` / `args` / `env`）。

> OSS 相关环境变量按需补充到 `env`，见下方[环境变量](#oss-配置可选用于图片上传)。

## 工具列表

### `parse_pdf`

解析 PDF 并输出知识库分块（Markdown + 图片），供 RAG 消费。解析完成后在 PDF 同目录生成同名 `.md` 文件（各分块内容拼接；写入失败时 `md_path` 为 `null` 并附 `md_error`，不影响解析结果）。

**参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | 是 | — | 本地 PDF 文件路径 |
| `vlm_model` | string | 否 | "" | VLM 模型名称（空=使用配置默认） |
| `chunk_tokens` | int | 否 | 500 | 每块目标 token 数 |
| `overlap_tokens` | int | 否 | 50 | 块间重叠 token 数 |
| `include_images` | bool | 否 | true | 是否上传图片到 OSS 并插入图片引用 |

**返回示例：**

```json
{
  "task_id": "abc123",
  "filename": "report.pdf",
  "status": "completed",
  "total_pages": 10,
  "chunks": [
    {
      "chunk_id": "abc123_000",
      "content": "# 报告标题\n\n...文字内容...\n\n![图表描述](https://oss.example.com/tasks/abc123/2_0.png)",
      "page_start": 1,
      "page_end": 2,
      "page_types": ["text", "mixed"],
      "token_estimate": 480
    }
  ],
  "md_path": "/path/to/report.md",
  "metrics": {
    "vlm_calls": 3,
    "total_cost": 12.5,
    "total_latency_ms": 4500
  }
}
```

**错误返回：**

```json
{
  "error": true,
  "error_code": "FILE_NOT_FOUND",
  "error_message": "文件不存在: /path/to/missing.pdf"
}
```

**错误码：**

| 错误码 | 说明 |
|--------|------|
| `FILE_NOT_FOUND` | 文件路径不存在 |
| `INVALID_FILE_TYPE` | 非 PDF 文件 |
| `PARSE_FAILED` | 解析失败（文件损坏） |
| `TASK_NOT_FOUND` | 任务不存在 |
| `TASK_FAILED` | 任务解析失败 |

## 环境变量

### VLM 配置（必填）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VLM_BASE_URL` | — | OpenAI 兼容 VLM 端点 |
| `VLM_API_KEY` | — | API Key |
| `VLM_MODEL` | MiniMax-M3 | 默认模型 |

### OSS 配置（可选，用于图片上传）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OSS_ENABLED` | off | 是否启用 OSS 上传 |
| `OSS_PROVIDER` | aliyun | 云服务商（aliyun / aws / s3 / minio） |
| `OSS_BUCKET` | — | 存储桶名称 |
| `OSS_ENDPOINT` | — | 服务端点 |
| `OSS_ACCESS_KEY` | — | Access Key |
| `OSS_SECRET_KEY` | — | Secret Key |
| `OSS_PREFIX` | tasks/ | 对象键前缀 |

> OSS 未启用时，`include_images` 自动降级为 false，图片块仅输出 VLM 描述文本。

## 使用场景

### 解析 PDF → 知识库 → 向量化 → RAG 检索

```
1. 调用 parse_pdf(file_path="/path/to/report.pdf")
2. 获取 chunks 数组（每块含 content / page_start / page_end / token_estimate）
3. 将 chunks 向量化入库
4. RAG 检索时，chunk.content 可直接作为 LLM 上下文
5. 若 include_images=true，content 中包含图片 OSS URL，可 multimodal 展示
```

### 自定义分块大小

```python
parse_pdf(
    file_path="report.pdf",
    chunk_tokens=1000,    # 每块 1000 tokens
    overlap_tokens=100,   # 块间重叠 100 tokens
    include_images=true,
)
```

## 开发

```bash
# 运行测试
uv run pytest src/test/test_mcp_server.py src/test/test_mcp_tools.py -v

# 运行全部测试
uv run pytest src/test/ -v
```

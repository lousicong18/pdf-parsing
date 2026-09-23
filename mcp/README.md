# PDF Parser MCP Server

PDF 图文混排解析 MCP 服务器，供 IDE（Claude Code、Cursor）调用。

## 安装

```bash
# 克隆项目
git clone https://github.com/lousicong18/pdf-parsing.git
cd pdf-parsing

# 安装依赖
uv sync

# 配置 VLM（必填）
cp .env.example .env
# 编辑 .env，填写 VLM_BASE_URL / VLM_API_KEY / VLM_MODEL
```

## 使用

### Claude Code / Cursor 配置

在项目根目录创建 `.mcp.json`：

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

> 配置完成后，在对话中直接说"解析这个 PDF"即可调用。

### 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | string | 是 | — | 本地 PDF 文件路径 |
| `vlm_model` | string | 否 | "" | VLM 模型名称（空=使用 .env 默认） |
| `chunk_tokens` | int | 否 | 500 | 每块目标 token 数 |
| `overlap_tokens` | int | 否 | 50 | 块间重叠 token 数 |
| `include_images` | bool | 否 | true | 是否上传图片到 OSS 并插入图片引用 |

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VLM_BASE_URL` | — | OpenAI 兼容 VLM 端点 |
| `VLM_API_KEY` | — | API Key |
| `VLM_MODEL` | MiniMax-M3 | 默认模型 |
| `OSS_ENABLED` | off | 是否启用 OSS 上传（可选） |
| `OSS_PROVIDER` | aliyun | 云服务商（aliyun / aws / s3 / minio） |
| `OSS_BUCKET` | — | 存储桶名称 |
| `OSS_ENDPOINT` | — | 服务端点 |
| `OSS_ACCESS_KEY` | — | Access Key |
| `OSS_SECRET_KEY` | — | Secret Key |
| `OSS_PREFIX` | tasks/ | 对象键前缀 |

> OSS 未启用时，`include_images` 自动降级为 false，图片块仅输出 VLM 描述文本。

## 开发

```bash
# 运行 MCP 测试
uv run pytest src/test/test_mcp_server.py src/test/test_mcp_tools.py -v
```

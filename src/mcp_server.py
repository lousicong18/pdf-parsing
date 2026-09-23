"""MCP Server entry point (stdio transport)."""

from mcp.server.fastmcp import FastMCP

from src.mcp_tools import parse_pdf

mcp = FastMCP("pdf-parser")


@mcp.tool()
def parse_pdf_tool(
    file_path: str,
    vlm_model: str = "",
    chunk_tokens: int = 500,
    overlap_tokens: int = 50,
    include_images: bool = True,
) -> dict:
    """解析 PDF 并输出知识库分块（Markdown + 图片），供 RAG 消费。"""
    return parse_pdf(file_path, vlm_model, chunk_tokens, overlap_tokens, include_images)


def main():
    mcp.run()


if __name__ == "__main__":
    main()

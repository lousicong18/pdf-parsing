"""Tests for MCP Server: startup, tool registration, inputSchema."""

import asyncio

from mcp.server.fastmcp import FastMCP


def test_server_creates_fastmcp_instance():
    from src.mcp_server import mcp
    assert isinstance(mcp, FastMCP)
    assert mcp.name == "pdf-parser"


def test_parse_pdf_tool_registered():
    from src.mcp_server import mcp
    tools = asyncio.run(mcp.list_tools())
    tool_names = [t.name for t in tools]
    assert "parse_pdf_tool" in tool_names


def test_parse_pdf_tool_input_schema():
    from src.mcp_server import mcp
    tools = asyncio.run(mcp.list_tools())
    tool = next(t for t in tools if t.name == "parse_pdf_tool")
    schema = tool.inputSchema
    assert schema["type"] == "object"
    props = schema["properties"]
    assert "file_path" in props
    assert props["file_path"]["type"] == "string"
    assert "vlm_model" in props
    assert "chunk_tokens" in props
    assert "overlap_tokens" in props
    assert "include_images" in props
    assert schema["required"] == ["file_path"]
    assert props["chunk_tokens"]["default"] == 500
    assert props["overlap_tokens"]["default"] == 50
    assert props["include_images"]["default"] is True

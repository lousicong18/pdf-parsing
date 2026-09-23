"""MCP tool functions: parse_pdf (sync, never raises)."""

import os
from typing import Optional

from src.controller.kb_export_controller import _build_segments, _chunk_segments
from src.store import task_store
from src.task_manager.task_service import create_task, run_parse
from src.utils import oss_client


def parse_pdf(
    file_path: str,
    vlm_model: str = "",
    chunk_tokens: int = 500,
    overlap_tokens: int = 50,
    include_images: bool = True,
) -> dict:
    """解析 PDF 并输出知识库分块（Markdown + 图片）。永不抛异常。"""
    # 1. 文件校验
    if not os.path.isfile(file_path):
        return _error("FILE_NOT_FOUND", f"文件不存在: {file_path}")
    if not file_path.lower().endswith(".pdf"):
        return _error("INVALID_FILE_TYPE", f"非 PDF 文件: {file_path}")

    file_bytes = _read_file(file_path)
    if file_bytes is None:
        return _error("FILE_NOT_FOUND", f"文件不存在: {file_path}")

    # 2. 同步解析
    try:
        response, pdf_path = create_task(file_bytes, os.path.basename(file_path), vlm_model or None)
    except Exception as e:
        return _error("PARSE_FAILED", str(e))

    task_id = response.task_id
    try:
        run_parse(task_id, pdf_path, vlm_model or None)
    except Exception as e:
        return _error("PARSE_FAILED", f"解析异常: {e}")

    result = task_store.get(task_id)
    if result is None:
        return _error("TASK_NOT_FOUND", f"任务不存在: {task_id}")
    if result.status == "failed":
        return _error("TASK_FAILED", f"任务解析失败: {result.errors[0].message if result.errors else '未知错误'}")

    # 3. 知识库分块
    include_images = include_images and oss_client.is_oss_enabled()
    segments = _build_segments(result, chunk_tokens, overlap_tokens, include_images=include_images)
    chunks = _chunk_segments(segments, chunk_tokens, overlap_tokens, task_id)

    # 4. 落盘同名 .md（失败不影响解析结果）
    md_path, md_error = _write_markdown(file_path, chunks)

    metrics = result.metrics
    response = {
        "task_id": task_id,
        "filename": result.filename,
        "status": result.status,
        "total_pages": result.total_pages,
        "chunks": chunks,
        "md_path": md_path,
        "metrics": {
            "vlm_calls": len(metrics.vlm_calls) if metrics else 0,
            "total_cost": metrics.total_cost if metrics else 0.0,
            "total_latency_ms": metrics.total_latency_ms if metrics else 0,
        },
    }
    if md_error:
        response["md_error"] = md_error
    return response


def _write_markdown(file_path: str, chunks: list) -> tuple:
    """将 chunks 内容写入 PDF 同目录同名 .md，返回 (md_path, error)。"""
    md_path = os.path.splitext(file_path)[0] + ".md"
    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(c["content"] for c in chunks))
        return md_path, None
    except OSError as e:
        return None, f"写入 Markdown 失败: {e}"


def _read_file(file_path: str) -> Optional[bytes]:
    try:
        with open(file_path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _error(code: str, message: str) -> dict:
    return {"error": True, "error_code": code, "error_message": message}

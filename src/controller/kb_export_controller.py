"""GET /api/v1/tasks/{task_id}/export-kb — 知识库优化导出（按 token 切块 + 表格增强 + 元数据）。"""

from typing import Optional

from fastapi import APIRouter, Query

from src.models.schemas import Block, ErrorResponse
from src.parser.extract_table import tables_to_markdown
from src.store import image_cache, task_store
from src.utils import oss_client
from src.utils.errors import AppError

router = APIRouter(tags=["export"])

_CHARS_PER_TOKEN = 2.5  # 中英混合估算


@router.get(
    "/tasks/{task_id}/export-kb",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def export_kb(
    task_id: str,
    chunk_tokens: int = Query(default=500, ge=100, le=2000, description="每块目标 token 数"),
    overlap_tokens: int = Query(default=50, ge=0, le=500, description="块间重叠 token 数"),
):
    result = task_store.get(task_id)
    if result is None:
        raise AppError(code="TASK_NOT_FOUND", detail="任务不存在或已过期", status_code=404)
    if result.status not in {"completed", "partial", "failed"}:
        raise AppError(code="TASK_NOT_READY", detail="任务尚未完成，请稍后再试", status_code=409)

    segments = _build_segments(result, chunk_tokens, overlap_tokens)
    chunks = _chunk_segments(segments, chunk_tokens, overlap_tokens, result.task_id)
    return {
        "task_id": result.task_id,
        "filename": result.filename,
        "chunk_tokens": chunk_tokens,
        "overlap_tokens": overlap_tokens,
        "chars_per_token": _CHARS_PER_TOKEN,
        "total_chunks": len(chunks),
        "chunks": chunks,
    }


def _build_segments(result, chunk_tokens: int, overlap_tokens: int, include_images: bool = False) -> list[dict]:
    """将每页的 block 转为增强文本段（带表格标题、合并单元格填充）。"""
    segments: list[dict] = []
    for page in result.pages:
        prev_text = ""
        for block in page.blocks:
            if block.type == "text":
                text = (block.content or "").strip()
                if text:
                    segments.append({"text": text, "page": page.page, "type": "text"})
                    prev_text = text
            elif block.type == "table":
                title = _find_table_title(block, prev_text)
                # 重新生成 markdown：填充合并单元格 + 加标题
                content = tables_to_markdown(block.table, title=title) if block.table else (block.content or "")
                if content:
                    segments.append({"text": content, "page": page.page, "type": "table"})
            elif block.type == "image":
                text = (block.content or "").strip()
                if text:
                    segment = {"text": text, "page": page.page, "type": "image"}
                    if include_images:
                        oss_url = _upload_image_to_oss(result.task_id, page.page, block)
                        if oss_url:
                            segment["text"] += f"\n\n![{text}]({oss_url})"
                    segments.append(segment)
    return segments


def _upload_image_to_oss(task_id: str, page: int, block: Block) -> Optional[str]:
    """上传图片块到 OSS，返回公网 URL。失败返回 None。"""
    if not block.image_url:
        return None
    try:
        parts = block.image_url.rstrip("/").split("/")
        index = int(parts[-1])
    except (ValueError, IndexError):
        return None
    data = image_cache.get(task_id, page, index)
    if data is None:
        return None
    return oss_client.upload_image(task_id, page, index, data)


def _find_table_title(block: Block, prev_text: str) -> str:
    """从表格 block 的 title 字段或相邻文本块提取标题。"""
    # 若表格本身带 title 字段（扩展 TableData 时可用），优先使用
    if block.table and getattr(block.table, "title", None):
        return block.table.title
    # 启发式：上一段文本若是短句（< 60 字）且以"表"/"Table"/数字开头，视为标题
    if prev_text and len(prev_text) < 60:
        stripped = prev_text.strip()
        if stripped and (stripped[0].isdigit() or stripped.startswith("表") or stripped.lower().startswith("table")):
            return stripped
    return ""


def _chunk_segments(segments: list[dict], chunk_tokens: int, overlap_tokens: int, task_id: str) -> list[dict]:
    """按 token 大小切块，保留页码/类型元数据。"""
    max_chars = int(chunk_tokens * _CHARS_PER_TOKEN)
    overlap_chars = int(overlap_tokens * _CHARS_PER_TOKEN)

    chunks: list[dict] = []
    seg_idx = 0

    while seg_idx < len(segments):
        cur_texts: list[str] = []
        cur_chars = 0
        pages: list[int] = []
        types: set[str] = set()
        overlap_seg_idx: int | None = None

        while seg_idx < len(segments):
            seg = segments[seg_idx]
            if cur_chars + len(seg["text"]) > max_chars and cur_texts:
                break
            if cur_chars >= max_chars - overlap_chars and overlap_seg_idx is None:
                overlap_seg_idx = seg_idx
            cur_texts.append(seg["text"])
            cur_chars += len(seg["text"])
            pages.append(seg["page"])
            types.add(seg["type"])
            seg_idx += 1

        if cur_texts:
            chunks.append({
                "chunk_id": f"{task_id}_{len(chunks):03d}",
                "page_start": min(pages),
                "page_end": max(pages),
                "page_types": sorted(types),
                "content": "\n\n".join(cur_texts),
                "char_count": cur_chars,
                "token_estimate": int(cur_chars / _CHARS_PER_TOKEN),
            })

        if overlap_seg_idx is not None and overlap_seg_idx < seg_idx:
            seg_idx = overlap_seg_idx

    return chunks

"""Task orchestration: create task + run_parse (background)."""

from datetime import datetime, timezone
from typing import Optional, Tuple

import fitz

from src.models.schemas import CreateTaskResponse, ParseResult, TaskError
from src.parser import classify, pipeline
from src.store import task_store
from src.task_manager import progress_service
from src.utils import env, metrics, pdf_utils, unique_id


def create_task(file_bytes: bytes, filename: str, vlm_model: Optional[str] = None) -> Tuple[CreateTaskResponse, str]:
    pdf_utils.validate_upload(filename, len(file_bytes), file_bytes[:8])
    task_id = unique_id.gen_task_id()
    pdf_path = pdf_utils.save_temp_pdf(file_bytes, task_id)
    try:
        total_pages = pdf_utils.get_page_count(pdf_path)
    except Exception as e:
        pdf_utils.remove_temp_pdf(pdf_path)
        raise ValueError(f"PARSE_FAILED: {e}")
    created_at = datetime.now(timezone.utc).isoformat()
    result = ParseResult(
        task_id=task_id,
        filename=filename,
        status="pending",  # type: ignore[arg-type]
        total_pages=total_pages,
        created_at=created_at,
    )
    task_store.create(task_id, result)
    response = CreateTaskResponse(
        task_id=task_id,
        filename=filename,
        status="pending",  # type: ignore[arg-type]
        total_pages=total_pages,
        created_at=created_at,
    )
    return response, pdf_path


def run_parse(task_id: str, pdf_path: str, vlm_model: Optional[str] = None) -> None:
    progress_service.mark_parsing(task_id)
    ctx = metrics.new_task_metrics()
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        progress_service.add_error(task_id, None, f"文件损坏或无法打开: {e}")
        progress_service.finish(task_id, "failed")
        pdf_utils.remove_temp_pdf(pdf_path)
        return

    try:
        prev_type: Optional[str] = None
        prev_header: Optional[list[str]] = None
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            page_type, features = classify.classify_page(page, prev_type, pdf_path, page_num, task_id, ctx)
            blocks, features = pipeline.dispatch_page(
                page, page_type, task_id, page_num, doc, prev_type, ctx, vlm_model, features, prev_header,
            )
            progress_service.update_page_done(task_id, page_num + 1, page_type, blocks, features)
            prev_type = page_type
            # 记录当前页最后一个表格的表头，用于下一页续表去重
            prev_header = None
            for b in reversed(blocks):
                if b.type == "table" and b.table and b.table.rows:
                    prev_header = b.table.rows[0]
                    break
    except Exception as e:
        progress_service.add_error(task_id, None, f"解析异常: {e}")
    finally:
        doc.close()

    progress_service.set_metrics(task_id, ctx)
    progress_service.add_cost(task_id, ctx.total_cost)

    result = task_store.get(task_id)
    if result and result.errors:
        status = "partial"
    else:
        status = "completed"
    progress_service.finish(task_id, status)
    pdf_utils.remove_temp_pdf(pdf_path)

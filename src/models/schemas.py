from typing import Literal, Optional

from pydantic import BaseModel

TaskStatus = Literal["pending", "parsing", "completed", "partial", "failed"]
PageType = Literal["text", "table", "mixed", "scan"]
BlockType = Literal["text", "image", "table"]


class MergedCell(BaseModel):
    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1


class TableData(BaseModel):
    rows: list[list[str]]  # row-major structure (source of truth, not flattened)
    n_rows: int
    n_cols: int
    merged: list[MergedCell] = []
    cross_page: bool = False
    header_repeat: bool = False  # 续表行与上一页表头重复
    bbox: list[float] = []  # [x0, y0, x1, y1] in page coordinates
    row_y_positions: list[float] = []  # data row center y-coordinates (page coords), aligned with rows[header_count:]
    chart_columns: list[int] = []  # indices of columns containing chart drawings (detected by vector analysis)


class ImageData(BaseModel):
    description: str  # VLM description
    image_url: str
    mime: str = "image/png"
    width: Optional[int] = None
    height: Optional[int] = None


class PageFeatures(BaseModel):
    line_count: int
    text_blocks_count: int
    images_count: int
    drawings_path_count: int
    area_ratio: float  # dense-line area / page area
    overlap_rate: float  # text-block bbox overlap rate
    char_density: float  # chars / text area
    font_flags: list[str] = []  # hidden-layer feature fonts
    orthogonality: float  # line orthogonality 0-1
    columns: int = 1
    filled_path_count: int = 0  # filled paths (dots/bars/areas/pies), excludes strokes


class PageRaw(BaseModel):
    """PyMuPDF 原始提取数据（用于前端查看 PDF 原始结构）。"""
    text_blocks: list[list] = []  # get_text("blocks"): [x0,y0,x1,y1,text,block_no,block_type]
    images: list[list] = []       # get_images(full=True): [xref,w,h,bpc,colorspace,...]
    drawings: list[dict] = []     # get_drawings(): 前 N 个路径（含 type/items/rect/color）
    links: list[list] = []        # get_links()
    page_size: list[float] = []   # [width, height]


class VlmCallMetric(BaseModel):
    kind: str  # image / scan
    model: str
    latency_ms: int
    tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0  # 实际为 ¥（人民币），保留字段名兼容
    retry: int = 0
    success: bool


class TaskMetrics(BaseModel):
    vlm_calls: list[VlmCallMetric] = []
    total_cost: float = 0.0
    total_latency_ms: int = 0
    by_kind: dict[str, int] = {}


class Block(BaseModel):
    type: BlockType
    bbox: list[float]  # [x0, y0, x1, y1], always kept
    page_type: PageType  # always kept
    order: int  # reading order within page
    # extraction layer: structured source of truth
    text: Optional[str] = None
    table: Optional[TableData] = None
    image: Optional[ImageData] = None
    # presentation layer: markdown derived view
    content: str = ""
    image_url: Optional[str] = None  # convenience = image.image_url


class PageResult(BaseModel):
    page: int
    type: PageType
    blocks: list[Block] = []
    features: Optional[PageFeatures] = None
    classification_log: list[str] = []
    raw: Optional[PageRaw] = None


class TaskError(BaseModel):
    page: Optional[int] = None
    message: str


class ParseResult(BaseModel):
    task_id: str
    filename: str
    status: TaskStatus
    total_pages: int
    progress: int = 0
    pages: list[PageResult] = []
    cost_usd: float = 0.0
    errors: list[TaskError] = []
    metrics: Optional[TaskMetrics] = None
    created_at: str = ""
    finished_at: Optional[str] = None


class CreateTaskResponse(BaseModel):
    task_id: str
    filename: str
    status: TaskStatus
    total_pages: int
    created_at: str


class TaskSummary(BaseModel):
    task_id: str
    filename: str
    status: TaskStatus
    total_pages: int
    cost_usd: float = 0.0
    created_at: str = ""
    finished_at: Optional[str] = None


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None

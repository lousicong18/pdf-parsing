export type TaskStatus = 'pending' | 'parsing' | 'completed' | 'partial' | 'failed'
export type PageType = 'text' | 'table' | 'mixed' | 'scan'
export type BlockType = 'text' | 'image' | 'table'
export type ExportFormat = 'markdown' | 'json'

export interface MergedCell {
  row: number
  col: number
  rowspan: number
  colspan: number
}

export interface TableData {
  rows: string[][]
  n_rows: number
  n_cols: number
  merged: MergedCell[]
  cross_page: boolean
}

export interface ImageData {
  description: string
  image_url: string
  mime: string
  width?: number
  height?: number
}

export interface PageFeatures {
  line_count: number
  text_blocks_count: number
  images_count: number
  drawings_path_count: number
  area_ratio: number
  overlap_rate: number
  char_density: number
  font_flags: string[]
  orthogonality: number
  columns: number
}

export interface PageRaw {
  text_blocks: (string | number)[][]
  images: (string | number)[][]
  drawings: Record<string, any>[]
  links: (string | number)[][]
  page_size: number[]
}

export interface VlmCallMetric {
  kind: string
  model: string
  latency_ms: number
  tokens: number
  cost_usd: number
  retry: number
  success: boolean
}

export interface TaskMetrics {
  vlm_calls: VlmCallMetric[]
  total_cost: number
  total_latency_ms: number
  by_kind: Record<string, number>
}

export interface Block {
  type: BlockType
  bbox: [number, number, number, number]
  page_type: PageType
  order: number
  text?: string
  table?: TableData
  image?: ImageData
  content: string
  image_url?: string
}

export interface PageResult {
  page: number
  type: PageType
  blocks: Block[]
  features?: PageFeatures
  classification_log?: string[]
  raw?: PageRaw
}

export interface TaskError {
  page?: number
  message: string
}

export interface ParseResult {
  task_id: string
  filename: string
  status: TaskStatus
  total_pages: number
  progress: number
  pages: PageResult[]
  cost_usd?: number
  errors: TaskError[]
  metrics?: TaskMetrics
  created_at: string
  finished_at?: string
}

export interface CreateTaskResponse {
  task_id: string
  filename: string
  status: TaskStatus
  total_pages: number
  created_at: string
}

export interface TaskSummary {
  task_id: string
  filename: string
  status: TaskStatus
  total_pages: number
  cost_usd: number
  created_at: string
  finished_at?: string
}

export interface ModelsResponse {
  models: string[]
  default: string
}

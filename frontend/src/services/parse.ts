import request from './request'
import type {
  CreateTaskResponse,
  ExportFormat,
  ModelsResponse,
  ParseResult,
  TaskSummary
} from '@/types'

export function createParseTask(file: File, vlmModel?: string): Promise<CreateTaskResponse> {
  const formData = new FormData()
  formData.append('file', file)
  if (vlmModel) formData.append('vlm_model', vlmModel)
  return request.post('/parse', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }).then((r) => r.data)
}

export function getTask(taskId: string): Promise<ParseResult> {
  return request.get(`/tasks/${taskId}`).then((r) => r.data)
}

export function exportTask(taskId: string, format: ExportFormat): Promise<Blob> {
  return request
    .get(`/tasks/${taskId}/export`, {
      params: { format },
      responseType: 'blob'
    })
    .then((r) => r.data)
}

export function getModels(): Promise<ModelsResponse> {
  return request.get('/models').then((r) => r.data)
}

export function listTasks(): Promise<TaskSummary[]> {
  return request.get('/tasks').then((r) => r.data)
}

export function deleteTask(taskId: string): Promise<void> {
  return request.delete(`/tasks/${taskId}`).then((r) => r.data)
}

export function exportKb(taskId: string, chunkTokens = 500, overlapTokens = 50): Promise<any> {
  return request.get(`/tasks/${taskId}/export-kb`, {
    params: { chunk_tokens: chunkTokens, overlap_tokens: overlapTokens }
  }).then((r) => r.data)
}

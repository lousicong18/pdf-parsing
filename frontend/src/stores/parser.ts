import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ParseResult, TaskMetrics } from '@/types'
import { createParseTask, exportTask, getTask, exportKb } from '@/services/parse'

const STATUS_TEXT: Record<string, string> = {
  pending: '待处理',
  parsing: '解析中',
  completed: '已完成',
  partial: '部分完成',
  failed: '失败'
}

export const useParserStore = defineStore('parser', () => {
  const result = ref<ParseResult | null>(null)
  const isUploading = ref(false)
  const uploadError = ref<string | null>(null)
  const vlmModel = ref<string>('')

  let timer: ReturnType<typeof setInterval> | null = null

  const isParsing = computed(
    () => result.value?.status === 'pending' || result.value?.status === 'parsing'
  )
  const isTerminal = computed(() =>
    ['completed', 'partial', 'failed'].includes(result.value?.status ?? '')
  )
  const isExportReady = computed(
    () => isTerminal.value && result.value?.status !== 'failed'
  )
  const uploadDisabled = computed(() => isParsing.value || isUploading.value)
  const progressPercent = computed(() => {
    if (!result.value) return 0
    return Math.round((result.value.progress / result.value.total_pages) * 100) || 0
  })
  const processedPages = computed(() => result.value?.pages.length ?? 0)
  const statusText = computed(() => STATUS_TEXT[result.value?.status ?? ''] ?? '')
  const metrics = computed<TaskMetrics | null>(() => result.value?.metrics ?? null)
  const totalVlmCost = computed(
    () => result.value?.metrics?.total_cost ?? result.value?.cost_usd ?? 0
  )

  async function upload(file: File, vlmModel?: string) {
    if (isParsing.value || isUploading.value) {
      ElMessage.warning('解析进行中，请等待完成')
      return
    }
    isUploading.value = true
    uploadError.value = null
    try {
      const resp = await createParseTask(file, vlmModel)
      result.value = {
        task_id: resp.task_id,
        filename: resp.filename,
        status: resp.status,
        total_pages: resp.total_pages,
        progress: 0,
        pages: [],
        errors: [],
        created_at: resp.created_at
      }
      startPolling(resp.task_id)
    } catch (e: any) {
      uploadError.value = e?.message || '上传失败'
      ElMessage.error(uploadError.value!)
    } finally {
      isUploading.value = false
    }
  }

  function startPolling(taskId: string) {
    stopPolling()
    timer = setInterval(async () => {
      try {
        const data = await getTask(taskId)
        result.value = data
        if (['completed', 'partial', 'failed'].includes(data.status)) {
          stopPolling()
        }
      } catch (e) {
        console.error('[polling] getTask failed:', e)
      }
    }, 1500)
  }

  function stopPolling() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  async function exportResult(format: 'markdown' | 'json') {
    if (!result.value) return
    if (!isExportReady.value) {
      ElMessage.warning('任务未完成，暂不可导出')
      return
    }
    const blob = await exportTask(result.value.task_id, format)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${result.value.task_id}.${format === 'json' ? 'json' : 'md'}`
    a.click()
    URL.revokeObjectURL(url)
  }

  async function exportKbResult(chunkTokens: number, overlapTokens: number) {
    if (!result.value || !isExportReady.value) {
      ElMessage.warning('任务未完成，暂不可导出')
      return
    }
    const data = await exportKb(result.value.task_id, chunkTokens, overlapTokens)
    const md = _buildKbMarkdown(data)
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${result.value.filename}_kb.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  function _buildKbMarkdown(data: any): string {
    const lines: string[] = []
    lines.push(`# ${data.filename}`)
    lines.push(`> 知识库优化导出 | ${data.total_chunks} 块 | 目标 ${data.chunk_tokens} tok/块 | 重叠 ${data.overlap_tokens} tok\n`)
    for (const c of data.chunks) {
      lines.push(`---`)
      lines.push(`<!-- chunk_id: ${c.chunk_id} | pages: ${c.page_start}-${c.page_end} | types: ${c.page_types.join(',')} | tokens: ~${c.token_estimate} -->`)
      lines.push(c.content)
      lines.push('')
    }
    return lines.join('\n')
  }

  async function loadTask(taskId: string) {
    stopPolling()
    try {
      const data = await getTask(taskId)
      result.value = data
      if (['pending', 'parsing'].includes(data.status)) {
        startPolling(taskId)
      }
    } catch (e: any) {
      ElMessage.error(e?.message || '加载任务失败')
    }
  }

  function reset() {
    stopPolling()
    result.value = null
    isUploading.value = false
    uploadError.value = null
  }

  return {
    result,
    isUploading,
    uploadError,
    vlmModel,
    isParsing,
    isTerminal,
    isExportReady,
    uploadDisabled,
    progressPercent,
    processedPages,
    statusText,
    metrics,
    totalVlmCost,
    upload,
    loadTask,
    startPolling,
    stopPolling,
    exportResult,
    exportKbResult,
    reset
  }
})

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElTag } from 'element-plus'
import { Refresh, View, Document } from '@element-plus/icons-vue'
import { listTasks } from '@/services/parse'
import type { TaskSummary } from '@/types'

const router = useRouter()
const tasks = ref<TaskSummary[]>([])
const loading = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

const STATUS_MAP: Record<string, { text: string; type: 'success' | 'warning' | 'danger' | 'info' | '' }> = {
  pending: { text: '待处理', type: 'info' },
  parsing: { text: '解析中', type: '' },
  completed: { text: '已完成', type: 'success' },
  partial: { text: '部分完成', type: 'warning' },
  failed: { text: '失败', type: 'danger' }
}

async function fetchTasks() {
  loading.value = true
  try {
    tasks.value = await listTasks()
  } catch (e: any) {
    ElMessage.error(e?.message || '加载历史记录失败')
  } finally {
    loading.value = false
  }
}

function viewTask(taskId: string) {
  router.push({ name: 'parser', query: { task_id: taskId } })
}

function getRowClass({ row }: { row: TaskSummary }) {
  return row.status === 'failed' ? 'row-failed' : ''
}

onMounted(() => {
  fetchTasks()
  timer = setInterval(fetchTasks, 3000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="history-view page" data-test="history-view">
    <div class="history-header">
      <h1 class="page-title">
        <el-icon><Document /></el-icon>
        解析历史
      </h1>
      <el-button type="primary" :icon="Refresh" @click="fetchTasks" :loading="loading">
        刷新
      </el-button>
    </div>

    <el-table
      :data="tasks"
      v-loading="loading"
      stripe
      :row-class-name="getRowClass"
      empty-text="暂无解析记录"
      data-test="history-table"
    >
      <el-table-column prop="filename" label="文件名" min-width="200" show-overflow-tooltip />
      <el-table-column prop="total_pages" label="页数" width="80" align="center" />
      <el-table-column label="状态" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="STATUS_MAP[row.status]?.type" size="small">
            {{ STATUS_MAP[row.status]?.text || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="成本" width="100" align="center">
        <template #default="{ row }">
          ${{ row.cost_usd?.toFixed(4) ?? '0.0000' }}
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="180" />
      <el-table-column label="操作" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            :icon="View"
            @click="viewTask(row.task_id)"
          >
            查看
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped lang="scss">
.history-view {
  .history-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  }

  :deep(.row-failed) {
    --el-table-tr-bg-color: var(--el-color-danger-light-9);
  }
}
</style>

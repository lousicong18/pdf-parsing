<script setup lang="ts">
import { computed } from 'vue'
type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'
import { useParserStore } from '@/stores/parser'

const parserStore = useParserStore()

const statusTagType = computed<TagType>(() => {
  const map: Record<string, TagType> = {
    pending: 'info',
    parsing: 'primary',
    completed: 'success',
    partial: 'warning',
    failed: 'danger'
  }
  return map[parserStore.result?.status ?? ''] ?? 'info'
})

const finishedAt = computed(() => parserStore.result?.finished_at ?? '')
</script>

<template>
  <div v-if="parserStore.result" class="status-bar card" data-test="status-bar">
    <el-tag :type="statusTagType" data-test="status-tag">
      {{ parserStore.statusText }}
    </el-tag>
    <el-progress
      :percentage="parserStore.progressPercent"
      :stroke-width="14"
      style="flex: 1; min-width: 200px"
      data-test="progress"
    />
    <span class="page-count" data-test="page-count">
      已处理 {{ parserStore.processedPages }} / 共 {{ parserStore.result.total_pages }} 页
    </span>
    <span v-if="parserStore.totalVlmCost" class="cost" data-test="cost">
      VLM 成本: ${{ parserStore.totalVlmCost.toFixed(4) }}
    </span>
    <span v-if="finishedAt" class="finished-at" data-test="finished-at">
      完成于: {{ finishedAt }}
    </span>
  </div>
</template>

<style scoped lang="scss">
.status-bar {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  flex-wrap: wrap;
}
.page-count,
.cost,
.finished-at {
  font-size: 13px;
  color: $color-text-secondary;
}
</style>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PageResult, TaskMetrics } from '@/types'
type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'
import BlockView from './BlockView.vue'
import FeaturesJsonDialog from './FeaturesJsonDialog.vue'

const props = defineProps<{
  page: PageResult
  taskId: string
  metrics?: TaskMetrics | null
}>()

const showFeatures = ref(false)

const sortedBlocks = computed(() =>
  [...props.page.blocks].sort((a, b) => a.order - b.order)
)

const typeTagType = computed<TagType>(() => {
  const map: Record<string, TagType> = {
    text: 'info',
    table: 'primary',
    mixed: 'warning',
    scan: 'danger'
  }
  return map[props.page.type] ?? 'info'
})

const typeLabel = computed(() => {
  const map: Record<string, string> = {
    text: '文本',
    table: '表格',
    mixed: '图文混排',
    scan: '扫描件'
  }
  return map[props.page.type] ?? props.page.type
})

const isVlmPage = computed(() => props.page.type === 'mixed' || props.page.type === 'scan')
</script>

<template>
  <div class="page-card" data-test="page-card">
    <div class="page-card-header" data-test="page-card-header">
      <span>第 {{ page.page }} 页</span>
      <el-tag :type="typeTagType" size="small">{{ typeLabel }}</el-tag>
    </div>

    <div v-if="page.features" class="features-bar" data-test="page-features-bar">
      <el-tag size="small" type="info" data-test="feature-line_count">
        线条: {{ page.features.line_count }}
      </el-tag>
      <el-tag size="small" type="info" data-test="feature-area_ratio">
        面积占比: {{ (page.features.area_ratio * 100).toFixed(1) }}%
      </el-tag>
      <el-tag
        size="small"
        :type="page.features.columns > 1 ? 'warning' : 'info'"
        data-test="feature-columns"
      >
        栏数: {{ page.features.columns }}
      </el-tag>
      <el-button
        size="small"
        text
        type="primary"
        data-test="view-features-json"
        @click="showFeatures = true"
      >
        查看特征 JSON
      </el-button>
    </div>

    <div v-if="isVlmPage" class="vlm-badge" data-test="vlm-cost-badge">
      <el-tag size="small" type="warning">VLM 调用页</el-tag>
      <span v-if="metrics" class="vlm-total-cost">
        任务 VLM 总成本: ${{ metrics.total_cost.toFixed(4) }}
      </span>
    </div>

    <div class="block-list">
      <BlockView
        v-for="b in sortedBlocks"
        :key="b.order"
        :block="b"
        :task-id="taskId"
      />
    </div>

    <FeaturesJsonDialog
      :visible="showFeatures"
      :features="page.features ?? null"
      :page="page.page"
      @update:visible="showFeatures = $event"
    />
  </div>
</template>

<style scoped lang="scss">
.page-card-header {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  font-weight: 600;
  margin-bottom: $spacing-md;
}
.vlm-badge {
  display: flex;
  align-items: center;
  gap: $spacing-sm;
  margin: $spacing-sm 0;
}
.vlm-total-cost {
  font-size: 12px;
  color: $color-text-secondary;
}
.block-list {
  margin-top: $spacing-md;
}
</style>

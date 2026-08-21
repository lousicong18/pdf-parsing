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
const showLog = ref(false)
const showRaw = ref(false)

const sortedBlocks = computed(() =>
  [...props.page.blocks].sort((a, b) => a.order - b.order)
)

const blockSummary = computed(() =>
  [...props.page.blocks]
    .sort((a, b) => a.order - b.order)
    .map(b => `${b.type}[${b.bbox.map(n => Math.round(n)).join(',')}]`)
    .join(' → ')
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

    <div v-if="page.classification_log?.length || page.raw" class="cls-log-bar">
      <el-button size="small" text type="primary" @click="showLog = !showLog">
        {{ showLog ? '隐藏' : '查看' }}分类日志 ({{ page.classification_log?.length ?? 0 }})
      </el-button>
      <el-button v-if="page.raw" size="small" text type="primary" @click="showRaw = true">
        查看 PyMuPDF 原始数据
      </el-button>
      <span class="block-summary">{{ blockSummary }}</span>
    </div>

    <el-collapse-transition>
      <div v-if="showLog" class="cls-log" data-test="classification-log">
        <div v-for="(line, i) in page.classification_log" :key="i" class="cls-log-line">
          <span class="cls-log-index">{{ i + 1 }}</span>
          <span>{{ line }}</span>
        </div>
      </div>
    </el-collapse-transition>

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

    <el-dialog
      v-if="page.raw"
      :model-value="showRaw"
      :title="`第 ${page.page} 页 PyMuPDF 原始数据`"
      width="800px"
      @update:model-value="showRaw = $event"
      data-test="raw-dialog"
    >
      <el-tabs>
        <el-tab-pane label="概览">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="页面尺寸">
              {{ page.raw.page_size[0]?.toFixed(1) }} × {{ page.raw.page_size[1]?.toFixed(1) }}
            </el-descriptions-item>
            <el-descriptions-item label="文本块数">{{ page.raw.text_blocks.length }}</el-descriptions-item>
            <el-descriptions-item label="图片数">{{ page.raw.images.length }}</el-descriptions-item>
            <el-descriptions-item label="矢量路径数">{{ page.raw.drawings.length }}</el-descriptions-item>
            <el-descriptions-item label="链接数">{{ page.raw.links.length }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
        <el-tab-pane :label="`文本块 (${page.raw.text_blocks.length})`">
          <div class="raw-scroll">
            <div v-for="(b, i) in page.raw.text_blocks" :key="i" class="raw-block-item">
              <div class="raw-block-meta">
                <span>[{{ b.slice(0, 4).map((n: any) => Math.round(n)).join(', ') }}]</span>
                <span class="raw-block-type">block {{ b[5] }} | type {{ b[6] }}</span>
              </div>
              <div class="raw-block-text">{{ b[4] }}</div>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane :label="`图片 (${page.raw.images.length})`">
          <pre class="raw-json">{{ JSON.stringify(page.raw.images, null, 2) }}</pre>
        </el-tab-pane>
        <el-tab-pane :label="`矢量路径 (${page.raw.drawings.length})`">
          <pre class="raw-json">{{ JSON.stringify(page.raw.drawings, null, 2) }}</pre>
        </el-tab-pane>
        <el-tab-pane :label="`链接 (${page.raw.links.length})`">
          <pre class="raw-json">{{ JSON.stringify(page.raw.links, null, 2) }}</pre>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
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
.cls-log-bar {
  display: flex;
  align-items: center;
  gap: $spacing-md;
  margin: $spacing-sm 0;
  flex-wrap: wrap;
}
.block-summary {
  font-size: 12px;
  color: $color-text-secondary;
  font-family: $font-mono;
}
.cls-log {
  background: $color-background;
  border: 1px solid $color-border;
  border-radius: 4px;
  padding: $spacing-sm $spacing-md;
  margin: $spacing-sm 0;
  font-family: $font-mono;
  font-size: 12px;
  line-height: 1.6;
}
.cls-log-line {
  display: flex;
  gap: $spacing-sm;
}
.cls-log-index {
  color: $color-text-tertiary;
  flex-shrink: 0;
  width: 18px;
  text-align: right;
}
.raw-scroll {
  max-height: 500px;
  overflow-y: auto;
}
.raw-block-item {
  padding: $spacing-sm 0;
  border-bottom: 1px solid $color-border-lighter;
  &:last-child { border-bottom: none; }
}
.raw-block-meta {
  font-size: 12px;
  color: $color-text-secondary;
  font-family: $font-mono;
  display: flex;
  gap: $spacing-md;
}
.raw-block-type { color: $color-text-tertiary; }
.raw-block-text {
  margin-top: 2px;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
}
.raw-json {
  max-height: 500px;
  overflow: auto;
  background: $color-background-secondary;
  padding: $spacing-md;
  font-size: 12px;
  line-height: 1.5;
}
</style>

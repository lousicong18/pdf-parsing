<script setup lang="ts">
import { computed } from 'vue'
import type { PageFeatures } from '@/types'

const props = defineProps<{
  visible: boolean
  features: PageFeatures | null
  page: number
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
}>()

function highlightJson(json: string): string {
  return json
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"([^"]+)"(?=\s:)/g, '<span class="json-key">"$1"</span>')
    .replace(/: "([^"]*)"/g, ': <span class="json-string">"$1"</span>')
    .replace(/: (\d+\.?\d*)/g, ': <span class="json-number">$1</span>')
}

const jsonHtml = computed(() =>
  props.features ? highlightJson(JSON.stringify(props.features, null, 2)) : ''
)

const fieldLabels: Record<string, string> = {
  line_count: '线条数',
  text_blocks_count: '文本块数',
  images_count: '图片数',
  drawings_path_count: '绘图路径数',
  area_ratio: '线密集区面积占比',
  overlap_rate: '文本块 bbox 重叠率',
  char_density: '字符密度',
  font_flags: '隐形层特征字体',
  orthogonality: '线条正交性 (0-1)',
  columns: '栏数'
}

const fields = computed(() => {
  if (!props.features) return []
  return Object.entries(props.features).map(([key, value]) => ({
    key,
    label: fieldLabels[key] ?? key,
    value: Array.isArray(value) ? JSON.stringify(value) : String(value)
  }))
})
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="`第 ${page} 页 PageFeatures`"
    width="640px"
    @update:model-value="emit('update:visible', $event)"
    data-test="features-json-dialog"
  >
    <div class="features-fields" data-test="features-fields">
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item v-for="f in fields" :key="f.key" :label="f.label">
          {{ f.value }}
        </el-descriptions-item>
      </el-descriptions>
    </div>
    <div class="json-viewer" data-test="features-json-content" v-html="jsonHtml"></div>
  </el-dialog>
</template>

<style scoped lang="scss">
.features-fields {
  margin-bottom: $spacing-md;
}
.json-key {
  color: #d19a66;
}
.json-string {
  color: #98c379;
}
.json-number {
  color: #61afef;
}
</style>

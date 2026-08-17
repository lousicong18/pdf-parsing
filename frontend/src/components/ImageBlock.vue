<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/types'

const props = defineProps<{
  block: Block
  taskId: string
}>()

const src = computed(() => props.block.image_url ?? props.block.image?.image_url ?? '')
const description = computed(
  () => props.block.image?.description ?? props.block.content ?? ''
)
const isFailed = computed(() =>
  /未识别|调用失败/.test(description.value)
)
const bboxText = computed(() => {
  const [x0, y0, x1, y1] = props.block.bbox
  return `[${x0.toFixed(1)}, ${y0.toFixed(1)}, ${x1.toFixed(1)}, ${y1.toFixed(1)}]`
})
</script>

<template>
  <div class="image-block" data-test="image-block">
    <el-alert
      v-if="isFailed"
      type="warning"
      :closable="false"
      data-test="image-failed"
    >
      {{ description }}
    </el-alert>

    <div v-else class="image-body">
      <div v-if="src" class="image-preview" data-test="image-preview">
        <el-image
          :src="src"
          :preview-src-list="[src]"
          fit="contain"
          style="max-width: 320px; max-height: 240px"
          data-test="image-thumb"
        />
      </div>
      <div v-else class="image-placeholder" data-test="image-placeholder">
        图片缺失
      </div>
      <div class="image-desc" data-test="image-desc">{{ description }}</div>
    </div>

    <div class="image-meta" data-test="image-bbox">
      bbox: {{ bboxText }}
    </div>
  </div>
</template>

<style scoped lang="scss">
.image-body {
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
}
.image-desc {
  font-size: 13px;
  color: $color-text-secondary;
  line-height: 1.5;
}
.image-placeholder {
  padding: $spacing-lg;
  background: $color-background-secondary;
  border-radius: $border-radius-sm;
  text-align: center;
  color: $color-text-placeholder;
}
.image-meta {
  margin-top: $spacing-xs;
  font-size: 12px;
  color: $color-text-placeholder;
}
</style>

<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/types'
import TextBlock from './TextBlock.vue'
import ImageBlock from './ImageBlock.vue'
import TableBlock from './TableBlock.vue'

const props = defineProps<{
  block: Block
  taskId: string
}>()

const metaText = computed(() => {
  const [x0, y0, x1, y1] = props.block.bbox
  return `page_type=${props.block.page_type}  bbox=[${x0.toFixed(1)}, ${y0.toFixed(1)}, ${x1.toFixed(1)}, ${y1.toFixed(1)}]`
})
</script>

<template>
  <div class="block-view block-item" data-test="block-view">
    <TextBlock v-if="block.type === 'text'" :block="block" />
    <ImageBlock v-else-if="block.type === 'image'" :block="block" :task-id="taskId" />
    <TableBlock v-else-if="block.type === 'table'" :block="block" />
    <div v-else class="block-fallback" data-test="block-fallback">
      {{ block.content }}
    </div>

    <div class="block-meta" data-test="block-meta">
      <el-collapse>
        <el-collapse-item title="元信息">
          <span>{{ metaText }}</span>
          <span v-if="block.text">原文长度: {{ block.text.length }}</span>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<style scoped lang="scss">
.block-fallback {
  padding: $spacing-sm;
  color: $color-text-secondary;
  font-size: 13px;
}
</style>

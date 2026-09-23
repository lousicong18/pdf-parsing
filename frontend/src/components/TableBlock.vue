<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import type { Block } from '@/types'
import { buildCellMatrix } from '@/utils/table'

const props = defineProps<{ block: Block }>()

const matrix = computed(() =>
  props.block.table ? buildCellMatrix(props.block.table) : []
)
const table = computed(() => props.block.table)

function copyMarkdown() {
  navigator.clipboard.writeText(props.block.content ?? '').then(() => {
    ElMessage.success('已复制 Markdown')
  })
}
</script>

<template>
  <div class="table-block" data-test="table-block">
    <div v-if="table?.cross_page" class="cross-page-tag" data-test="cross-page-tag">
      <el-alert type="info" :closable="false" title="跨页续表" />
    </div>

    <div class="el-table-wrapper" v-if="matrix.length">
      <table class="struct-table" data-test="struct-table">
        <tbody>
          <tr v-for="(row, ri) in matrix" :key="ri">
            <td
              v-for="cell in row"
              :key="`${cell.row}-${cell.col}`"
              :colspan="cell.colspan > 1 ? cell.colspan : undefined"
              :rowspan="cell.rowspan > 1 ? cell.rowspan : undefined"
            >
              {{ cell.text }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else-if="block.content" class="table-fallback" data-test="table-fallback">
      <pre class="markdown-content">{{ block.content }}</pre>
    </div>

    <div v-else class="table-fallback" data-test="table-fallback">
      <el-alert type="info" :closable="false" title="无结构化表格数据" />
    </div>

    <div class="table-actions">
      <el-button size="small" data-test="copy-markdown" @click="copyMarkdown">
        复制 Markdown
      </el-button>
    </div>
  </div>
</template>

<style scoped lang="scss">
.cross-page-tag {
  margin-bottom: $spacing-sm;
}
.table-actions {
  margin-top: $spacing-sm;
}
.table-fallback {
  margin: $spacing-sm 0;
}
.markdown-content {
  white-space: pre-wrap;
  font-family: monospace;
  font-size: 12px;
  margin: 0;
  padding: $spacing-sm;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
</style>

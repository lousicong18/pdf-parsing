<script setup lang="ts">
import { QuestionFilled } from '@element-plus/icons-vue'
import { useParserStore } from '@/stores/parser'

const parserStore = useParserStore()
</script>

<template>
  <div class="export-btn action-bar" data-test="export-btn">
    <el-button
      type="primary"
      :disabled="!parserStore.isExportReady"
      data-test="export-json"
      @click="parserStore.exportResult('json')"
    >
      导出 JSON（结构化真相源，含 metrics）
    </el-button>
    <el-button
      type="success"
      :disabled="!parserStore.isExportReady"
      data-test="export-markdown"
      @click="parserStore.exportResult('markdown')"
    >
      导出 Markdown（派生视图）
    </el-button>
    <el-button
      type="warning"
      :disabled="!parserStore.isExportReady"
      data-test="export-kb"
      @click="parserStore.exportKbResult(500, 50)"
    >
      导出知识库（切块 + 元数据）
    </el-button>
    <el-tooltip content="JSON 保全结构；Markdown 为派生视图；知识库版按 token 切块并带页码/类型元数据">
      <el-icon><QuestionFilled /></el-icon>
    </el-tooltip>
  </div>
</template>

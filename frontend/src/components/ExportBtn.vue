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
    <el-tooltip content="JSON 保全 bbox/合并单元格/page_type 且含 VLM 成本 metrics；Markdown 为派生视图">
      <el-icon><QuestionFilled /></el-icon>
    </el-tooltip>
  </div>
</template>

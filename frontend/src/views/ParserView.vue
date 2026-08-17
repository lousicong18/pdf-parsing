<script setup lang="ts">
import { computed, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useParserStore } from '@/stores/parser'
import Uploader from '@/components/Uploader.vue'
import StatusBar from '@/components/StatusBar.vue'
import MetricsPanel from '@/components/MetricsPanel.vue'
import PageCard from '@/components/PageCard.vue'
import ExportBtn from '@/components/ExportBtn.vue'

const route = useRoute()
const parserStore = useParserStore()

const pages = computed(() => parserStore.result?.pages ?? [])
const taskId = computed(() => parserStore.result?.task_id ?? '')
const errors = computed(() => parserStore.result?.errors ?? [])
const showErrors = computed(() =>
  parserStore.result && ['partial', 'failed'].includes(parserStore.result.status)
)

watch(
  () => route.query.task_id,
  (id) => {
    if (typeof id === 'string' && id) {
      parserStore.loadTask(id)
    }
  },
  { immediate: true }
)

onUnmounted(() => parserStore.stopPolling())
</script>

<template>
  <div class="parser-view page" data-test="parser-view">
    <div class="page-header">
      <h1 class="page-title">PDF 图文混排解析</h1>
      <router-link to="/history" class="history-link">
        <el-button link type="primary">解析历史</el-button>
      </router-link>
    </div>

    <Uploader />
    <StatusBar />

    <div v-if="showErrors && errors.length" class="error-list" data-test="error-list">
      <el-alert
        v-for="(err, i) in errors"
        :key="i"
        type="warning"
        :closable="false"
        :title="(err.page ? `第 ${err.page} 页: ` : '') + err.message"
      />
    </div>

    <div v-if="parserStore.result" class="investigation-panel" data-test="investigation-panel">
      <MetricsPanel :metrics="parserStore.metrics" />
    </div>

    <div v-if="pages.length" class="result-list" data-test="result-list">
      <PageCard
        v-for="p in pages"
        :key="p.page"
        :page="p"
        :task-id="taskId"
        :metrics="parserStore.metrics"
      />
    </div>

    <div v-if="parserStore.result && !pages.length" class="empty-state">
      解析中，请稍候...
    </div>

    <ExportBtn />
  </div>
</template>

<style scoped lang="scss">
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: $spacing-md;
}

.investigation-panel {
  margin-bottom: $spacing-lg;
}
.error-list {
  margin-bottom: $spacing-lg;
  display: flex;
  flex-direction: column;
  gap: $spacing-sm;
}
</style>

<script setup lang="ts">
import { computed } from 'vue'
import type { TaskMetrics, VlmCallMetric } from '@/types'

const props = defineProps<{ metrics: TaskMetrics | null }>()

const latencySeconds = computed(() =>
  props.metrics ? (props.metrics.total_latency_ms / 1000).toFixed(2) : '0'
)

const byKindEntries = computed(() =>
  Object.entries(props.metrics?.by_kind ?? {})
)
</script>

<template>
  <div class="metrics-panel" data-test="metrics-panel">
    <div class="panel-title">VLM 指标汇总</div>

    <div v-if="!metrics" class="empty-state" data-test="metrics-empty">
      暂无 VLM 指标
    </div>

    <div v-else>
      <div class="metrics-summary" data-test="metrics-summary">
        <el-statistic title="总成本 ($)" :value="metrics.total_cost" :precision="4" />
        <el-statistic title="总耗时 (s)" :value="Number(latencySeconds)" :precision="2" />
        <el-statistic title="调用次数" :value="metrics.vlm_calls.length" />
      </div>

      <div v-if="byKindEntries.length" class="by-kind" data-test="by-kind">
        <div class="kind-title">按类型分布</div>
        <el-tag
          v-for="[kind, count] in byKindEntries"
          :key="kind"
          size="small"
          class="m-sm-r"
        >
          {{ kind }}: {{ count }}
        </el-tag>
      </div>

      <el-table
        :data="metrics.vlm_calls"
        size="small"
        style="margin-top: 12px"
        data-test="vlm-calls-table"
      >
        <el-table-column prop="kind" label="类型" width="80" />
        <el-table-column prop="model" label="模型" width="140" />
        <el-table-column prop="latency_ms" label="耗时(ms)" width="100" />
        <el-table-column prop="tokens" label="Tokens" width="90" />
        <el-table-column prop="cost_usd" label="成本($)" width="100" :formatter="(r: VlmCallMetric) => r.cost_usd.toFixed(4)" />
        <el-table-column prop="retry" label="重试" width="70" />
        <el-table-column prop="success" label="成功" width="80">
          <template #default="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'" size="small">
              {{ row.success ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped lang="scss">
.panel-title {
  font-weight: 600;
  margin-bottom: $spacing-md;
}
.metrics-summary {
  display: flex;
  gap: $spacing-xl;
  margin-bottom: $spacing-md;
}
.by-kind {
  margin: $spacing-md 0;
}
.kind-title {
  font-size: 13px;
  color: $color-text-secondary;
  margin-bottom: $spacing-sm;
}
.m-sm-r {
  margin-right: $spacing-sm;
}
</style>

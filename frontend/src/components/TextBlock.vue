<script setup lang="ts">
import { computed } from 'vue'
import type { Block } from '@/types'
import { markdownIt } from '@/utils/markdown'

const props = defineProps<{ block: Block }>()

const html = computed(() => markdownIt.render(props.block.content ?? ''))
</script>

<template>
  <div class="text-block" data-test="text-block">
    <div class="text-content" v-html="html" data-test="text-content"></div>
  </div>
</template>

<style scoped lang="scss">
.text-content {
  font-size: 14px;
  line-height: 1.6;
  color: $color-text;

  :deep(p) { margin: 0 0 $spacing-sm 0; }
  :deep(h1), :deep(h2), :deep(h3) { margin: $spacing-md 0 $spacing-sm; }
  :deep(ul), :deep(ol) { padding-left: $spacing-lg; }
}
</style>

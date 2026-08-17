<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadRawFile } from 'element-plus'
import { useParserStore } from '@/stores/parser'
import { getModels } from '@/services/parse'
import type { ModelsResponse } from '@/types'

const parserStore = useParserStore()

const fileList = ref<string[]>([])
const models = ref<string[]>([])
const defaultModel = ref('')

const MAX_SIZE = 50 * 1024 * 1024

function beforeUpload(raw: UploadRawFile): boolean {
  if (raw.type !== 'application/pdf') {
    ElMessage.error('仅支持 PDF 格式')
    return false
  }
  if (raw.size > MAX_SIZE) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

function handleChange(file: UploadRawFile | { raw?: UploadRawFile }) {
  const raw = (file as { raw?: UploadRawFile }).raw
  if (!raw) return
  if (!beforeUpload(raw)) {
    fileList.value = []
    return
  }
  parserStore.upload(raw, parserStore.vlmModel || undefined)
}

async function loadModels() {
  try {
    const data: ModelsResponse = await getModels()
    models.value = data.models ?? []
    defaultModel.value = data.default ?? ''
    if (defaultModel.value && models.value.includes(defaultModel.value)) {
      parserStore.vlmModel = defaultModel.value
    } else if (models.value.length) {
      parserStore.vlmModel = models.value[0]
    }
  } catch {
    // 无模型时隐藏下拉
  }
}

onMounted(loadModels)
</script>

<template>
  <div class="uploader" data-test="uploader">
    <el-upload
      drag
      :auto-upload="false"
      :show-file-list="true"
      :file-list="fileList"
      :before-upload="beforeUpload"
      :on-change="handleChange"
      :disabled="parserStore.uploadDisabled"
      accept="application/pdf"
      data-test="upload-dropzone"
    >
      <div class="upload-zone">
        <div class="upload-text">拖拽 PDF 到此处，或点击上传</div>
        <div class="upload-hint">仅支持 PDF，最大 50MB</div>
      </div>
    </el-upload>

    <div v-if="models.length" class="model-select" data-test="vlm-model-select">
      <span class="model-label">VLM 模型：</span>
      <el-select v-model="parserStore.vlmModel" placeholder="选择模型" size="default">
        <el-option
          v-for="m in models"
          :key="m"
          :label="m"
          :value="m"
        />
      </el-select>
    </div>

    <div v-if="parserStore.uploadDisabled" class="upload-disabled-tip" data-test="upload-disabled-tip">
      解析进行中，请等待完成
    </div>
  </div>
</template>

<style scoped lang="scss">
.uploader {
  margin-bottom: $spacing-lg;
}
.model-select {
  display: flex;
  align-items: center;
  margin-top: $spacing-md;
  gap: $spacing-sm;
}
.model-label {
  font-size: 13px;
  color: $color-text-secondary;
}
.upload-disabled-tip {
  margin-top: $spacing-sm;
  color: $color-warning;
  font-size: 13px;
}
</style>

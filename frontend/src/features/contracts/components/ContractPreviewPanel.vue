<!-- @file 当前修订的合同文字预览、人工确认与历史文件下载。 -->
<script setup>
import { computed, ref, watch } from 'vue'
import { readableText } from '../fieldPresentation'

const props = defineProps({ workspace: Object, preview: Object, busy: Boolean, unsaved: Boolean })
const emit = defineEmits(['preview', 'generate', 'download', 'back-review'])
const acknowledged = ref(false)
const visualAcknowledged = ref(false)
const visualReviewRequired = computed(() =>
  Boolean(props.workspace.selected_template?.requires_visual_review)
)
const ready = computed(() => ['ready_to_generate', 'generated'].includes(props.workspace.stage) ||
  (props.workspace.stage === 'field_review' && props.workspace.fields?.length > 0 && !pendingCount.value))
const isDraft = computed(() => props.workspace.fields?.some((field) => field.status === 'omitted'))
const blockedReason = computed(() => {
  if (props.unsaved) return '审核修改尚未保存，请先返回内容审核保存修改，再载入最新预览。'
  if (props.workspace.selected_template?.requires_reselection)
    return '模板填写规则已更新，请重新载入模板并审核字段。'
  if (!props.workspace.fields?.length && !ready.value) return '当前还没有可审核字段，请先选择可填写的模板。'
  if (pendingCount.value) return `尚有 ${pendingCount.value} 项待确认，请核对已有值、补充缺失或明确留空。`
  return ready.value ? '' : '当前审核状态尚未就绪，请返回内容审核保存结果，或刷新任务状态。'
})
const canPreview = computed(() => ready.value && !blockedReason.value)
const previewIsCurrent = computed(() => props.preview?.revision === props.workspace.revision)
const pendingCount = computed(
  () =>
    props.workspace.fields?.filter((field) => !['confirmed', 'omitted'].includes(field.status)).length || 0
)
const blocks = computed(() =>
  props.preview?.blocks?.length
    ? props.preview.blocks
    : (props.preview?.text || '')
        .split('\n')
        .filter((text) => text.trim())
        .map((text) => ({ type: 'paragraph', text }))
)
watch(
  () => [props.preview?.revision, props.workspace.revision],
  () => {
    acknowledged.value = false
    visualAcknowledged.value = false
  }
)
</script>

<template>
  <section class="surface preview-panel">
    <div class="section-heading">
      <div>
        <span class="eyebrow">确认后导出</span>
        <h2>合同内容预览</h2>
      </div>
      <button
        v-if="canPreview && (preview || !busy)"
        class="secondary"
        :disabled="busy"
        @click="emit('preview')"
      >
        {{ preview ? '刷新预览' : '重新载入' }}
      </button>
    </div>
    <p class="muted">
      文字预览不等同于 Word 版面，导出后请核对表格、换页和签章区域。
    </p>
    <div v-if="blockedReason" class="preview-blocked" role="status">
      <h3>还不能导出：请先完成内容审核</h3>
      <p>{{ blockedReason }}</p>
      <button class="primary" :disabled="busy" @click="emit('back-review')">返回内容审核 →</button>
    </div>
    <template v-else-if="preview">
      <div class="contract-paper" aria-label="已审核合同文字预览">
        <template v-for="(block, index) in blocks" :key="index">
          <div v-if="block.type === 'table'" class="preview-table-scroll">
            <table class="preview-table">
              <tbody>
                <tr v-for="(row, rowIndex) in block.rows" :key="rowIndex">
                  <td v-for="(cell, column) in row" :key="column">{{ readableText(cell) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else>{{ readableText(block.text) }}</p>
        </template>
      </div>
    </template>
    <p v-else class="empty-state">{{ busy ? '正在载入合同预览…' : '预览尚未载入，请重新进入本步骤或刷新任务。' }}</p>
    <p v-if="preview?.truncated" class="review-issue">文字预览已截断，导出后请核对完整 Word 文件。</p>
    <p v-if="workspace.coverage_gaps?.length" class="review-issue">
      提取时的全合同覆盖检查发现
      {{ workspace.coverage_gaps.length }}
      项待核对。请回到内容审核查看原文依据和补充建议，并核对现在的合同是否已覆盖；这份预览不代表所有纪要约定已完整写入。
    </p>
    <p v-if="['failed', 'unverified', 'skipped'].includes(workspace.coverage_status)" class="review-issue">
      {{ workspace.coverage_error?.message || '全合同覆盖检查未完整通过' }}。请人工对照完整纪要。
    </p>
    <p v-if="preview?.omitted_fields?.length && canPreview" class="review-issue">
      已保留 {{ preview.omitted_fields.length }} 处空白，将导出待完善草稿，之后仍可补充。
    </p>
    <label v-if="canPreview" class="checkbox-label">
      <input v-model="acknowledged" type="checkbox" :disabled="!canPreview || !previewIsCurrent || busy" />
      我已对照原始模板核对填写范围、未识别空白及选项，并审查此版本预览，确认生成合同
    </label>
    <label v-if="canPreview && visualReviewRequired" class="checkbox-label">
      <input
        v-model="visualAcknowledged"
        type="checkbox"
        :disabled="!canPreview || !previewIsCurrent || busy"
      />
      我已查看原始 Word 的图片、图形及图表，确认这些保留区域无需自动填写；系统没有对其执行 OCR 或修改
    </label>
    <button
      v-if="canPreview"
      class="primary generate-button"
      :disabled="
        busy ||
        !canPreview ||
        !previewIsCurrent ||
        !acknowledged ||
        (visualReviewRequired && !visualAcknowledged)
      "
      @click="emit('generate', { visualReviewAcknowledged: visualAcknowledged })"
    >
      <span v-if="busy" class="loading-spinner" aria-hidden="true" />
      {{ isDraft ? '生成 DOCX 草稿' : '生成 DOCX 合同' }}
    </button>
    <div v-if="workspace.artifacts.length" class="generated-files">
      <h3>已生成的版本</h3>
      <article v-for="artifact in [...workspace.artifacts].reverse()" :key="artifact.id">
        <div>
          <strong>{{ artifact.template.name }}</strong>
          <p class="small-note">
            填写版本 {{ artifact.source_revision }} · {{ new Date(artifact.created_at).toLocaleString() }}
          </p>
        </div>
        <button class="secondary" :disabled="busy" @click="emit('download', artifact.id)">下载 DOCX</button>
      </article>
    </div>
  </section>
</template>

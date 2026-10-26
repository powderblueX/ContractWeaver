<!-- @file 纪要草稿及上传解析，不把文件直接发送给模型。 -->
<script setup>
import { ref } from 'vue'
import { contractApi } from '../contractApi'

const props = defineProps({
  busy: Boolean,
  maxChars: { type: Number, default: 60000 },
  maxUploadBytes: { type: Number, default: 5242880 },
})
const emit = defineEmits(['create'])
const title = ref('')
const sourceName = ref('协商记录')
const sourceText = ref('')
const importing = ref(false)
const importError = ref('')

/**
 * 限制文件大小后调用解析接口，把返回纪要放入草稿并清理文件输入状态。
 * @param {Event} event 浏览器文件或页面生命周期事件。
 */
async function importFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  importError.value = ''
  if (file.size > props.maxUploadBytes) {
    importError.value = '文件超过上传大小限制'
    return
  }
  importing.value = true
  try {
    const result = await contractApi.parseSource(file)
    sourceText.value = result.source_text
    sourceName.value = result.source_name
    if (!title.value) title.value = file.name.replace(/\.[^.]+$/, '')
  } catch (reason) {
    importError.value = reason.message
  } finally {
    importing.value = false
    event.target.value = ''
  }
}

/**
 * 提交任务名称与原始纪要，不在浏览器中直接调用模型。
 */
function submitSource() {
  emit('create', {
    title: title.value.trim() || '新的合同任务',
    source_name: sourceName.value,
    source_text: sourceText.value,
  })
}
</script>

<template>
  <section class="surface source-import">
    <span class="eyebrow">从真实协商记录开始</span>
    <h1>把已谈好的内容，变成待你确认的合同。</h1>
    <p class="muted">
      粘贴聊天记录或会议纪要，也可以导入 TXT、Markdown、DOCX。保留发言人和先后顺序，有助于区分提议与最终约定。
    </p>
    <ol class="welcome-steps">
      <li>导入记录</li>
      <li>选择合同模板</li>
      <li>提取并由你审核</li>
      <li>确认后导出</li>
    </ol>
    <form @submit.prevent="submitSource">
      <label>
        合同任务名称
        <input v-model="title" maxlength="100" placeholder="例如：设备采购协商记录" />
      </label>
      <div class="import-toolbar">
        <label class="secondary file-picker">
          {{ importing ? '正在读取…' : '导入记录文件' }}
          <input type="file" accept=".txt,.md,.docx" :disabled="busy || importing" @change="importFile" />
        </label>
        <span class="muted">{{ sourceName }} · 最大 {{ Math.floor(maxUploadBytes / 1024 / 1024) }} MB</span>
      </div>
      <label>
        协商记录
        <textarea
          v-model="sourceText"
          rows="14"
          :maxlength="maxChars"
          required
          minlength="10"
          placeholder="例如：\n采购方：10 台设备能否按每台 8000 元？\n供货方：可以，含税总价 80000 元，6 月 30 日前交付。\n采购方：确认，先付 30%，验收后付尾款。"
        />
      </label>
      <div class="inline-actions">
        <span class="muted">{{ sourceText.length }} / {{ maxChars }} 字符</span>
        <button class="primary" :disabled="busy || importing || sourceText.trim().length < 10">
          <span v-if="busy" class="loading-spinner" aria-hidden="true" />
          保存记录，进入合同任务 →
        </button>
      </div>
      <p v-if="importError" class="error" role="alert">{{ importError }}</p>
      <p v-if="importing" role="status" class="inline-actions">
        <span class="loading-spinner" aria-hidden="true" />
        正在读取文件，请稍候…
      </p>
      <p class="small-note">
        运行分析与提取时，记录会发送到部署者配置的模型 API。导入后可先浏览模板，也可让 Agent 分析并推荐。
      </p>
    </form>
  </section>
</template>

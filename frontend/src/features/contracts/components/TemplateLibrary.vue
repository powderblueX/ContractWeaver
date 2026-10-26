<!-- @file 推荐候选与完整模板目录，保留用户自主选择入口。 -->
<script setup>
import { onMounted, ref } from 'vue'
import { contractApi } from '../contractApi'
import { downloadFile } from '../../../shared/httpClient'
import { readableText } from '../fieldPresentation'

const props = defineProps({
  recommendations: { type: Array, default: () => [] },
  selectedTemplate: Object,
  busy: Boolean,
})
const emit = defineEmits(['select'])
const query = ref('')
const group = ref('')
const offset = ref(0)
const page = ref({ items: [], total: 0, limit: 24 })
const loading = ref(false)
const error = ref('')
const detail = ref(null)
const inspectingId = ref(null)
const downloading = ref(false)
let browseSequence = 0
// 单调序号使较早的查询响应无法覆盖用户刚提交的新筛选。
let detailSequence = 0

/**
 * 按分页筛选读取模板，利用请求序号丢弃过时响应。
 * @param {boolean} reset 是否把模板目录分页重置到首页。
 */
async function browse(reset = false) {
  if (reset) offset.value = 0
  const sequence = ++browseSequence
  loading.value = true
  try {
    const result = await contractApi.browseTemplates({
      query: query.value,
      group: group.value,
      offset: offset.value,
      limit: 24,
    })
    if (sequence === browseSequence) {
      page.value = result
      error.value = ''
    }
  } catch (reason) {
    if (sequence === browseSequence) error.value = reason.message
  } finally {
    if (sequence === browseSequence) loading.value = false
  }
}

/**
 * 读取结构支持情况及预览说明，避免迟到响应覆盖当前选择。
 * @param {Object} template 用户检查或选择的模板元数据。
 */
async function inspectTemplate(template) {
  const sequence = ++detailSequence
  error.value = ''
  inspectingId.value = template.id
  try {
    const result = await contractApi.templateDetails(template.id)
    if (sequence === detailSequence) detail.value = result
  } catch (reason) {
    error.value = reason.message
  } finally {
    if (sequence === detailSequence) inspectingId.value = null
  }
}

/**
 * 下载当前详情对应的未改动原件，并维护独立下载等待状态。
 */
async function downloadOriginal() {
  downloading.value = true
  try {
    await downloadFile(`/contracts/templates/${detail.value.id}/download`, `${detail.value.name}.docx`)
  } catch (reason) {
    error.value = reason.message
  } finally {
    downloading.value = false
  }
}

/**
 * 通知父页面明确选择该原件，然后关闭当前详情。
 * @param {Object} template 用户检查或选择的模板元数据。
 */
function chooseTemplate(template) {
  emit('select', template)
  detail.value = null
}
/**
 * 更新目录偏移并重新查询模板，不影响已选模板。
 * @param {number} direction 分页移动方向。
 */
function changePage(direction) {
  offset.value += direction * 24
  browse()
}
onMounted(() => browse())
</script>

<template>
  <section class="template-library">
    <div v-if="recommendations.length" class="surface">
      <div class="section-heading">
        <div>
          <span class="eyebrow">AGENT 推荐</span>
          <h2>从协商内容中找到的候选模板</h2>
        </div>
        <span class="muted">排序分仅供比较，不代表适用概率</span>
      </div>
      <div class="template-grid">
        <article
          v-for="template in recommendations"
          :key="template.id"
          class="template-card"
          :class="{ chosen: selectedTemplate?.id === template.id }"
        >
          <span class="tag">{{ template.group }}</span>
          <h3>{{ template.name }}</h3>
          <p v-for="reason in template.match_reasons" :key="reason" class="muted">{{ reason }}</p>
          <span class="score">检索排序分 {{ template.match_score }}</span>
          <div class="inline-actions">
            <button
              class="secondary"
              :disabled="busy || inspectingId === template.id"
              @click="inspectTemplate(template)"
            >
              <span v-if="inspectingId === template.id" class="loading-spinner" aria-hidden="true" />
              查看模板
            </button>
            <button
              class="primary"
              :disabled="busy || template.fillable === false || selectedTemplate?.id === template.id"
              @click="chooseTemplate(template)"
            >
              {{
                template.fillable === false
                  ? '仅供查看原件'
                  : selectedTemplate?.id === template.id
                    ? '已选择'
                    : '选用此模板'
              }}
            </button>
          </div>
        </article>
      </div>
    </div>
    <div class="surface">
      <span class="eyebrow">完整模板库</span>
      <h2>推荐不合适？由你选择。</h2>
      <form class="library-filters" @submit.prevent="browse(true)">
        <input v-model="query" aria-label="搜索合同模板" placeholder="搜索模板名称或关键词" />
        <select v-model="group" aria-label="模板来源">
          <option value="">全部来源</option>
          <option value="部委">部委</option>
          <option value="地方">地方</option>
        </select>
        <button class="secondary" :disabled="loading">搜索</button>
      </form>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="loading" class="muted inline-actions" role="status">
        <span class="loading-spinner" aria-hidden="true" />
        加载模板…
      </p>
      <div class="template-grid">
        <article
          v-for="template in page.items"
          :key="template.id"
          class="template-card"
          :class="{ chosen: selectedTemplate?.id === template.id }"
        >
          <span class="tag">{{ template.group }}</span>
          <h3>{{ template.name }}</h3>
          <div class="inline-actions">
            <button
              class="secondary"
              :disabled="busy || inspectingId === template.id"
              @click="inspectTemplate(template)"
            >
              <span v-if="inspectingId === template.id" class="loading-spinner" aria-hidden="true" />
              查看
            </button>
            <button
              class="primary"
              :disabled="busy || selectedTemplate?.id === template.id"
              @click="chooseTemplate(template)"
            >
              {{ selectedTemplate?.id === template.id ? '已选择' : '选用' }}
            </button>
          </div>
        </article>
      </div>
      <div class="pagination">
        <span class="muted">
          共 {{ page.total }} 份 · {{ page.total ? offset + 1 : 0 }}–{{ Math.min(offset + 24, page.total) }}
        </span>
        <button class="secondary" :disabled="loading || offset === 0" @click="changePage(-1)">上一页</button>
        <button class="secondary" :disabled="loading || offset + 24 >= page.total" @click="changePage(1)">
          下一页
        </button>
      </div>
    </div>
    <div v-if="detail" class="modal-backdrop" @click.self="detail = null">
      <section class="template-modal surface" role="dialog" aria-modal="true" aria-label="合同模板预览">
        <div class="section-heading">
          <h2>{{ detail.name }}</h2>
          <button class="secondary" @click="detail = null">关闭</button>
        </div>
        <p class="muted">
          {{ detail.group }} · {{ detail.fields.length }} 个填写字段 · 此处为内容预览，原始排版请下载查看。
        </p>
        <p v-for="warning in detail.warnings" :key="warning" class="review-issue">{{ warning }}</p>
        <p class="small-note">
          使用原始 Word
          模板，自动识别下划线、空白表格和候选填写位置；请下载原件核对扫描范围。无需手工添加占位符。
        </p>
        <pre class="document-preview">{{ readableText(detail.preview_text) }}</pre>
        <p v-if="detail.preview_truncated" class="muted">内容预览已截断，请下载查看完整模板。</p>
        <div class="inline-actions">
          <button class="secondary" :disabled="downloading" @click="downloadOriginal">
            <span v-if="downloading" class="loading-spinner" aria-hidden="true" />
            {{ downloading ? '正在下载…' : '下载原始模板' }}
          </button>
          <button
            class="primary"
            :disabled="
              busy || !detail.fields.length || detail.fillable === false || selectedTemplate?.id === detail.id
            "
            @click="chooseTemplate(detail)"
          >
            选用此模板
          </button>
        </div>
        <p v-if="!detail.fields.length || detail.fillable === false" class="error">
          此模板暂无可安全填写的位置，或含不支持的文档结构；可下载原件人工处理。
        </p>
      </section>
    </div>
  </section>
</template>

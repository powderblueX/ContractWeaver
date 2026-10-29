<!-- @file 本地审核草稿、批量确认和暂留空操作，不擅自替用户审批。 -->
<script setup>
import { computed, ref, watch } from 'vue'
import { fieldLabel, readableText } from '../fieldPresentation'

const props = defineProps({ fields: { type: Array, default: () => [] }, busy: Boolean })
const emit = defineEmits(['save', 'source', 'dirty'])
const drafts = ref({})
// drafts 是未提交的编辑缓冲；props.fields 始终代表最近一次服务端保存结果。
const filter = ref('all')
const search = ref('')
const selectedBlanks = ref([])
const blankReason = ref('此处为未使用的模板空白，保留原样，签署前再核对')
const unknownReason = ref('首轮纪要未提供或尚未确定，本次草稿暂留空，签署前补充并核对')
const pageIndex = ref(0)
const pageSize = 20
const saveNotice = ref('')
const savingNames = ref(new Set())
// 仅清理本次成功保存的字段，保留同页其他尚未提交的修改。
const statusLabels = {
  extracted: '待核对',
  missing: '未提取到',
  conflict: '存在分歧',
  unverified: '依据待核验',
  confirmed: '已确认',
  omitted: '明确保留空白',
}

watch(
  () => props.fields,
  (fields, previousFields = []) => {
    const previousByName = Object.fromEntries(previousFields.map((field) => [field.name, field]))
    const saved = fields.filter((field) => savingNames.value.has(field.name) &&
      ['confirmed', 'omitted'].includes(field.status) &&
      (field.status === 'omitted' ? drafts.value[field.name]?.action === 'omit' : field.value === drafts.value[field.name]?.value))
    if (saved.length) saveNotice.value = `已保存 ${saved.length} 项审核决定（${saved.filter((field) => field.status === 'omitted').length} 项保留空白）。`
    drafts.value = Object.fromEntries(
      fields.map((field) => {
        const previous = previousByName[field.name]
        const local = drafts.value[field.name]
        const localChanged =
          previous &&
          local &&
          (local.value !== previous.value ||
            local.note !== (previous.user_note || '') ||
            local.action !== (previous.status === 'omitted' ? 'omit' : 'confirm'))
        const draft =
          localChanged && !savingNames.value.has(field.name)
            ? local
            : {
                value: field.value,
                note: field.user_note || '',
                action: field.status === 'omitted' ? 'omit' : 'confirm',
              }
        return [field.name, draft]
      })
    )
    savingNames.value = new Set()
  },
  { immediate: true }
)
watch(
  () => props.busy,
  (busy) => {
    if (!busy) savingNames.value = new Set()
  }
)

/**
 * 判断字段是否已由用户确认或明确留空，不把模型提取当成人工审核。
 * @param {Object} field 当前字段元数据和审核状态。
 */
const isReviewed = (field) => ['confirmed', 'omitted'].includes(field.status)
const changedFields = computed(() =>
  props.fields.filter((field) => {
    const draft = drafts.value[field.name]
    return (
      draft &&
      (draft.value !== field.value ||
        draft.note !== (field.user_note || '') ||
        draft.action !== (field.status === 'omitted' ? 'omit' : 'confirm'))
    )
  })
)
watch(changedFields, (fields) => emit('dirty', fields.length > 0), { immediate: true })
/** Already saved decisions need no duplicate submission; editing re-enables the action. */
const isSaved = (field) => isReviewed(field) && !changedFields.value.some((item) => item.name === field.name)
const remaining = computed(() => props.fields.filter((field) => !isReviewed(field)).length)
// Apply to the whole contract, never just the visible page; preserve local edits.
const unknownFields = computed(() => {
  const changedNames = new Set(changedFields.value.map((field) => field.name))
  return props.fields.filter(
    (field) =>
      !isReviewed(field) &&
      !field.value.trim() &&
      !drafts.value[field.name]?.value.trim() &&
      !changedNames.has(field.name)
  )
})
const filteredFields = computed(() =>
  props.fields.filter((field) => {
    if (search.value && !`${fieldLabel(field)} ${field.context}`.includes(search.value)) return false
    if (filter.value === 'filled') return !isReviewed(field) && Boolean(field.value)
    if (filter.value === 'table') return field.kind === 'table'
    if (filter.value === 'layout') return field.kind === 'layout'
    if (filter.value === 'pending') return !isReviewed(field)
    if (filter.value === 'issues') return ['missing', 'conflict', 'unverified'].includes(field.status)
    if (filter.value === 'confirmed') return isReviewed(field)
    return true
  })
)
const visibleFields = computed(() =>
  filteredFields.value.slice(pageIndex.value * pageSize, (pageIndex.value + 1) * pageSize)
)
const pageCount = computed(() => Math.max(1, Math.ceil(filteredFields.value.length / pageSize)))
watch([filter, search], () => {
  pageIndex.value = 0
})
watch(pageCount, (count) => {
  pageIndex.value = Math.min(pageIndex.value, count - 1)
})
const pendingWithValues = computed(() =>
  props.fields.filter(
    (field) =>
      !isReviewed(field) &&
      !['conflict', 'unverified'].includes(field.status) &&
      !field.review_issues?.length &&
      drafts.value[field.name]?.value.trim() &&
      drafts.value[field.name]?.action === 'confirm'
  )
)

/**
 * 把指定字段的本地草稿序列化为服务端审核协议。
 * @param {Array<Object>} fields 本次参与决定的字段集合。
 */
function decisionsFor(fields) {
  return fields.map((field) => ({ name: field.name, ...drafts.value[field.name] }))
}

/**
 * 记录本次保存目标并提交审核，避免刷新时覆盖其他未保存草稿。
 * @param {Array<Object>} fields 本次参与决定的字段集合。
 */
function saveDecisions(fields) {
  if (props.busy || !fields.length) return
  saveNotice.value = ''
  savingNames.value = new Set(fields.map((field) => field.name))
  emit('save', decisionsFor(fields))
}

/**
 * 把原文中的候选填入本地草稿；仍需用户保存确认。
 * @param {string} fieldName 本地草稿使用的内部字段名。
 * @param {string} value 用户选择或输入的候选值。
 */
function useAlternative(fieldName, value) {
  drafts.value[fieldName].value = value
  drafts.value[fieldName].action = 'confirm'
}

/**
 * 仅批量确认无复核警告的非空候选，并要求一次明确确认。
 */
function saveAllFilled() {
  if (
    window.confirm(`确认已经核对这 ${pendingWithValues.value.length} 个已填写字段，并将它们作为合同填写值？`)
  )
    saveDecisions(pendingWithValues.value)
}
/**
 * 跨筛选和分页暂留空未确定字段，不覆盖已有值、已审核项或未保存修改。
 */
function ignoreUnknownFields() {
  const fields = unknownFields.value
  const reason = unknownReason.value.trim()
  if (
    !fields.length ||
    !reason ||
    !window.confirm(
      `将整个合同的 ${fields.length} 个未确定空白统一暂留空（包含其他页和筛选隐藏项）？\n已有内容、已审核项和未保存修改不会被覆盖。留空不代表无需约定，导出的只是待完善草稿；以后可取消留空并补充。`
    )
  )
    return
  fields.forEach((field) => {
    drafts.value[field.name].action = 'omit'
    drafts.value[field.name].note = reason
  })
  saveDecisions(fields)
  selectedBlanks.value = selectedBlanks.value.filter((name) => !savingNames.value.has(name))
}
/**
 * 仅勾选本页未审核且无值的表格或排版候选，不提交留空决定。
 */
function selectVisibleBlanks() {
  selectedBlanks.value = visibleFields.value
    .filter(
      (field) =>
        ['table', 'layout'].includes(field.kind) &&
        !isReviewed(field) &&
        !drafts.value[field.name]?.value.trim()
    )
    .map((field) => field.name)
}
/**
 * 给已勾选空白统一记录原因并提交，不自动清除非空内容。
 */
function omitSelected() {
  const fields = props.fields.filter(
    (field) => selectedBlanks.value.includes(field.name) && !drafts.value[field.name]?.value.trim()
  )
  if (
    !fields.length ||
    !blankReason.value.trim() ||
    !window.confirm(`请确认这 ${fields.length} 处确实无需填写，而不是遗漏的合同内容。全部保留原始空白？`)
  )
    return
  fields.forEach((field) => {
    drafts.value[field.name].action = 'omit'
    drafts.value[field.name].note = blankReason.value.trim()
  })
  saveDecisions(fields)
  selectedBlanks.value = []
}
</script>

<template>
  <section class="field-review">
    <div class="surface review-toolbar">
      <div class="section-heading">
        <div>
          <span class="eyebrow">原文依据 · 人工审查</span>
          <h2>{{ fields.length }} 个候选位置，{{ remaining }} 个待确认</h2>
        </div>
        <span class="muted">修改值将保留提取原值和原文依据</span>
      </div>
      <p v-if="saveNotice" role="status" aria-live="polite" class="review-save-notice">{{ saveNotice }}</p>
      <p class="guide-copy">确认填写值，或明确留空后导出待完善草稿；有分歧的内容请逐项核对。</p>
      <div v-if="unknownFields.length" class="ignore-unknown-tools">
        <button class="secondary" :disabled="busy || !unknownReason.trim()" @click="ignoreUnknownFields">
          未确定空白暂留空（{{ unknownFields.length }} 项）
        </button>
        <details>
          <summary>留空原因（适用于整个合同的未确定空白）</summary>
          <label>留空原因<input v-model="unknownReason" :disabled="busy" maxlength="2000" /></label>
        </details>
      </div>
      <div class="library-filters">
        <input v-model="search" aria-label="查找字段" placeholder="查找字段名称" />
        <select v-model="filter" aria-label="筛选字段状态">
          <option value="all">全部字段</option>
          <option value="filled">有提取值，待核对</option>
          <option value="table">表格明细</option>
          <option value="layout">排版与其他候选</option>
          <option value="pending">待确认</option>
          <option value="issues">缺失、分歧或依据待核验</option>
          <option value="confirmed">已审核</option>
        </select>
      </div>
      <details class="bulk-blank-tools">
        <summary>未使用的行或空白太多？批量说明留空</summary>
        <p class="small-note">只处理你勾选的空白项，不自动略过缺失信息，也不会清除已有填写值。</p>
        <button class="secondary" :disabled="busy" @click="selectVisibleBlanks">
          选中本页空的表格/排版项
        </button>
        <label>
          留空原因
          <input v-model="blankReason" :disabled="busy" maxlength="2000" />
        </label>
        <button
          class="secondary"
          :disabled="busy || !selectedBlanks.length || !blankReason.trim()"
          @click="omitSelected"
        >
          确认所选 {{ selectedBlanks.length }} 项保留空白
        </button>
      </details>
      <div v-if="pageCount > 1" class="pagination">
        <span class="muted">第 {{ pageIndex + 1 }} / {{ pageCount }} 页 · 每页 {{ pageSize }} 个字段</span>
        <button class="secondary" :disabled="pageIndex === 0" @click="pageIndex--">上一页字段</button>
        <button class="secondary" :disabled="pageIndex + 1 >= pageCount" @click="pageIndex++">
          下一页字段
        </button>
      </div>
      <div class="inline-actions">
        <button
          class="secondary"
          :disabled="busy || !changedFields.length"
          @click="saveDecisions(changedFields)"
        >
          保存并确认已修改项（{{ changedFields.length }}）
        </button>
        <button class="primary" :disabled="busy || !pendingWithValues.length" @click="saveAllFilled">
          确认所有已填写项（{{ pendingWithValues.length }}）
        </button>
      </div>
    </div>
    <article
      v-for="field in visibleFields"
      :key="field.name"
      class="surface field-card"
      :class="`field-${field.status}`"
    >
      <div class="section-heading">
        <h3>{{ fieldLabel(field) }}</h3>
        <span class="field-status" :class="field.status">{{ statusLabels[field.status] }}</span>
      </div>
      <label
        v-if="!isReviewed(field) && !drafts[field.name]?.value.trim()"
        class="checkbox-label bulk-select"
      >
        <input v-model="selectedBlanks" type="checkbox" :value="field.name" :disabled="busy" />
        选择此空白，供批量留空
      </label>
      <details class="field-context">
        <summary>在合同中的位置与含义</summary>
        <p>{{ readableText(field.context) }}</p>
      </details>
      <div class="field-columns">
        <div class="field-input">
          <label :for="`field-${fields.indexOf(field)}`">
            待填写的内容
            <textarea
              :id="`field-${fields.indexOf(field)}`"
              v-model="drafts[field.name].value"
              rows="3"
              maxlength="5000"
              :disabled="busy || drafts[field.name].action === 'omit'"
              placeholder="根据原文核对，或直接补充正确内容"
            />
          </label>
          <p v-if="field.value_type === 'date_part'" class="small-note">
            本格只填{{ field.component }}的数字，不含单位或完整日期。
          </p>
          <p v-if="field.choices?.length" class="small-note">
            允许选项：{{ field.choices.join(' / ') }}；未确定可暂留空。
          </p>
          <p v-if="field.fixed_unit" class="small-note">
            模板右侧已有“{{ field.fixed_unit }}”，本格不重复填写单位；例如填“叁仟”，不填“叁仟元整”。
          </p>
          <p
            v-if="field.extracted_value && drafts[field.name].value !== field.extracted_value"
            class="small-note"
          >
            Agent 原始提取：{{ field.extracted_value }}
          </p>
          <div v-if="field.alternatives?.length" class="alternatives">
            <span class="small-note">记录中的候选值：</span>
            <button
              v-for="alternative in field.alternatives"
              :key="alternative"
              class="secondary"
              :disabled="busy"
              @click="useAlternative(field.name, alternative)"
            >
              {{ alternative }}
            </button>
          </div>
        </div>
        <div class="source-evidence">
          <strong>原文依据</strong>
          <blockquote v-for="(evidence, index) in field.evidence" :key="index">
            <button @click="emit('source', evidence.line_number)">第 {{ evidence.line_number }} 行 ↗</button>
            <p>{{ evidence.quote }}</p>
          </blockquote>
          <p v-if="!field.evidence.length" class="muted">没有可核验的原文依据，请补充或确认。</p>
          <p v-if="field.note" class="small-note">提取说明：{{ field.note }}</p>
          <p v-for="issue in field.review_issues" :key="issue" class="review-issue">{{ issue }}</p>
        </div>
      </div>
      <div class="field-decision">
        <label class="checkbox-label">
          <input
            v-model="drafts[field.name].action"
            type="checkbox"
            true-value="omit"
            false-value="confirm"
            :disabled="busy"
          />
          此项明确保留空白（例如线下签字）
        </label>
        <input
          v-model="drafts[field.name].note"
          maxlength="2000"
          :placeholder="
            drafts[field.name].action === 'omit' ? '必填：保留空白的原因' : '修改或确认备注（选填）'
          "
          :disabled="busy"
        />
        <button
          class="primary"
          :disabled="
            busy || isSaved(field) ||
            (drafts[field.name].action === 'omit'
              ? !drafts[field.name].note.trim()
              : !drafts[field.name].value.trim())
          "
          @click="saveDecisions([field])"
        >
          {{ busy && savingNames.has(field.name) ? '正在保存…' : isSaved(field) ? (field.status === 'omitted' ? '已保存 · 保留空白' : '已保存 · 已确认') : drafts[field.name].action === 'omit' ? '确认保留空白' : '保存并确认' }}
        </button>
      </div>
    </article>
    <p v-if="!visibleFields.length" class="empty-state">没有符合筛选条件的字段。</p>
  </section>
</template>

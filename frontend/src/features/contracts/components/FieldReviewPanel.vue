<script setup>
import { computed, ref, watch } from 'vue'
import { fieldLabel, readableText } from '../fieldPresentation'

const props = defineProps({ fields: { type: Array, default: () => [] }, busy: Boolean })
const emit = defineEmits(['save', 'source', 'dirty'])
const drafts = ref({})
const filter = ref('all')
const search = ref('')
const selectedBlanks = ref([])
const blankReason = ref('此处为未使用的模板空白，保留原样，签署前再核对')
const unknownReason = ref('首轮纪要未提供或尚未确定，本次草稿暂留空，签署前补充并核对')
const pageIndex = ref(0)
const pageSize = 20
let savingNames = new Set()
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
          localChanged && !savingNames.has(field.name)
            ? local
            : {
                value: field.value,
                note: field.user_note || '',
                action: field.status === 'omitted' ? 'omit' : 'confirm',
              }
        return [field.name, draft]
      })
    )
    savingNames = new Set()
  },
  { immediate: true }
)
watch(
  () => props.busy,
  (busy) => {
    if (!busy) savingNames = new Set()
  }
)

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

function decisionsFor(fields) {
  return fields.map((field) => ({ name: field.name, ...drafts.value[field.name] }))
}

function saveDecisions(fields) {
  savingNames = new Set(fields.map((field) => field.name))
  emit('save', decisionsFor(fields))
}

function useAlternative(fieldName, value) {
  drafts.value[fieldName].value = value
  drafts.value[fieldName].action = 'confirm'
}

function saveAllFilled() {
  if (
    window.confirm(`确认已经核对这 ${pendingWithValues.value.length} 个已填写字段，并将它们作为合同填写值？`)
  )
    saveDecisions(pendingWithValues.value)
}
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
  selectedBlanks.value = selectedBlanks.value.filter((name) => !savingNames.has(name))
}
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
      <p class="guide-copy">
        先核对已有提取值。纪要不完整也可以继续：暂无信息的空白可一键暂留空，之后再补充；有内容的分歧仍需核对，不会自动清除。
      </p>
      <p class="small-note">
        批量确认只包含无复核警告的已填写项。有分歧或依据问题的字段请逐项修正和确认；年月日分格只填数字，选择项只填一个选项。
      </p>
      <div class="ignore-unknown-tools">
        <strong>第一轮信息不全？不必逐项点击。</strong>
        <p class="small-note">
          对整个合同生效，不受当前筛选或分页影响。保留已有值、已审核项与未保存修改；统一记录留空原因。至少确认一项有效填写值后，才可导出草稿。
        </p>
        <label>
          统一暂留空原因
          <input v-model="unknownReason" :disabled="busy" maxlength="2000" />
        </label>
        <button
          class="secondary"
          :disabled="busy || !unknownFields.length || !unknownReason.trim()"
          @click="ignoreUnknownFields"
        >
          一键忽略未确定空白（{{ unknownFields.length }} 项）
        </button>
        <p class="small-note">
          这是暂缓填写，不是删除条款或认定合同完整。以后取消对应项的“保留空白”，即可填写并重新确认。
        </p>
      </div>
      <div class="inline-actions review-shortcuts">
        <button class="secondary" :disabled="busy" @click="filter = 'filled'">先核对已提取</button>
        <button class="secondary" :disabled="busy" @click="filter = 'issues'">再处理缺失与分歧</button>
        <button class="secondary" :disabled="busy" @click="filter = 'table'">检查表格明细</button>
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
            busy ||
            (drafts[field.name].action === 'omit'
              ? !drafts[field.name].note.trim()
              : !drafts[field.name].value.trim())
          "
          @click="saveDecisions([field])"
        >
          {{ drafts[field.name].action === 'omit' ? '确认保留空白' : '保存并确认' }}
        </button>
      </div>
    </article>
    <p v-if="!visibleFields.length" class="empty-state">没有符合筛选条件的字段。</p>
  </section>
</template>

<!-- @file 合同工作区页面编排、导航和未保存内容保护。 -->
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { clearSession, getSession } from '../../shared/authSession'
import { postJson } from '../../shared/httpClient'
import { useContractWorkspace } from './useContractWorkspace'
import SourceImportPanel from './components/SourceImportPanel.vue'
import TemplateLibrary from './components/TemplateLibrary.vue'
import FieldReviewPanel from './components/FieldReviewPanel.vue'
import ContractPreviewPanel from './components/ContractPreviewPanel.vue'
import OperationProgress from './components/OperationProgress.vue'
import { failureGuidance } from './failureGuidance'
import './workspace.css'
import './experience.css'

const router = useRouter()
const signedInUser = getSession()?.user
const workflow = useContractWorkspace()
const {
  workspaces,
  workspace,
  systemStatus,
  preview,
  busyAction,
  error,
  errorInfo,
  failedAction,
  activity,
  elapsedSeconds,
  progressWarning,
} = workflow
const activeTab = ref('record')
const hasUnsavedFields = ref(false)
const highlightedLine = ref(null)
const tabs = [
  { id: 'record', title: '1 · 协商记录' },
  { id: 'templates', title: '2 · 选择模板' },
  { id: 'review', title: '3 · 内容审核' },
  { id: 'preview', title: '4 · 预览与导出' },
]
const stageLabels = {
  source_ready: '待分析',
  template_selection: '待选模板',
  template_selected: '待提取字段',
  field_review: '待人工审查',
  ready_to_generate: '可生成合同',
  generated: '已生成',
}
const roleLabels = {
  user: '用户',
  analysis_agent: '记录分析 Agent',
  retrieval: '模板检索',
  extraction_agent: '字段提取 Agent',
  review_agent: '独立复核 Agent',
  coverage_agent: '全合同覆盖 Agent',
  supervisor_agent: '主控协调 Agent',
  renderer: '合同生成',
}
const sourceLines = computed(() => workspace.value?.source_text.split('\n') || [])
const busy = computed(() => Boolean(busyAction.value) || activity.value?.status === 'running')
const recovery = computed(() => {
  if (error.value) return errorInfo.value || failureGuidance({ message: error.value })
  const failure = workspace.value?.extraction_failures?.[0]
  if (failure) return failureGuidance(failure.error?.code ? failure.error : { message: failure.message })
  if (workspace.value?.coverage_error?.message) return failureGuidance(workspace.value.coverage_error)
  return null
})
const retryLabel = computed(() => {
  if (!recovery.value?.retryable || busy.value) return ''
  if (
    workspace.value?.extraction_failures?.some((failure) =>
      workspace.value.fields.some(
        (field) =>
          failure.field_names?.includes(field.name) && !['confirmed', 'omitted'].includes(field.status)
      )
    )
  )
    return '重试失败批次'
  if (['failed', 'unverified', 'skipped'].includes(workspace.value?.coverage_status)) return '重试覆盖检查'
  if (workspace.value?.extraction_failures?.length) return ''
  if (failedAction.value?.includes('分析')) return '重新分析并推荐'
  if (failedAction.value?.includes('提取')) return '重新提取'
  return ''
})
/** Switch steps and load a fresh preview once all explicit review decisions are saved. */
async function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'preview' && !hasUnsavedFields.value && workspace.value?.fields.length &&
      workspace.value.fields.every((field) => ['confirmed', 'omitted'].includes(field.status)) &&
      !workspace.value.selected_template?.requires_reselection && preview.value?.revision !== workspace.value.revision) {
    await workflow.loadPreview()
  }
}

/**
 * 在离开审核草稿前询问是否放弃未保存修改。
 */
function confirmDiscard() {
  return !hasUnsavedFields.value || window.confirm('有尚未保存的字段修改，确定离开并放弃这些修改？')
}
/**
 * 核对未保存修改后切换到新的纪要导入界面。
 */
function newWorkspace() {
  if (!busy.value && confirmDiscard()) {
    workflow.reset()
    hasUnsavedFields.value = false
    activeTab.value = 'record'
  }
}
/**
 * 核对未保存修改后加载用户选择的任务。
 * @param {string} id 任务或生成文件的受控标识。
 */
async function openWorkspace(id) {
  if (busy.value || !confirmDiscard()) return
  const result = await workflow.open(id)
  if (result) {
    hasUnsavedFields.value = false
    await switchTab(['ready_to_generate', 'generated'].includes(result.stage)
      ? 'preview'
      : result.selected_template ? 'review' : result.analysis ? 'templates' : 'record')
  }
}
/**
 * 保存导入内容并把操作引导切换到新任务。
 * @param {Object} source 任务名称与原始纪要载荷。
 */
async function createWorkspace(source) {
  if (await workflow.create(source)) activeTab.value = 'record'
}
/**
 * 发起记录分析与模板检索，完成后切换到模板选择页。
 */
async function analyzeRecord() {
  const result = await workflow.analyze()
  if (result || (workspace.value && activity.value?.status !== 'running')) activeTab.value = 'templates'
}

/** 先核实服务端状态，再由用户明确重试未完成操作。 */
async function retryOperation() {
  if (hasUnsavedFields.value && !confirmDiscard()) return
  const action = failedAction.value
  const previousRevision = workspace.value.revision
  const latest = await workflow.open(workspace.value.id, true)
  if (!latest || activity.value?.status === 'running') return
  hasUnsavedFields.value = false
  if (latest.extraction_failures?.length || ['failed', 'unverified', 'skipped'].includes(latest.coverage_status)) return extractFields(true)
  if (latest.revision > previousRevision) return
  if (action?.includes('分析') && !latest.selected_template) return analyzeRecord()
  if (action?.includes('提取')) return extractFields(false)
}
/**
 * 提交用户明确选择的模板及当前修订，不自动批准填写内容。
 * @param {Object} template 用户选择的模板元数据。
 */
async function selectTemplate(template) {
  if (
    workspace.value.selected_template?.id === template.id &&
    !workspace.value.selected_template?.requires_reselection
  )
    return
  if (
    workspace.value.fields.length &&
    !window.confirm('更换模板将清除当前字段提取和审核结果，已生成版本会保留。确定更换？')
  )
    return
  if (await workflow.selectTemplate(template.id)) {
    hasUnsavedFields.value = false
    activeTab.value = 'review'
  }
}
/**
 * 核对覆盖风险后请求字段提取，完成后进入人工审核。
 * @param {boolean} retryFailed 是否仅重试未审核的失败字段。
 */
async function extractFields(retryFailed = false) {
  const reviewed = workspace.value.fields.some((field) => ['confirmed', 'omitted'].includes(field.status))
  if (
    !retryFailed &&
    (reviewed || hasUnsavedFields.value) &&
    !window.confirm('重新提取会覆盖当前填写值和人工审核结果。确定继续？')
  )
    return
  if (retryFailed && hasUnsavedFields.value && !confirmDiscard()) return
  if (await workflow.extract(!retryFailed && reviewed, retryFailed)) hasUnsavedFields.value = false
}
/**
 * 保存用户提交的字段决定并清理对应未保存提示。
 * @param {Array<Object>} decisions 用户提交的确认、修改或留空决定。
 */
async function saveFields(decisions) {
  await workflow.review(decisions)
}
/**
 * 提交当前预览版本的导出确认，生成后保留历史文件入口。
 * @param {Object} approval 用户预览及视觉核对的确认结果。
 */
async function generateContract(approval = {}) {
  if (await workflow.generate(Boolean(approval.visualReviewAcknowledged))) hasUnsavedFields.value = false
}
/**
 * 要求明确确认后删除任务，避免误删用户合同记录。
 * @param {Object} task 待删除且需核对归属的任务摘要。
 */
async function removeWorkspace(task) {
  if (busy.value || !window.confirm(`删除“${task.title}”及其协商记录、审核结果和已生成文件？`)) return
  if (await workflow.remove(task.id)) {
    if (!workspace.value) {
      hasUnsavedFields.value = false
      activeTab.value = 'record'
    }
  }
}
/**
 * 读取用户输入的新任务名称并提交修订更新。
 */
async function renameWorkspace() {
  const title = window.prompt('合同任务名称', workspace.value.title)?.trim()
  if (title && title !== workspace.value.title) await workflow.rename(title)
}
/**
 * 切换到原文视图并定位被引用行，帮助用户核验依据。
 * @param {number} line 需要定位核验的原始纪要行号。
 */
async function showSource(line) {
  activeTab.value = 'record'
  highlightedLine.value = line
  await nextTick()
  document.getElementById(`source-line-${line}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
/**
 * 下载指定历史版本，不隐式重新生成合同。
 * @param {string} id 任务或生成文件的受控标识。
 */
async function downloadArtifact(id) {
  if (busy.value) return
  await workflow.download(id)
}
/**
 * 退出当前登录会话。
 */
async function logout() {
  if (!confirmDiscard()) return
  try {
    await postJson('/auth/logout', {})
  } finally {
    clearSession()
    router.replace('/login')
  }
}
/**
 * 存在未保存审核时触发浏览器离开提醒。
 * @param {Event} event 浏览器页面生命周期事件。
 */
function beforeUnload(event) {
  if (hasUnsavedFields.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
onMounted(() => {
  workflow.initialize()
  window.addEventListener('beforeunload', beforeUnload)
})
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
</script>

<template>
  <div class="contract-app">
    <aside class="task-sidebar">
      <div class="brand">
        <span class="brand-mark">契</span>
        <div>
          <strong>ContractWeaver</strong>
          <small>CONTRACT AGENT</small>
        </div>
      </div>
      <button class="new-chat" :disabled="busy" @click="newWorkspace">＋ 新建合同任务</button>
      <div class="sidebar-label">合同任务</div>
      <nav aria-label="合同任务列表">
        <div
          v-for="task in workspaces"
          :key="task.id"
          class="task-row"
          :class="{ selected: task.id === workspace?.id }"
        >
          <button :disabled="busy" @click="openWorkspace(task.id)">
            <strong>{{ task.title }}</strong>
            <small>{{ stageLabels[task.stage] }}</small>
          </button>
          <button
            class="task-delete"
            :disabled="busy"
            :aria-label="`删除 ${task.title}`"
            @click="removeWorkspace(task)"
          >
            ×
          </button>
        </div>
        <p v-if="!workspaces.length" class="sidebar-empty">从一份聊天记录或会议纪要开始。</p>
      </nav>
      <div class="sidebar-footer">
        <span>{{ signedInUser?.email }}</span>
        <button :disabled="busy" @click="logout">退出</button>
      </div>
    </aside>
    <main class="contract-main">
      <header class="contract-header">
        <div>
          <span class="eyebrow">协商记录 → 合同填写</span>
          <h1>{{ workspace?.title || '新的合同任务' }}</h1>
        </div>
        <div class="header-actions">
          <span class="model-state">
            {{
              !systemStatus
                ? '服务状态待获取'
                : systemStatus.model_configured
                  ? `已配置模型 · ${systemStatus.model}（不代表已调用）`
                  : '模型服务待配置'
            }}
          </span>
          <button v-if="workspace" class="secondary" :disabled="busy" @click="renameWorkspace">重命名</button>
          <button
            class="secondary"
            :disabled="busy"
            @click="workspace ? openWorkspace(workspace.id) : workflow.initialize()"
          >
            刷新
          </button>
        </div>
      </header>
      <p v-if="systemStatus && !systemStatus.model_configured" class="notice">
        模型服务尚未配置。可以先保存记录、浏览并选择模板；部署者完成模型 API 配置后即可分析和提取。
      </p>
      <section v-if="recovery" class="surface recovery-notice" role="alert" aria-label="操作恢复指引">
        <h2>{{ recovery.title }}</h2>
        <p>{{ recovery.message }}</p>
        <p>{{ recovery.hint }}</p>
        <p v-if="workspace" class="small-note">已保存的协商记录与审核内容仍可继续使用。</p>
        <p v-if="retryLabel" class="small-note">重试会重新调用模型；提交前会先核实任务状态。</p>
        <div class="inline-actions">
          <button v-if="retryLabel && workspace" class="primary" :disabled="busy" @click="retryOperation">
            {{ retryLabel }}
          </button>
          <button v-if="workspace" class="secondary" :disabled="busy" @click="openWorkspace(workspace.id)">
            刷新任务状态
          </button>
          <button
            v-if="workspace && !workspace.selected_template"
            class="secondary"
            :disabled="busy"
            @click="activeTab = 'templates'"
          >
            去模板库手动选择
          </button>
          <button
            v-if="workspace?.selected_template"
            class="secondary"
            :disabled="busy"
            @click="activeTab = 'review'"
          >
            继续手动填写
          </button>
          <button v-if="!workspace" class="secondary" :disabled="busy" @click="workflow.initialize()">
            重新连接服务
          </button>
        </div>
      </section>
      <Transition name="panel">
        <OperationProgress
          v-if="busy || activity?.action"
          :label="busyAction"
          :elapsed="elapsedSeconds"
          :activity="busyAction && !/分析|提取/.test(busyAction) ? null : activity"
          :warning="progressWarning"
        />
      </Transition>
      <div v-if="!workspace" class="contract-content">
        <SourceImportPanel
          :busy="busy"
          :max-chars="systemStatus?.max_source_chars"
          :max-upload-bytes="systemStatus?.max_upload_bytes"
          @create="createWorkspace"
        />
      </div>
      <template v-else>
        <section
          v-if="activeTab === 'review' && (workspace.agent_questions?.length || workspace.coordination_warnings?.length)"
          class="surface agent-guidance"
          aria-label="主控 Agent 补充问题与运行说明"
        >
          <h2>主控 Agent 提醒</h2>
          <p v-for="warning in workspace.coordination_warnings" :key="warning" class="review-issue">
            {{ warning }}
          </p>
          <template v-if="workspace.agent_questions?.length">
            <p>
              以下信息需由你确认，可在内容审核中补充对应字段；暂无信息也可先暂留空。系统不会自动替双方决定。
            </p>
            <ul>
              <li v-for="question in workspace.agent_questions" :key="question">{{ question }}</li>
            </ul>
            <p class="small-note">问题来自本次提取快照；修改字段后请自行核对，不表示当前仍全部缺失。</p>
          </template>
        </section>
        <nav class="workflow-tabs" aria-label="合同填写步骤">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            :class="{ active: activeTab === tab.id }"
            :disabled="busy || (['review', 'preview'].includes(tab.id) && !workspace.selected_template)"
            :aria-current="activeTab === tab.id ? 'step' : undefined"
            @click="switchTab(tab.id)"
          >
            {{ tab.title }}
          </button>
          <span>{{ stageLabels[workspace.stage] }} · 版本 {{ workspace.revision }}</span>
        </nav>
        <div class="contract-content">
          <Transition name="panel">
            <section v-show="activeTab === 'record'" class="record-section">
              <div class="surface">
                <div class="section-heading">
                  <div>
                    <span class="eyebrow">记录分析 Agent</span>
                    <h2>识别交易内容与待确认事项</h2>
                  </div>
                  <button
                    class="primary"
                    :disabled="busy || !systemStatus?.model_configured || !!workspace.selected_template"
                    @click="analyzeRecord"
                  >
                    <span v-if="busyAction.includes('分析')" class="loading-spinner" aria-hidden="true" />
                    {{ workspace.analysis ? '重新分析并推荐' : '分析记录并推荐模板' }}
                  </button>
                </div>
                <p class="muted">
                  先分析记录中的交易类型和已达成事项，再检索模板。你也可以直接进入模板库手动选择。
                </p>
                <div v-if="workspace.analysis" class="analysis-result">
                  <h3>{{ workspace.analysis.contract_type }}</h3>
                  <p>{{ workspace.analysis.summary }}</p>
                  <div class="tag-list">
                    <span v-for="term in workspace.analysis.key_terms" :key="term" class="tag">
                      {{ term }}
                    </span>
                  </div>
                  <div v-if="workspace.analysis.unresolved_points.length" class="unresolved-points">
                    <strong>记录中待确认的内容</strong>
                    <p v-for="point in workspace.analysis.unresolved_points" :key="point">• {{ point }}</p>
                  </div>
                </div>
              </div>
              <div class="surface">
                <div class="section-heading">
                  <h2>原始记录 · {{ workspace.source_name }}</h2>
                  <span class="muted">{{ sourceLines.length }} 行 · 引用可定位到这里</span>
                </div>
                <div class="numbered-source">
                  <div
                    v-for="(line, index) in sourceLines"
                    :id="`source-line-${index + 1}`"
                    :key="index"
                    :class="{ highlighted: highlightedLine === index + 1 }"
                  >
                    <span>{{ index + 1 }}</span>
                    <p>{{ line || ' ' }}</p>
                  </div>
                </div>
              </div>
            </section>
          </Transition>
          <Transition name="panel">
            <TemplateLibrary
              v-show="activeTab === 'templates'"
              :key="workspace.id"
              :recommendations="workspace.recommendations"
              :selected-template="workspace.selected_template"
              :recommendation-state="
                workspace.analysis
                  ? workspace.coordination_warnings?.length
                    ? 'failed'
                    : 'empty'
                  : failedAction?.includes('分析')
                    ? 'failed'
                    : 'not_run'
              "
              :busy="busy"
              @select="selectTemplate"
            />
          </Transition>
          <Transition name="panel">
            <section v-show="activeTab === 'review'">
              <div class="surface">
                <div class="section-heading">
                  <div>
                    <span class="eyebrow">已由你选定</span>
                    <h2>{{ workspace.selected_template?.name || '先选择一份合同模板' }}</h2>
                  </div>
                  <button
                    v-if="workspace.selected_template"
                    class="primary"
                    :disabled="busy || !systemStatus?.model_configured"
                    @click="extractFields(false)"
                  >
                    <span v-if="busyAction.includes('提取')" class="loading-spinner" aria-hidden="true" />
                    {{ workspace.stage === 'template_selected' ? '按模板提取并复核字段' : '重新提取并复核' }}
                  </button>
                  <button v-else class="primary" @click="activeTab = 'templates'">去选模板</button>
                </div>
                <div v-if="workspace.selected_template?.requires_reselection" class="review-issue">
                  <p>模板填写规则已更新，需要重新载入并审核；原始记录和历史文件保留。</p>
                  <button class="primary" :disabled="busy" @click="selectTemplate(workspace.selected_template)">
                    重新载入模板
                  </button>
                </div>
                <details v-if="workspace.selected_template?.warnings?.length">
                  <summary>模板识别范围与安全提示</summary>
                  <p
                    v-for="warning in workspace.selected_template.warnings"
                    :key="warning"
                    class="small-note"
                  >
                    {{ warning }}
                  </p>
                </details>
                <div v-if="workspace.coverage_gaps?.length" class="review-issue">
                  <strong>
                    完整纪要中还有 {{ workspace.coverage_gaps.length }} 项需要核对，不能只看已填字段
                  </strong>
                  <article v-for="(gap, index) in workspace.coverage_gaps" :key="index">
                    <p>{{ gap.summary }}</p>
                    <blockquote>第 {{ gap.evidence.line_number }} 行：{{ gap.evidence.quote }}</blockquote>
                    <p>{{ gap.suggestion }}</p>
                  </article>
                  <p>这是提取时的检查快照。修改后请重新对照；不会自动替你增写条款或修改原件固定文字。</p>
                </div>
                <p
                  v-if="['failed', 'unverified', 'skipped'].includes(workspace.coverage_status)"
                  class="review-issue"
                >
                  {{
                    workspace.coverage_error?.message || '全合同覆盖检查未完成或部分引用未通过核验'
                  }}。请人工对照全部纪要。
                </p>
                <div v-if="workspace.extraction_failures?.length" class="review-issue">
                  <strong>
                    {{ workspace.extraction_failures.length }}
                    个批次未完成；已保存的成功结果和人工审核可继续使用。
                  </strong>
                  <p v-for="(failure, index) in workspace.extraction_failures" :key="index">
                    {{ failure.field_names.length }} 个字段：{{ failure.message }}
                  </p>
                  <button
                    class="secondary"
                    :disabled="busy || !systemStatus?.model_configured"
                    @click="extractFields(true)"
                  >
                    仅重试失败批次（跳过已人工审核字段）
                  </button>
                </div>
              </div>
              <FieldReviewPanel
                v-if="workspace.fields.length"
                :key="workspace.id"
                :fields="workspace.fields"
                :busy="busy"
                @save="saveFields"
                @source="showSource"
                @dirty="hasUnsavedFields = $event"
              />
            </section>
          </Transition>
          <Transition name="panel">
            <ContractPreviewPanel
              v-show="activeTab === 'preview'"
              :workspace="workspace"
              :preview="preview"
              :busy="busy"
              :unsaved="hasUnsavedFields"
              @preview="workflow.loadPreview"
              @generate="generateContract"
              @download="downloadArtifact"
              @back-review="activeTab = 'review'"
            />
          </Transition>
          <details class="surface workflow-audit">
            <summary>查看任务执行记录 · {{ workspace.events.length }} 条</summary>
            <ol>
              <li v-for="(event, index) in [...workspace.events].reverse()" :key="index">
                <strong>{{ roleLabels[event.role] || event.role }}</strong>
                <span>{{ event.detail }}</span>
                <time>{{ new Date(event.created_at).toLocaleString() }}</time>
              </li>
            </ol>
          </details>
        </div>
      </template>
    </main>
  </div>
</template>

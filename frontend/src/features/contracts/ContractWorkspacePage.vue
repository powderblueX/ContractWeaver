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
  { id: 'review', title: '3 · 字段审查' },
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
const reviewedCount = computed(
  () => workspace.value?.fields.filter((field) => ['confirmed', 'omitted'].includes(field.status)).length || 0
)
const sourceLines = computed(() => workspace.value?.source_text.split('\n') || [])
const fieldCounts = computed(() => ({
  filled:
    workspace.value?.fields.filter((field) => field.value && !['confirmed', 'omitted'].includes(field.status))
      .length || 0,
  missing: workspace.value?.fields.filter((field) => field.status === 'missing').length || 0,
  conflict:
    workspace.value?.fields.filter((field) => ['conflict', 'unverified'].includes(field.status)).length || 0,
}))
const busy = computed(() => Boolean(busyAction.value) || activity.value?.status === 'running')
const nextStep = computed(() => {
  const stage = workspace.value?.stage
  if (workspace.value?.selected_template?.requires_reselection)
    return {
      title: '填写规则已更新，请重新载入模板',
      detail:
        '旧字段存在重复、日期或选项映射风险，不能继续导出。重新载入会重置字段审核；原始纪要和历史文件保留，旧文件不会自动修复。',
      button: '重新载入当前模板并开始审核',
      action: 'reload-template',
    }
  if (stage === 'source_ready')
    return {
      title: '下一步：分析这份记录',
      detail: '让模型识别交易、最终约定与待确认事项，再推荐模板。也可手动选择模板。',
      button: '分析记录并推荐模板',
      action: 'analyze',
    }
  if (stage === 'template_selection')
    return {
      title: '下一步：由你选定合同模板',
      detail: '推荐只是候选。先查看原件，确认类型与版本，再选择；不合适可搜索完整模板库。',
      button: '查看候选与模板库',
      action: 'templates',
    }
  if (stage === 'template_selected')
    return {
      title: '下一步：从记录提取填写内容',
      detail: '你刚选择了模板，还没有提取。点击后可看到模型请求与每批进展。',
      button: '按模板提取并复核字段',
      action: 'extract',
    }
  if (stage === 'field_review')
    return {
      title: `下一步：审核填写内容（还剩 ${(workspace.value?.fields.length || 0) - reviewedCount.value} 项）`,
      detail: '核对并确认已有值；纪要不完整时，可一键将未确定空白暂留空，先生成待完善草稿，后续再补充。',
      button: '进入内容审核',
      action: 'review',
    }
  return {
    title: '审核已完成，可以检查最终合同',
    detail: '载入填写后的预览，核对内容和版面说明，再确认生成 DOCX。',
    button: '查看最终预览',
    action: 'preview',
  }
})
async function continueWorkflow() {
  if (nextStep.value.action === 'reload-template') return selectTemplate(workspace.value.selected_template)
  if (nextStep.value.action === 'analyze') return analyzeRecord()
  if (nextStep.value.action === 'extract') return extractFields(false)
  activeTab.value = nextStep.value.action
  if (activeTab.value === 'preview') await workflow.loadPreview()
}

function confirmDiscard() {
  return !hasUnsavedFields.value || window.confirm('有尚未保存的字段修改，确定离开并放弃这些修改？')
}
function newWorkspace() {
  if (!busy.value && confirmDiscard()) {
    workflow.reset()
    hasUnsavedFields.value = false
    activeTab.value = 'record'
  }
}
async function openWorkspace(id) {
  if (busy.value || !confirmDiscard()) return
  const result = await workflow.open(id)
  if (result) {
    hasUnsavedFields.value = false
    activeTab.value = ['ready_to_generate', 'generated'].includes(result.stage)
      ? 'preview'
      : result.fields.length
        ? 'review'
        : result.selected_template
          ? 'review'
          : result.analysis
            ? 'templates'
            : 'record'
  }
}
async function createWorkspace(source) {
  if (await workflow.create(source)) activeTab.value = 'record'
}
async function analyzeRecord() {
  if (await workflow.analyze()) activeTab.value = 'templates'
}
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
async function saveFields(decisions) {
  await workflow.review(decisions)
}
async function generateContract(approval = {}) {
  if (await workflow.generate(Boolean(approval.visualReviewAcknowledged))) hasUnsavedFields.value = false
}
async function removeWorkspace(task) {
  if (busy.value || !window.confirm(`删除“${task.title}”及其协商记录、审核结果和已生成文件？`)) return
  if (await workflow.remove(task.id)) {
    if (!workspace.value) {
      hasUnsavedFields.value = false
      activeTab.value = 'record'
    }
  }
}
async function renameWorkspace() {
  const title = window.prompt('合同任务名称', workspace.value.title)?.trim()
  if (title && title !== workspace.value.title) await workflow.rename(title)
}
async function showSource(line) {
  activeTab.value = 'record'
  highlightedLine.value = line
  await nextTick()
  document.getElementById(`source-line-${line}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
async function downloadArtifact(id) {
  if (busy.value) return
  await workflow.download(id)
}
async function logout() {
  if (!confirmDiscard()) return
  try {
    await postJson('/auth/logout', {})
  } finally {
    clearSession()
    router.replace('/login')
  }
}
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
      <div v-if="error" class="error-banner" role="alert">
        {{ error }}
        <button aria-label="关闭错误提示" @click="error = ''">×</button>
      </div>
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
          v-if="workspace.agent_questions?.length || workspace.coordination_warnings?.length"
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
        <section class="next-step-card" aria-live="polite">
          <div>
            <span class="eyebrow">操作指引</span>
            <h2>{{ nextStep.title }}</h2>
            <p>{{ nextStep.detail }}</p>
          </div>
          <button
            class="primary"
            :disabled="
              busy || (['analyze', 'extract'].includes(nextStep.action) && !systemStatus?.model_configured)
            "
            @click="continueWorkflow"
          >
            {{ nextStep.button }}
          </button>
        </section>
        <nav class="workflow-tabs" aria-label="合同填写步骤">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            :class="{ active: activeTab === tab.id }"
            :disabled="busy || (['review', 'preview'].includes(tab.id) && !workspace.selected_template)"
            :aria-current="activeTab === tab.id ? 'step' : undefined"
            @click="activeTab = tab.id"
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
                <p class="muted">
                  字段提取 Agent 从原记录查找对应内容，独立复核 Agent 检查分歧与依据。请逐项确认、修正或补充。
                </p>
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
                <p v-if="workspace.selected_template" class="small-note">
                  模板有 {{ workspace.fields.length }} 个字段，完整提取分
                  {{ Math.ceil(workspace.fields.length / (systemStatus?.fields_per_batch || 30)) }}
                  批，基础模型请求约
                  {{ Math.ceil(workspace.fields.length / (systemStatus?.fields_per_batch || 30)) * 2 + 1 }}
                  次（含一次全合同覆盖检查，格式重试另计）。也可以直接人工填写。
                </p>
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
                <p v-if="['failed', 'unverified'].includes(workspace.coverage_status)" class="review-issue">
                  全合同覆盖检查未完成或部分引用未通过核验，请人工对照全部纪要，不要将当前字段视作完整覆盖。
                </p>
                <div v-if="workspace.extraction_failures?.length" class="review-issue">
                  <strong>
                    {{ workspace.extraction_failures.length }} 个批次未完成，其余成功结果已保存。
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
                <div v-if="workspace.fields.length" class="review-progress">
                  <span :style="{ width: `${(reviewedCount / workspace.fields.length) * 100}%` }" />
                </div>
                <div v-if="workspace.fields.length" class="inline-actions">
                  <span class="muted">{{ reviewedCount }} / {{ workspace.fields.length }} 项已审核</span>
                  <button class="secondary" @click="activeTab = 'preview'">查看合同预览 →</button>
                </div>
              </div>
              <div v-if="workspace.fields.length" class="review-stat-strip" aria-label="审核概览">
                <span>
                  <strong>{{ fieldCounts.filled }}</strong>
                  项有值待核对
                </span>
                <span>
                  <strong>{{ fieldCounts.missing }}</strong>
                  项待补充或判断留空
                </span>
                <span>
                  <strong>{{ fieldCounts.conflict }}</strong>
                  项有分歧或依据待核验
                </span>
                <span>
                  <strong>{{ reviewedCount }}</strong>
                  项已审核
                </span>
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
              :busy="busy || hasUnsavedFields"
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

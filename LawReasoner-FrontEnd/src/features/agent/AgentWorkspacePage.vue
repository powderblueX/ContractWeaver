<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { requestJson, downloadContract, postJson } from '../../shared/httpClient'
import { clearSession, getSession } from '../../shared/authSession'

const router = useRouter()
const signedInUser = getSession()?.user
const conversationSessions = ref([])
const activeSessionId = ref(null)
const messages = ref([])
const draftMessage = ref('')
const allowDraft = ref(false)
const busy = ref(false)
const error = ref('')
const modelConfigured = ref(false)
const suggestions = [
  '房屋租赁纠纷中，押金不退有哪些法律依据？请引用民法典条文。',
  '我准备签订设备买卖合同，请帮我查找合适的合同模板。',
  '请分析这起民事纠纷的争议焦点、适用条款和待补充证据。',
]
const currentSession = computed(() => conversationSessions.value.find((item) => item.id === activeSessionId.value))

function citedArticles(trace) {
  const articles = new Map()
  for (const step of trace || []) {
    if (!['lookup_civil_code', 'search_civil_code'].includes(step.tool)) continue
    for (const item of Array.isArray(step.result) ? step.result : [step.result]) {
      if (item?.article && item?.text) articles.set(item.article, item)
    }
  }
  return [...articles.values()]
}

async function loadSessions() { conversationSessions.value = await requestJson('/agent/sessions') }

async function openSession(id) {
  error.value = ''
  activeSessionId.value = id
  const history = id ? (await requestJson(`/agent/sessions/${id}`)).messages : []
  messages.value = history.map((message) => ({
    role: message.role,
    content: message.content,
    trace: message.trace || [],
    evidence: citedArticles(message.trace),
    artifacts: (message.trace || []).filter((step) => step.tool === 'draft_contract' && step.result?.id).map((step) => step.result),
  }))
}

async function sendMessage() {
  const message = draftMessage.value.trim()
  if (!message || busy.value) return
  draftMessage.value = ''
  error.value = ''
  busy.value = true
  messages.value.push({ role: 'user', content: message })
  try {
    const result = await postJson('/agent/runs', { message, session_id: activeSessionId.value, allow_draft: allowDraft.value })
    activeSessionId.value = result.session_id
    messages.value.push({ role: 'assistant', content: result.answer, trace: result.trace, artifacts: result.artifacts, evidence: result.evidence })
    await loadSessions()
  } catch (reason) {
    error.value = reason.message
    draftMessage.value = message
    messages.value.pop()
  } finally {
    busy.value = false
    allowDraft.value = false
  }
}

async function removeSession(id) {
  if (!window.confirm('删除此对话及历史消息？')) return
  try {
    await requestJson(`/agent/sessions/${id}`, { method: 'DELETE' })
    if (activeSessionId.value === id) await openSession(null)
    await loadSessions()
  } catch (reason) { error.value = reason.message }
}

async function renameSession(session) {
  const title = window.prompt('修改对话标题', session.title)?.trim()
  if (!title || title === session.title) return
  try {
    await requestJson(`/agent/sessions/${session.id}`, { method: 'PATCH', body: JSON.stringify({ title }) })
    await loadSessions()
  } catch (reason) { error.value = reason.message }
}

async function logout() {
  try { await postJson('/auth/logout', {}) } finally {
    clearSession()
    router.replace('/login')
  }
}

async function download(id) {
  try { await downloadContract(id) } catch (reason) { error.value = reason.message }
}

onMounted(async () => {
  try {
    await loadSessions()
    modelConfigured.value = (await requestJson('/health')).model_configured
  } catch (reason) { error.value = reason.message }
})
</script>

<template>
  <div class="workspace">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark">法</span><div><strong>法理智推</strong><small>LEGAL AGENT</small></div></div>
      <button class="new-chat" @click="openSession(null)">＋ 新建对话</button>
      <div class="sidebar-label">最近的对话</div>
      <nav aria-label="对话列表">
        <div v-for="session in conversationSessions" :key="session.id" class="session-row" :class="{ selected: activeSessionId === session.id }">
          <button @click="openSession(session.id)">{{ session.title }}</button>
          <button class="rename" :aria-label="`重命名 ${session.title}`" @click="renameSession(session)">✎</button>
          <button class="remove" :aria-label="`删除 ${session.title}`" @click="removeSession(session.id)">×</button>
        </div>
      </nav>
      <div class="sidebar-footer"><span>{{ signedInUser?.username }}</span><button @click="logout">退出</button></div>
    </aside>

    <main class="conversation">
      <header class="topbar"><div><span class="eyebrow">AGENT WORKSPACE</span><h2>{{ currentSession?.title || '新的法律问题' }}</h2></div><span class="status-dot">{{ modelConfigured ? 'Agent 已就绪' : '模型待配置' }}</span></header>
      <section class="thread" aria-live="polite">
        <div v-if="!messages.length" class="welcome">
          <div class="welcome-mark">法</div><span class="eyebrow">一步一步，有据可查</span>
          <h1>你想解决什么法律问题？</h1>
          <p>描述案情、查找《民法典》条文，或说明合同需求。Agent 会按需要调用法条与合同工具，并展示依据和执行过程。</p>
          <div class="suggestions"><button v-for="item in suggestions" :key="item" @click="draftMessage = item">{{ item }} <span>↗</span></button></div>
        </div>
        <article v-for="(message, index) in messages" :key="index" class="message" :class="message.role">
          <div class="avatar">{{ message.role === 'user' ? '我' : '法' }}</div>
          <div class="message-body"><div class="message-label">{{ message.role === 'user' ? '你' : '法理智推 Agent' }}</div><div class="message-content">{{ message.content }}</div>
            <div v-if="message.evidence?.length" class="evidence"><strong>已核验法条</strong>
              <details v-for="article in message.evidence" :key="article.article"><summary>《民法典》第{{ article.article }}条</summary><p>{{ article.text }}</p></details>
            </div>
            <details v-if="message.trace?.length" class="trace"><summary>查看 Agent 执行过程 · {{ message.trace.length }} 步</summary>
              <div v-for="(step, stepIndex) in message.trace" :key="stepIndex" class="trace-step"><strong>{{ step.tool }}</strong><pre>{{ JSON.stringify(step.result, null, 2) }}</pre></div>
            </details>
            <div v-if="message.artifacts?.length" class="artifacts"><button v-for="artifact in message.artifacts" :key="artifact.id" @click="download(artifact.id)">下载 {{ artifact.template.name }}.docx</button><small>未填写字段需人工核对后使用</small></div>
          </div>
        </article>
        <div v-if="busy" class="working">Agent 正在分析并选择工具…</div>
      </section>
      <div class="composer-wrap"><p v-if="error" class="error" role="alert">{{ error }}</p><form class="composer" @submit.prevent="sendMessage"><textarea v-model="draftMessage" rows="3" placeholder="描述案情，或提出合同需求…" @keydown.ctrl.enter.prevent="sendMessage" /><div class="composer-actions"><label class="draft-toggle"><input v-model="allowDraft" type="checkbox" />本次允许生成合同文件</label><button class="primary" :disabled="busy || !draftMessage.trim()">{{ busy ? '处理中…' : '发送 ↗' }}</button></div></form><div class="composer-note">法律分析与合同草稿仅供辅助参考；请核对事实、法条及所有未填写字段。</div></div>
    </main>
  </div>
</template>

/** Keep remote workflow state separate from page navigation and editable forms. */
import { ref, getCurrentScope, onScopeDispose } from 'vue'
import { contractApi } from './contractApi'

export function useContractWorkspace() {
  const workspaces = ref([])
  const workspace = ref(null)
  const systemStatus = ref(null)
  const preview = ref(null)
  const busyAction = ref('')
  const error = ref('')
  const activity = ref(null)
  const elapsedSeconds = ref(0)
  const progressWarning = ref('')
  let progressTimer = null
  let progressController = null
  let pollInFlight = false
  let operationSequence = 0

  function stopProgress() {
    clearInterval(progressTimer)
    progressTimer = null
    progressController?.abort()
    progressController = null
  }
  async function fetchProgress(sequence, id) {
    if (pollInFlight || !contractApi.activity) return
    pollInFlight = true
    const controller = new AbortController()
    progressController = controller
    let timedOut = false
    const timeout = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 4000)
    try {
      const result = await contractApi.activity(id, controller.signal)
      if (sequence === operationSequence) {
        activity.value = result
        progressWarning.value = ''
      }
    } catch (reason) {
      if (sequence === operationSequence && (timedOut || reason.name !== 'AbortError'))
        progressWarning.value = '进度暂时不可达；主请求仍在等待，未伪造完成百分比。'
    } finally {
      clearTimeout(timeout)
      pollInFlight = false
    }
  }
  if (getCurrentScope())
    onScopeDispose(() => {
      operationSequence++
      stopProgress()
    })

  function followRunningOperation() {
    const sequence = operationSequence
    const id = workspace.value?.id
    if (!id || !contractApi.activity) return
    progressTimer = setInterval(async () => {
      if (pollInFlight) return
      await fetchProgress(sequence, id)
      if (sequence !== operationSequence || activity.value?.status === 'running') return
      stopProgress()
      try {
        workspace.value = await contractApi.get(id)
        preview.value = null
        await refreshList()
      } catch {
        progressWarning.value = '操作状态已更新，但结果读取失败，请刷新任务。'
      }
    }, 1000)
  }

  async function perform(label, operation, observe = false) {
    if (busyAction.value) return null
    busyAction.value = label
    error.value = ''
    progressWarning.value = ''
    elapsedSeconds.value = 0
    const sequence = ++operationSequence
    const started = Date.now()
    const id = workspace.value?.id
    if (observe) activity.value = null
    progressTimer = setInterval(() => {
      elapsedSeconds.value = Math.floor((Date.now() - started) / 1000)
      if (observe && id) fetchProgress(sequence, id)
    }, 1000)
    try {
      return await operation()
    } catch (reason) {
      error.value = reason.message
      return null
    } finally {
      stopProgress()
      busyAction.value = ''
      if (activity.value?.status === 'running') followRunningOperation()
    }
  }

  async function refreshList() {
    workspaces.value = await contractApi.list()
  }

  async function mutate(label, operation, observe = false) {
    return perform(
      label,
      async () => {
        const updated = await operation()
        workspace.value = updated
        if (updated.last_run) activity.value = updated.last_run
        preview.value = null
        // A list refresh failure must not make a successful mutation look rolled back.
        try {
          await refreshList()
        } catch {
          error.value = '操作已保存，但任务列表刷新失败，请稍后刷新。'
        }
        return updated
      },
      observe
    )
  }

  return {
    workspaces,
    workspace,
    systemStatus,
    preview,
    busyAction,
    error,
    activity,
    elapsedSeconds,
    progressWarning,
    initialize: () =>
      perform('加载任务', async () => {
        const [tasks, status] = await Promise.all([contractApi.list(), contractApi.health()])
        workspaces.value = tasks
        systemStatus.value = status
        return true
      }),
    open: (id) =>
      mutate('打开任务', async () => {
        const task = await contractApi.get(id)
        if (contractApi.activity) {
          try {
            const live = await contractApi.activity(id)
            if (live?.action) task.last_run = live
          } catch {
            progressWarning.value = '暂时无法读取执行进度，请稍后刷新。'
          }
        }
        return task
      }),
    create: (source) => mutate('保存协商记录', () => contractApi.create(source)),
    analyze: () => mutate('分析记录并检索模板', () => contractApi.analyze(workspace.value), true),
    selectTemplate: (templateId) =>
      mutate('选择模板', () => contractApi.selectTemplate(workspace.value, templateId)),
    extract: (replaceReviewed = false, retryFailed = false) =>
      mutate(
        '提取并复核字段',
        () => contractApi.extract(workspace.value, replaceReviewed, retryFailed),
        true
      ),
    review: (decisions) => mutate('保存字段审核', () => contractApi.review(workspace.value, decisions)),
    rename: (title) => mutate('修改任务名称', () => contractApi.rename(workspace.value, title)),
    generate: (visualReviewAcknowledged = false) =>
      mutate('生成合同', () => contractApi.generate(workspace.value, visualReviewAcknowledged)),
    download: (id) => perform('下载合同', () => contractApi.download(id)),
    loadPreview: () =>
      perform('生成文字预览', async () => {
        preview.value = await contractApi.preview(workspace.value)
        return preview.value
      }),
    remove: (id) =>
      perform('删除任务', async () => {
        await contractApi.remove(id)
        if (workspace.value?.id === id) {
          workspace.value = null
          preview.value = null
        }
        await refreshList()
        return true
      }),
    reset: () => {
      operationSequence++
      stopProgress()
      workspace.value = null
      preview.value = null
      error.value = ''
      activity.value = null
    },
  }
}

/** @file 服务端任务状态与异步操作控制，不与字段本地草稿混用。 */
import { ref, getCurrentScope, onScopeDispose } from 'vue'
import { contractApi } from './contractApi'

/**
 * 集中管理服务端快照、异步操作和进度轮询，页面草稿由子组件单独持有。
 */
export function useContractWorkspace() {
  const workspaces = ref([])
  const workspace = ref(null)
  // 服务端已提交快照与预览分开保存；每次变更使旧预览失效，字段编辑草稿由审核组件持有。
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
  // 请求序号防止切换任务后迟到的进度响应污染当前任务；取消轮询不等于取消后端任务。

  /**
   * 清理进度定时器并取消正在读取的进度请求，不伪称终止后端任务。
   */
  function stopProgress() {
    clearInterval(progressTimer)
    progressTimer = null
    progressController?.abort()
    progressController = null
  }
  /**
   * 在请求序号仍有效时更新进度，防止旧任务响应污染当前页面。
   * @param {number} sequence 本次操作绑定的页面请求序号。
   * @param {string} id 任务或生成文件的受控标识。
   */
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

  /**
   * 主请求结束但服务端仍运行时继续观察，终态后重新读取任务。
   */
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

  /**
   * 为界面操作提供单一等待、错误与清理出口，不把轮询异常当作业务失败。
   * @param {string} label 向用户展示的等待状态名称。
   * @param {Function} operation 实际执行的异步业务操作。
   * @param {boolean} observe 是否开启服务端进度轮询。
   */
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

  /**
   * 刷新当前账户的任务摘要，不修改当前字段草稿。
   */
  async function refreshList() {
    workspaces.value = await contractApi.list()
  }

  /**
   * 先保存成功返回的任务快照，再刷新目录；目录刷新失败不撤销已提交操作。
   * @param {string} label 向用户展示的等待状态名称。
   * @param {Function} operation 实际执行的异步业务操作。
   * @param {boolean} observe 是否开启服务端进度轮询。
   */
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
    /**
     * 并行读取任务列表与公开配置，初始化工作区。
     */
    initialize: () =>
      perform('加载任务', async () => {
        const [tasks, status] = await Promise.all([contractApi.list(), contractApi.health()])
        workspaces.value = tasks
        systemStatus.value = status
        return true
      }),
    /**
     * 打开任务并尝试补读持久进度，进度读取失败仍保留任务。
     * @param {string} id 任务或生成文件的受控标识。
     */
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
    /**
     * 保存新的原始纪要与任务名称。
     * @param {Object} source 任务名称与原始纪要载荷。
     */
    create: (source) => mutate('保存协商记录', () => contractApi.create(source)),
    /**
     * 请求主控分析并检索模板，携带当前任务修订号。
     */
    analyze: () => mutate('分析记录并检索模板', () => contractApi.analyze(workspace.value), true),
    /**
     * 提交用户明确选择的模板及当前修订，不自动批准填写内容。
     * @param {string} templateId 用户选定的模板标识。
     */
    selectTemplate: (templateId) =>
      mutate('选择模板', () => contractApi.selectTemplate(workspace.value, templateId)),
    /**
     * 请求提取与复核，区分覆盖人工结果和仅重试失败批次。
     * @param {boolean} replaceReviewed 是否明确允许覆盖已有人工审核。
     * @param {boolean} retryFailed 是否仅重试未审核的失败字段。
     */
    extract: (replaceReviewed = false, retryFailed = false) =>
      mutate(
        '提取并复核字段',
        () => contractApi.extract(workspace.value, replaceReviewed, retryFailed),
        true
      ),
    /**
     * 以当前修订批量保存用户的字段审核决定。
     * @param {Array<Object>} decisions 用户提交的确认、修改或留空决定。
     */
    review: (decisions) => mutate('保存字段审核', () => contractApi.review(workspace.value, decisions)),
    /**
     * 以当前修订更新任务名称，避免陈旧页面覆盖。
     * @param {string} title 用户指定的任务名称。
     */
    rename: (title) => mutate('修改任务名称', () => contractApi.rename(workspace.value, title)),
    /**
     * 提交预览及可选视觉复核确认，仍由服务端验证全部导出条件。
     * @param {boolean} visualReviewAcknowledged 是否单独确认已核对原件图形区域。
     */
    generate: (visualReviewAcknowledged = false) =>
      mutate('生成合同', () => contractApi.generate(workspace.value, visualReviewAcknowledged)),
    /**
     * 通过认证下载已生成合同，不触发新的模型请求。
     * @param {string} id 任务或生成文件的受控标识。
     */
    download: (id) => perform('下载合同', () => contractApi.download(id)),
    /**
     * 读取当前版本的文字预览，保存到独立预览状态。
     */
    loadPreview: () =>
      perform('生成文字预览', async () => {
        preview.value = await contractApi.preview(workspace.value)
        return preview.value
      }),
    /**
     * 删除指定任务及其生成文件，保留原始模板库。
     * @param {string} id 任务或生成文件的受控标识。
     */
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
    /**
     * 使旧轮询失效并清理当前页面状态，不删除服务端任务。
     */
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

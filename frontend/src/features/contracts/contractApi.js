/** @file 与后端显式工作流转换对应的 HTTP 接口门面。 */
import { requestJson, postJson, downloadContract } from '../../shared/httpClient'

/**
 * 对任务标识进行 URL 编码，统一生成任务接口路径。
 * @param {string} id 任务或生成文件的受控标识。
 */
const workspacePath = (id) => `/workspaces/${encodeURIComponent(id)}`

export const contractApi = {
  /**
   * 读取公开服务状态和限制，不接触后端模型密钥。
   */
  health: () => requestJson('/health'),
  /**
   * 通过认证下载已生成合同，不触发新的模型请求。
   * @param {string} id 任务或生成文件的受控标识。
   */
  download: (id) => downloadContract(id),
  /**
   * 读取当前账户的任务摘要。
   */
  list: () => requestJson('/workspaces'),
  /**
   * 读取当前账户拥有的指定任务快照。
   * @param {string} id 任务或生成文件的受控标识。
   */
  get: (id) => requestJson(workspacePath(id)),
  /**
   * 读取可取消的任务进度，轮询失败不代表主请求已失败。
   * @param {string} id 任务或生成文件的受控标识。
   * @param {AbortSignal} signal 用于取消进度读取的信号。
   */
  activity: (id, signal) => requestJson(`${workspacePath(id)}/activity`, { signal }),
  /**
   * 保存新的原始纪要与任务名称。
   * @param {Object} source 任务名称与原始纪要载荷。
   */
  create: (source) => postJson('/workspaces', source),
  /**
   * 请求主控分析并检索模板，携带当前任务修订号。
   * @param {Object} workspace 含任务标识和修订号的服务端快照。
   */
  analyze: (workspace) =>
    postJson(`${workspacePath(workspace.id)}/analyze`, { revision: workspace.revision }),
  /**
   * 提交用户明确选择的模板及当前修订，不自动批准填写内容。
   * @param {Object} workspace 含任务标识和修订号的服务端快照。
   * @param {string} templateId 用户明确选择的模板标识。
   */
  selectTemplate: (workspace, templateId) =>
    postJson(`${workspacePath(workspace.id)}/template`, {
      revision: workspace.revision,
      template_id: templateId,
    }),
  /**
   * 请求提取与复核，区分覆盖人工结果和仅重试失败批次。
   * @param {Object} workspace 含任务标识和修订号的服务端快照。
   * @param {boolean} replaceReviewed 是否明确允许覆盖既有人工审核。
   * @param {boolean} retryFailed 是否仅重试未审核的失败字段。
   */
  extract: (workspace, replaceReviewed, retryFailed) =>
    postJson(`${workspacePath(workspace.id)}/extract`, {
      revision: workspace.revision,
      replace_reviewed: replaceReviewed,
      retry_failed: retryFailed,
    }),
  /**
   * 以当前修订批量保存用户的字段审核决定。
   * @param {Object} workspace 含任务标识和修订号的服务端快照。
   * @param {Array<Object>} decisions 用户确认、修改或留空的字段决定。
   */
  review: (workspace, decisions) =>
    requestJson(`${workspacePath(workspace.id)}/fields`, {
      method: 'PATCH',
      body: JSON.stringify({ revision: workspace.revision, decisions }),
    }),
  /**
   * 读取当前审核值生成的文字预览，不冒充 Word 页面渲染。
   * @param {Object} workspace 含任务标识和修订号的服务端快照。
   */
  preview: (workspace) => requestJson(`${workspacePath(workspace.id)}/preview`),
  /**
   * 提交预览及可选视觉复核确认，仍由服务端验证全部导出条件。
   * @param {Object} workspace 含任务标识和修订号的服务端快照。
   * @param {boolean} visualReviewAcknowledged 是否已额外核对原件的图形区域。
   */
  generate: (workspace, visualReviewAcknowledged = false) =>
    postJson(`${workspacePath(workspace.id)}/generate`, {
      revision: workspace.revision,
      preview_acknowledged: true,
      visual_review_acknowledged: visualReviewAcknowledged,
    }),
  /**
   * 以当前修订更新任务名称，避免陈旧页面覆盖。
   * @param {Object} workspace 含任务标识和修订号的服务端快照。
   * @param {string} title 用户指定的任务名称。
   */
  rename: (workspace, title) =>
    requestJson(workspacePath(workspace.id), {
      method: 'PATCH',
      body: JSON.stringify({ revision: workspace.revision, title }),
    }),
  /**
   * 删除指定任务及其生成文件，保留原始模板库。
   * @param {string} id 任务或生成文件的受控标识。
   */
  remove: (id) => requestJson(workspacePath(id), { method: 'DELETE' }),
  /**
   * 按筛选条件读取完整模板库分页。
   * @param {Object} filters 模板名称、分类和分页条件。
   */
  browseTemplates: (filters) => requestJson(`/contracts/templates?${new URLSearchParams(filters)}`),
  /**
   * 读取原件字段、安全提示与支持范围。
   * @param {string} id 任务或生成文件的受控标识。
   */
  templateDetails: (id) => requestJson(`/contracts/templates/${encodeURIComponent(id)}`),
  /**
   * 以 multipart 上传纪要文件，交服务端限制大小并解析。
   * @param {File} file 经过大小检查的纪要文件。
   */
  parseSource: (file) => {
    const body = new FormData()
    body.append('file', file)
    return requestJson('/sources/parse', { method: 'POST', body })
  },
}

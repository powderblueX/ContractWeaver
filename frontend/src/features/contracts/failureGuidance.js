/** @file 将公开错误分类转换为可操作的恢复说明。 */

/** 根据服务端分类、HTTP 状态和浏览器网络错误生成提示。 */
export function failureGuidance(reason) {
  const detail = reason?.error || reason || {}
  const code = detail.code || (reason?.status >= 500 ? 'service_unavailable' : 'request_failed')
  const network = ['browser_network', 'model_network', 'model_timeout'].includes(code)
  const configuration = ['model_config', 'model_auth', 'model_endpoint', 'model_format'].includes(code)
  return {
    code,
    title: network ? '连接暂时中断' : configuration ? '模型服务需要维护者检查' : '本次操作未完成',
    message: detail.message || '服务暂时无法完成请求。',
    hint:
      detail.hint ||
      (reason?.status === 409
        ? '任务可能仍在处理或已更新。请先刷新任务状态，再决定是否重新操作。'
        : reason?.status >= 500
          ? '请稍后重试；持续失败时联系服务维护者。'
          : '请核对提示中的信息后重新操作。'),
    retryable: detail.retryable !== false && reason?.status !== 409,
  }
}

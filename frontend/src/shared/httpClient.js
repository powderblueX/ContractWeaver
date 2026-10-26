/** @file 后端 API 请求与文件下载。 */
import { clearSession, getSession } from './authSession'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
// 前端只配置业务 API 地址。

/** 发送带登录会话的 API 请求。 */
async function authenticatedFetch(path, options = {}) {
  const session = getSession()
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(typeof options.body === 'string' ? { 'Content-Type': 'application/json' } : {}),
      ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
      ...options.headers,
    },
  })
  if (response.status === 401 && session && !path.startsWith('/auth/login')) {
    clearSession()
    window.location.assign('/login')
    throw new Error('登录已过期，请重新登录')
  }
  if (!response.ok) {
    let detail = '请求失败'
    try {
      detail = (await response.json()).detail || detail
    } catch {
      /* Keep fallback for non-JSON errors. */
    }
    const error = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    error.status = response.status
    throw error
  }
  return response
}

/**
 * 发送认证请求并解析 JSON 结果。
 * @param {string} path 相对 API 基础地址的受控路径。
 * @param {Object} options 当前操作的选项或解构参数。
 */
export async function requestJson(path, options = {}) {
  return (await authenticatedFetch(path, options)).json()
}

/**
 * 把公开业务载荷编码为 JSON 后发送 POST 请求。
 * @param {string} path 相对 API 基础地址的受控路径。
 * @param {Object} payload 编码为 JSON 的公开业务数据。
 */
export function postJson(path, payload) {
  return requestJson(path, { method: 'POST', body: JSON.stringify(payload) })
}

/**
 * 按受控生成标识下载合同并提供可读文件名。
 * @param {string} id 任务或生成文件的受控标识。
 */
export async function downloadContract(id) {
  return downloadFile(`/contracts/${encodeURIComponent(id)}/download`, `合同_${id.slice(0, 8)}.docx`)
}

/**
 * 下载二进制文件并及时释放浏览器临时 URL。
 * @param {string} path 相对 API 基础地址的受控路径。
 * @param {string} filename 建议保存的文件名。
 */
export async function downloadFile(path, filename) {
  const response = await authenticatedFetch(path)
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

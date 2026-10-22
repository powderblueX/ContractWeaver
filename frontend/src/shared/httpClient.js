import { clearSession, getSession } from './authSession'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

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

export async function requestJson(path, options = {}) {
  return (await authenticatedFetch(path, options)).json()
}

export function postJson(path, payload) {
  return requestJson(path, { method: 'POST', body: JSON.stringify(payload) })
}

export async function downloadContract(id) {
  return downloadFile(`/contracts/${encodeURIComponent(id)}/download`, `合同_${id.slice(0, 8)}.docx`)
}

export async function downloadFile(path, filename) {
  const response = await authenticatedFetch(path)
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

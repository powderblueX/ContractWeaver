/** @file 浏览器认证会话管理。 */
const AUTH_SESSION_KEY = 'contractweaver.session'
// 登录会话保存在当前标签页的 sessionStorage 中。

/** 读取有效登录会话。 */
export function getSession() {
  try {
    const session = JSON.parse(sessionStorage.getItem(AUTH_SESSION_KEY) || 'null')
    return session && new Date(session.expires_at).getTime() > Date.now() ? session : null
  } catch {
    return null
  }
}

/** 判断当前标签页是否已登录。 */
export function hasSession() {
  return Boolean(getSession())
}
/** 保存登录会话。 */
export function saveSession(session) {
  sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session))
}
/** 清除登录会话。 */
export function clearSession() {
  sessionStorage.removeItem(AUTH_SESSION_KEY)
}

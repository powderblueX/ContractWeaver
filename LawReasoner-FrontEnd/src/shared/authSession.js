const AUTH_SESSION_KEY = 'lawreasoner.session'

export function getSession() {
  try {
    const session = JSON.parse(sessionStorage.getItem(AUTH_SESSION_KEY) || 'null')
    return session && new Date(session.expires_at).getTime() > Date.now() ? session : null
  } catch {
    return null
  }
}

export function hasSession() { return Boolean(getSession()) }
export function saveSession(session) { sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session)) }
export function clearSession() { sessionStorage.removeItem(AUTH_SESSION_KEY) }

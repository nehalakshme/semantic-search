// Central auth + fetch helper. Stores the JWT in localStorage and attaches it
// to every API request as a Bearer token.

const TOKEN_KEY = 'docusearch_token'
const USER_KEY = 'docusearch_user'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser() {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? JSON.parse(raw) : null
}

export function setAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export async function login(username, password) {
  const res = await fetch('/api/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail ?? 'Login failed')
  }
  const data = await res.json()
  const user = {
    username: data.username,
    node: data.node,
    label: data.label,
    level: data.level,
    is_admin: data.is_admin,
  }
  setAuth(data.access_token, user)
  return user
}

// Wrapper around fetch that injects the Authorization header and logs the user
// out automatically if the token is rejected.
export async function apiFetch(url, options = {}) {
  const token = getToken()
  const headers = { ...(options.headers || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(url, { ...options, headers })
  if (res.status === 401) {
    clearAuth()
    window.location.reload()
  }
  return res
}

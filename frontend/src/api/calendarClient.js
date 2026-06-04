const BASE = '/api'

function getKey() {
  return localStorage.getItem('api_key') || ''
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'X-API-Key': getKey(), ...options.headers },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export async function getCalendarStatus() {
  return request('/calendar/status')
}

export async function startOAuth() {
  const { url } = await request('/calendar/oauth/start')
  window.location.href = url
}

export async function getEvents() {
  return request('/calendar/events')
}

export async function createReminderFromText(text) {
  return request('/calendar/reminder/voice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
}

export async function listReminders() {
  return request('/calendar/reminders')
}

export async function deleteReminder(id) {
  return request(`/calendar/reminders/${id}`, { method: 'DELETE' })
}

export async function getVapidKey() {
  return request('/push/vapid-public-key')
}

export async function subscribePush(subscription) {
  return request('/push/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subscription }),
  })
}

const BASE = '/api'

function getKey() {
  return localStorage.getItem('api_key') || ''
}

function getErrorMessage(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(d => `${d.loc ? d.loc.join('.') + ': ' : ''}${d.msg}`).join(', ')
  }
  if (detail && typeof detail === 'object') {
    return detail.message || JSON.stringify(detail)
  }
  return String(detail)
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { 'X-API-Key': getKey(), ...options.headers },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const msg = err.detail ? getErrorMessage(err.detail) : res.statusText
    throw new Error(msg)
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

export async function createReminderFromText(text, selectedDate = null) {
  const clientTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const now = new Date()
  const offset = now.getTimezoneOffset()
  const absOffset = Math.abs(offset)
  const tempDate = new Date(now.getTime() - (offset * 60 * 1000))
  const localIso = tempDate.toISOString().substring(0, 19) + 
    (offset <= 0 ? '+' : '-') + 
    String(Math.floor(absOffset / 60)).padStart(2, '0') + ':' + 
    String(absOffset % 60).padStart(2, '0')

  return request('/calendar/reminder/voice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      selected_date: selectedDate,
      client_timezone: clientTimezone,
      client_local_time: localIso
    }),
  })
}

export async function listReminders() {
  return request('/calendar/reminders')
}

export async function deleteReminder(id) {
  return request(`/calendar/reminders/${id}`, { method: 'DELETE' })
}

export async function deleteEvent(id) {
  return request(`/calendar/events/${id}`, { method: 'DELETE' })
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

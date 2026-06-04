import { request, getClientTimezone } from './client'

function getLocalIsoTime() {
  const now = new Date()
  const offset = now.getTimezoneOffset()
  const absOffset = Math.abs(offset)
  const local = new Date(now.getTime() - offset * 60 * 1000)
  return local.toISOString().substring(0, 19) +
    (offset <= 0 ? '+' : '-') +
    String(Math.floor(absOffset / 60)).padStart(2, '0') + ':' +
    String(absOffset % 60).padStart(2, '0')
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
  return request('/calendar/reminder/voice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      selected_date: selectedDate,
      client_timezone: getClientTimezone(),
      client_local_time: getLocalIsoTime(),
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

export async function doneReminder(id) {
  return request(`/calendar/reminders/${id}/done`, { method: 'POST' })
}

export async function undoneReminder(id) {
  return request(`/calendar/reminders/${id}/undone`, { method: 'POST' })
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

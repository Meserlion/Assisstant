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
    headers: {
      'X-API-Key': getKey(),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const msg = err.detail ? getErrorMessage(err.detail) : res.statusText
    throw new Error(msg)
  }
  return res.json()
}

export async function captureNote(audioBlob) {
  const form = new FormData()
  form.append('audio', audioBlob, 'recording.webm')
  return request('/notes/capture', { method: 'POST', body: form })
}

export async function listNotes(limit = 50, offset = 0) {
  return request(`/notes/?limit=${limit}&offset=${offset}`)
}

export async function deleteNote(id) {
  return request(`/notes/${id}`, { method: 'DELETE' })
}

export async function queryNotes(text, history = []) {
  return request('/notes/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, history }),
  })
}

export async function queryNotesVoice(audioBlob, history = []) {
  const form = new FormData()
  form.append('audio', audioBlob, 'query.webm')
  form.append('history', JSON.stringify(history))
  return request('/notes/query/voice', { method: 'POST', body: form })
}

export function setApiKey(key) {
  localStorage.setItem('api_key', key)
}

export function hasApiKey() {
  return Boolean(getKey())
}

export async function getNoteGroups() {
  return request('/notes/groups')
}

export async function mergeNoteGroup(noteIds, topic, summary) {
  return request('/notes/merge-group', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note_ids: noteIds, topic, summary }),
  })
}

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

export async function request(path, options = {}) {
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

export function getClientTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone
}

export async function captureImageNote(file) {
  const form = new FormData()
  form.append('image', file)
  form.append('client_timezone', getClientTimezone())
  form.append('client_local_time', getLocalIsoTime())
  return request('/notes/image', { method: 'POST', body: form })
}

export async function captureNote(audioBlob) {
  const type = audioBlob.type || ''
  const ext = type.includes('mp4') ? 'mp4' : type.includes('ogg') ? 'ogg' : 'webm'
  const form = new FormData()
  form.append('audio', audioBlob, 'recording.' + ext)
  form.append('client_timezone', getClientTimezone())
  form.append('client_local_time', getLocalIsoTime())
  return request('/notes/capture', { method: 'POST', body: form })
}

export async function listNotes(limit, offset, archived) {
  limit = limit || 50
  offset = offset || 0
  archived = archived || false
  return request('/notes/?limit=' + limit + '&offset=' + offset + '&archived=' + archived)
}

export async function deleteNote(id) {
  return request('/notes/' + id, { method: 'DELETE' })
}

export async function updateNote(id, text) {
  return request('/notes/' + id, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, client_timezone: getClientTimezone(), client_local_time: getLocalIsoTime() }),
  })
}

export async function createTextNote(text) {
  return request('/notes/text', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, client_timezone: getClientTimezone(), client_local_time: getLocalIsoTime() }),
  })
}

export async function rewriteNote(text, instruction) {
  return request('/notes/rewrite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, instruction }),
  })
}

export async function transcribeAudio(audioBlob) {
  const form = new FormData()
  form.append('audio', audioBlob, 'edit.webm')
  return request('/notes/transcribe', { method: 'POST', body: form })
}

export async function queryNotes(text, history) {
  return request('/notes/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, history: history || [] }),
  })
}

export async function queryNotesStream(text, history, onMeta, onChunk) {
  const res = await fetch(BASE + '/notes/query/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-API-Key': getKey() },
    body: JSON.stringify({ text, history: history || [] }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ? getErrorMessage(err.detail) : res.statusText)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const result = await reader.read()
    if (result.done) break
    buffer += decoder.decode(result.value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      if (!line.startsWith('data: ')) continue
      try {
        const data = JSON.parse(line.slice(6))
        if (data.type === 'meta') onMeta(data)
        else if (data.type === 'text') onChunk(data.delta)
      } catch (e) { if (e) { /* skip malformed SSE line */ } }
    }
  }
}

export async function queryNotesVoice(audioBlob, history) {
  const form = new FormData()
  form.append('audio', audioBlob, 'query.webm')
  form.append('history', JSON.stringify(history || []))
  return request('/notes/query/voice', { method: 'POST', body: form })
}

export function setApiKey(key) {
  localStorage.setItem('api_key', key)
}

export function hasApiKey() {
  return Boolean(getKey())
}

export async function getNoteGroups(includeArchived) {
  return request('/notes/groups?include_archived=' + (includeArchived ? 'true' : 'false'))
}

export async function cleanupTrashNotes(noteIds) {
  return request('/notes/groups/cleanup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note_ids: noteIds }),
  })
}

export async function pinNote(id, pinned) {
  return request('/notes/' + id + '/pin', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pinned }),
  })
}

export async function archiveNote(id, archived) {
  return request('/notes/' + id + '/archive', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ archived: archived !== false }),
  })
}

export async function mergeNoteGroup(noteIds, topic, summary) {
  return request('/notes/merge-group', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ note_ids: noteIds, topic: topic, summary: summary }),
  })
}

import { useState, useRef } from 'react'
import { createReminderFromText } from '../api/calendarClient'
import { updateNote } from '../api/client'

/**
 * Parse raw_text into checklist items if it contains 2+ bullet lines.
 * Supports: `- item`, `* item`, `- [ ] item`, `- [x] item`
 * Returns { isList: bool, items: [{text, checked, isBullet}] }
 */
function parseChecklist(text) {
  const lines = text.split('\n')
  const items = lines.map(line => {
    const checkedMatch = line.match(/^[-*]\s+\[x\]\s*(.*)/i)
    if (checkedMatch) return { text: checkedMatch[1].trim(), checked: true, isBullet: true }
    const uncheckedMatch = line.match(/^[-*]\s+\[\s*\]\s*(.*)/)
    if (uncheckedMatch) return { text: uncheckedMatch[1].trim(), checked: false, isBullet: true }
    const bulletMatch = line.match(/^[-*]\s+(.+)/)
    if (bulletMatch) return { text: bulletMatch[1].trim(), checked: false, isBullet: true }
    return { text: line, checked: false, isBullet: false }
  })
  const bulletCount = items.filter(i => i.isBullet).length
  return { isList: bulletCount >= 2, items }
}

/** Rebuild raw_text from checklist items after a toggle. */
function serializeChecklist(items) {
  return items.map(item => {
    if (!item.isBullet) return item.text
    return item.checked ? '- [x] ' + item.text : '- [ ] ' + item.text
  }).join('\n')
}

export function NoteCard({ note, onDelete, onEdit, onSplit, onTagClick, activeTag, tagCounts = {}, selected, onSelect, onPin, onArchive, isArchived, onUpdate }) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [swipeOffset, setSwipeOffset] = useState(0)
  const touchStartX = useRef(null)
  const deletingRef = useRef(false)
  const archivingRef = useRef(false)

  const date = new Date(note.created_at).toLocaleString()
  const { isList, items: checklistItems } = parseChecklist(note.raw_text)

  async function handleCreateReminder() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await createReminderFromText(note.raw_text)
      setResult('Scheduled: ' + new Date(res.remind_at).toLocaleString())
    } catch (e) {
      setError(e.message || "Failed to schedule reminder")
    } finally {
      setLoading(false)
    }
  }

  async function handleChecklistToggle(index) {
    const updated = checklistItems.map((item, i) =>
      i === index ? { ...item, checked: !item.checked } : item
    )
    const newText = serializeChecklist(updated)
    try {
      const updatedNote = await updateNote(note.id, newText)
      if (onUpdate) onUpdate(updatedNote)
    } catch (e) {
      setError(e.message || 'Failed to save')
    }
  }

  function handleTouchStart(e) {
    touchStartX.current = e.touches[0].clientX
  }

  function handleTouchMove(e) {
    if (touchStartX.current === null) return
    const delta = e.touches[0].clientX - touchStartX.current
    if (delta < 0) setSwipeOffset(Math.max(delta, -100))
    else if (delta > 0 && onArchive) setSwipeOffset(Math.min(delta, 100))
  }

  function handleTouchEnd() {
    if (swipeOffset < -60 && !deletingRef.current) {
      deletingRef.current = true
      onDelete(note.id)
    } else if (swipeOffset > 60 && onArchive && !archivingRef.current) {
      archivingRef.current = true
      onArchive(note.id)
    }
    setSwipeOffset(0)
    touchStartX.current = null
  }

  function handleAudioMetadata(e) {
    const audio = e.target
    if (!isFinite(audio.duration) || audio.duration === 0) {
      audio.currentTime = 1e101
      const reset = () => {
        if (isFinite(audio.duration) && audio.duration > 0) {
          audio.currentTime = 0
          audio.removeEventListener('timeupdate', reset)
        }
      }
      audio.addEventListener('timeupdate', reset)
    }
  }

  return (
    <div className="note-card-wrapper">
      <div className="note-card-archive-zone" aria-hidden="true">{isArchived ? 'Unarchive' : 'Archive'}</div>
      <div className="note-card-delete-zone" aria-hidden="true">Delete</div>
      <div
        className={'note-card' + (selected ? ' note-card-selected' : '')}
        style={{ transform: 'translateX(' + swipeOffset + 'px)', transition: swipeOffset === 0 ? 'transform 0.2s ease' : 'none' }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        <div className="note-header">
          {onSelect && (
            <input
              type="checkbox"
              className="note-checkbox"
              checked={!!selected}
              onChange={() => onSelect(note.id)}
              aria-label="Select note"
            />
          )}
          <span className="note-date">{date}</span>
          <div className="note-actions">
            {onPin && (
              <button
                className={'pin-btn' + (note.pinned ? ' pin-active' : '')}
                onClick={() => onPin(note.id, !note.pinned)}
                title={note.pinned ? 'Unpin note' : 'Pin note'}
              >&#128204;</button>
            )}
            <button
              className="reminder-btn"
              onClick={handleCreateReminder}
              disabled={loading}
              title="Create a reminder from this note"
            >
              {loading ? '⏳' : '🔔'}
            </button>
            <button className="edit-btn" onClick={onEdit} title="Edit note">&#9999;&#65039;</button>
            <button className="split-btn" onClick={onSplit} title="Split note into two">&#9986;&#65039;</button>
            <button className="delete-btn" onClick={() => onDelete(note.id)} aria-label="Delete note">x</button>
          </div>
        </div>
        <p className="note-summary">{note.summary}</p>

        {isList ? (
          <ul className="note-checklist">
            {checklistItems.map((item, i) =>
              item.isBullet ? (
                <li key={i} className={'checklist-item' + (item.checked ? ' checklist-item-done' : '')}>
                  <label>
                    <input
                      type="checkbox"
                      checked={item.checked}
                      onChange={() => handleChecklistToggle(i)}
                    />
                    <span>{item.text}</span>
                  </label>
                </li>
              ) : item.text ? (
                <li key={i} className="checklist-header">{item.text}</li>
              ) : null
            )}
          </ul>
        ) : (
          <p className="note-text">{note.raw_text}</p>
        )}

        <div className="note-tags">
          {note.tags.map((tag) => (
            <span
              key={tag}
              className={'tag' + (tag === activeTag ? ' tag-active' : '')}
              onClick={() => onTagClick && onTagClick(tag)}
              style={{ cursor: onTagClick ? 'pointer' : 'default' }}
            >{tag}{tagCounts[tag] > 1 && <sup className="tag-count">{tagCounts[tag]}</sup>}</span>
          ))}
        </div>

        {note.audio_url && (
          <audio
            className="note-audio"
            src={note.audio_url + '?key=' + encodeURIComponent(localStorage.getItem('api_key') || '')}
            controls
            preload="metadata"
            onLoadedMetadata={handleAudioMetadata}
          />
        )}

        {result && <p className="card-status success">{result}</p>}
        {error && <p className="card-status error">{error}</p>}
      </div>
    </div>
  )
}

import { useState, useRef } from 'react'
import { createReminderFromText } from '../api/calendarClient'

export function NoteCard({ note, onDelete, onEdit, onSplit, onTagClick, activeTag, tagCounts = {}, selected, onSelect, onPin, onArchive, isArchived }) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [swipeOffset, setSwipeOffset] = useState(0)
  const touchStartX = useRef(null)
  const deletingRef = useRef(false)
  const archivingRef = useRef(false)

  const date = new Date(note.created_at).toLocaleString()

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
    // MediaRecorder WebM files lack duration metadata -- browsers show 0:00.
    // Seeking past the end forces the browser to scan and compute real duration.
    // We wait until duration is finite before resetting to avoid premature reset.
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
              >📌</button>
            )}
            <button
              className="reminder-btn"
              onClick={handleCreateReminder}
              disabled={loading}
              title="Create a reminder from this note"
            >
              {loading ? '⏳' : '🔔'}
            </button>
            <button className="edit-btn" onClick={onEdit} title="Edit note">✏️</button>
            <button className="split-btn" onClick={onSplit} title="Split note into two">✂️</button>
            <button className="delete-btn" onClick={() => onDelete(note.id)} aria-label="Delete note">×</button>
          </div>
        </div>
        <p className="note-summary">{note.summary}</p>
        <p className="note-text">{note.raw_text}</p>
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

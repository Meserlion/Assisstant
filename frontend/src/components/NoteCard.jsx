import { useState } from 'react'
import { createReminderFromText } from '../api/calendarClient'

export function NoteCard({ note, onDelete }) {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  const date = new Date(note.created_at).toLocaleString()

  async function handleCreateReminder() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await createReminderFromText(note.raw_text)
      setResult(`Scheduled: ${new Date(res.remind_at).toLocaleString()}`)
    } catch (e) {
      setError(e.message || "Failed to schedule reminder")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="note-card">
      <div className="note-header">
        <span className="note-date">{date}</span>
        <div className="note-actions">
          <button 
            className="reminder-btn" 
            onClick={handleCreateReminder} 
            disabled={loading} 
            title="Create a reminder from this note"
          >
            {loading ? '⏳' : '🔔'}
          </button>
          <button className="delete-btn" onClick={() => onDelete(note.id)} aria-label="Delete note">×</button>
        </div>
      </div>
      <p className="note-summary">{note.summary}</p>
      <p className="note-text">{note.raw_text}</p>
      <div className="note-tags">
        {note.tags.map((tag) => (
          <span key={tag} className="tag">{tag}</span>
        ))}
      </div>
      
      {result && <p className="card-status success">{result}</p>}
      {error && <p className="card-status error">{error}</p>}
    </div>
  )
}

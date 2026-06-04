import { useState } from 'react'
import { createTextNote, deleteNote } from '../api/client'

export function SplitNoteModal({ note, onClose, onSplit }) {
  const mid = Math.floor(note.raw_text.length / 2)
  const breakPoint = note.raw_text.indexOf(' ', mid)
  const splitAt = breakPoint === -1 ? mid : breakPoint

  const [topText, setTopText] = useState(note.raw_text.slice(0, splitAt).trim())
  const [bottomText, setBottomText] = useState(note.raw_text.slice(splitAt).trim())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  async function handleSplit(e) {
    e.preventDefault()
    if (!topText.trim() || !bottomText.trim() || saving) return
    setSaving(true)
    setError(null)
    try {
      const [a, b] = await Promise.all([
        createTextNote(topText.trim()),
        createTextNote(bottomText.trim()),
      ])
      await deleteNote(note.id)
      onSplit([a, b], note.id)
    } catch (err) {
      setError(err.message || 'Failed to split note')
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-container note-edit-modal">
        <div className="modal-header">
          <h3>Split Note</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <p className="modal-hint">Edit the two halves, then save to replace this note with two separate ones.</p>
        <form onSubmit={handleSplit} className="split-form">
          <textarea
            value={topText}
            onChange={(e) => setTopText(e.target.value)}
            disabled={saving}
            rows={4}
            placeholder="First note…"
          />
          <div className="split-divider">✂ split here</div>
          <textarea
            value={bottomText}
            onChange={(e) => setBottomText(e.target.value)}
            disabled={saving}
            rows={4}
            placeholder="Second note…"
          />
          {error && <p className="error">{error}</p>}
          {saving && <p className="status">Splitting…</p>}
          <div className="form-buttons">
            <button type="button" className="secondary-btn" onClick={onClose} disabled={saving}>Cancel</button>
            <button type="submit" className="accent-btn" disabled={saving || !topText.trim() || !bottomText.trim()}>Split into 2 notes</button>
          </div>
        </form>
      </div>
    </div>
  )
}

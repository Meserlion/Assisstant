import { useState } from 'react'
import { useRecorder } from '../hooks/useRecorder'
import { updateNote, transcribeAudio } from '../api/client'
import { VoiceButton } from './VoiceButton'

export function EditNoteModal({ note, onClose, onSave }) {
  const [text, setText] = useState(note.raw_text)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const { recording, start, stop } = useRecorder()

  async function handleSave(e) {
    if (e) e.preventDefault()
    if (!text.trim() || saving) return
    setSaving(true)
    setError(null)
    try {
      const updated = await updateNote(note.id, text.trim())
      onSave(updated)
    } catch (e) {
      setError(e.message || "Failed to update note")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-container note-edit-modal">
        <div className="modal-header">
          <h3>Edit Note</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        
        <form onSubmit={handleSave} className="edit-note-form">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={saving}
            rows={6}
            placeholder="Type your note content here..."
          />
          
          {error && <p className="error">{error}</p>}
          {saving && <p className="status">Saving note and regenerating AI tags/summary...</p>}
          
          <div className="modal-actions">
            <div className="mini-voice-wrapper">
              <VoiceButton
                recording={recording}
                onStart={start}
                onStop={async () => {
                  setSaving(true)
                  setError(null)
                  try {
                    const blob = await stop()
                    const res = await transcribeAudio(blob)
                    if (res.text) {
                      setText((prev) => prev ? prev + ' ' + res.text : res.text)
                    }
                  } catch (e) {
                    setError(e.message || "Failed to transcribe voice")
                  } finally {
                    setSaving(false)
                  }
                }}
                label="Hold to add text via voice"
                disabled={saving}
              />
            </div>
            
            <div className="form-buttons">
              <button type="button" className="secondary-btn" onClick={onClose} disabled={saving}>Cancel</button>
              <button type="submit" className="accent-btn" disabled={saving || !text.trim()}>Save</button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useRecorder } from '../hooks/useRecorder'
import { updateNote, transcribeAudio, rewriteNote } from '../api/client'
import { VoiceButton } from './VoiceButton'

export function EditNoteModal({ note, onClose, onSave }) {
  const [text, setText] = useState(note.raw_text)
  const [instruction, setInstruction] = useState('')
  const [saving, setSaving] = useState(false)
  const [rewriting, setRewriting] = useState(false)
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
      setError(e.message || 'Failed to update note')
    } finally {
      setSaving(false)
    }
  }

  async function handleRewrite(e) {
    e.preventDefault()
    if (!instruction.trim() || rewriting) return
    setRewriting(true)
    setError(null)
    try {
      const res = await rewriteNote(text, instruction.trim())
      setText(res.rewritten)
      setInstruction('')
    } catch (e) {
      setError(e.message || 'Failed to rewrite note')
    } finally {
      setRewriting(false)
    }
  }

  const busy = saving || rewriting

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
            disabled={busy}
            rows={6}
            placeholder="Type your note content here..."
          />

          <div className="ai-rewrite-row">
            <input
              type="text"
              placeholder='Ask AI to edit… e.g. "turn into a bullet list"'
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleRewrite(e) }}
              disabled={busy}
            />
            <button
              type="button"
              className="accent-btn ai-apply-btn"
              onClick={handleRewrite}
              disabled={busy || !instruction.trim()}
            >
              {rewriting ? '…' : '✨'}
            </button>
          </div>

          {error && <p className="error">{error}</p>}
          {saving && <p className="status">Saving and regenerating AI tags/summary…</p>}
          {rewriting && <p className="status">Rewriting…</p>}

          <div className="modal-actions">
            <div className="mini-voice-wrapper">
              <VoiceButton
                recording={recording}
                onStart={start}
                onStop={async () => {
                  setRewriting(true)
                  setError(null)
                  try {
                    const blob = await stop()
                    const res = await transcribeAudio(blob)
                    if (res.text) {
                      setText((prev) => prev ? prev + ' ' + res.text : res.text)
                    }
                  } catch (e) {
                    setError(e.message || 'Failed to transcribe voice')
                  } finally {
                    setRewriting(false)
                  }
                }}
                label="Hold to add text via voice"
                disabled={busy}
              />
            </div>

            <div className="form-buttons">
              <button type="button" className="secondary-btn" onClick={onClose} disabled={busy}>Cancel</button>
              <button type="submit" className="accent-btn" disabled={busy || !text.trim()}>Save</button>
            </div>
          </div>
        </form>
      </div>
    </div>
  )
}

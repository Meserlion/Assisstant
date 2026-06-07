import { useState } from 'react'
import { useRecorder } from '../hooks/useRecorder'
import { updateNote, transcribeAudio, rewriteNote, setNoteColor } from '../api/client'

export function EditNoteModal({ note, onClose, onSave }) {
  const COLOR_SWATCHES = ['red', 'orange', 'yellow', 'green', 'blue', 'purple']
  const [text, setText] = useState(note.raw_text)
  const [color, setColor] = useState(note.color || null)
  const [instruction, setInstruction] = useState('')
  const [saving, setSaving] = useState(false)
  const [rewriting, setRewriting] = useState(false)
  const [error, setError] = useState(null)
  const { recording, start, stop } = useRecorder()
  const { recording: instrRecording, start: instrStart, stop: instrStop } = useRecorder()

  async function handleSave(e) {
    if (e) e.preventDefault()
    if (!text.trim() || saving) return
    setSaving(true)
    setError(null)
    try {
      let updated = await updateNote(note.id, text.trim())
      if ((color || null) !== (note.color || null)) {
        updated = await setNoteColor(note.id, color)
      }
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

  async function handleVoiceAppend() {
    setRewriting(true)
    setError(null)
    try {
      const blob = await stop()
      const res = await transcribeAudio(blob)
      if (res.text) setText((prev) => prev ? prev + ' ' + res.text : res.text)
    } catch (e) {
      setError(e.message || 'Failed to transcribe voice')
    } finally {
      setRewriting(false)
    }
  }

  async function handleVoiceInstruction() {
    setRewriting(true)
    setError(null)
    try {
      const blob = await instrStop()
      const res = await transcribeAudio(blob)
      if (res.text) setInstruction(res.text)
    } catch (e) {
      setError(e.message || 'Failed to transcribe')
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

          {/* Colour swatch picker */}
          <div className="color-picker-row">
            <span className="color-picker-label">Colour</span>
            <button
              type="button"
              className={'color-swatch color-swatch-none' + (!color ? ' color-swatch-selected' : '')}
              onClick={() => setColor(null)}
              disabled={busy}
              title="No colour"
              aria-label="No colour"
            >×</button>
            {COLOR_SWATCHES.map((c) => (
              <button
                key={c}
                type="button"
                className={'color-swatch color-swatch-' + c + (color === c ? ' color-swatch-selected' : '')}
                onClick={() => setColor(c)}
                disabled={busy}
                title={c}
                aria-label={c}
              />
            ))}
          </div>

          {/* AI rewrite row */}
          <div className="ai-rewrite-row">
            <input
              type="text"
              placeholder='Ask AI… e.g. "turn into a bullet list"'
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleRewrite(e) }}
              disabled={busy}
            />
            <button
              type="button"
              className="icon-btn"
              onPointerDown={(e) => { e.preventDefault(); if (!busy) instrStart() }}
              onPointerUp={(e) => { e.preventDefault(); if (instrRecording) handleVoiceInstruction() }}
              onPointerLeave={() => { if (instrRecording) handleVoiceInstruction() }}
              disabled={busy}
              title="Hold to dictate instruction"
              style={{ touchAction: 'none' }}
            >
              {instrRecording ? '⏹' : '🎙'}
            </button>
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
          {(saving || rewriting) && (
            <p className="status">{saving ? 'Saving…' : 'Rewriting…'}</p>
          )}

          {/* Bottom actions: voice append + Cancel + Save in one row */}
          <div className="modal-actions">
            <button
              type="button"
              className="icon-btn"
              onPointerDown={(e) => { e.preventDefault(); if (!busy) start() }}
              onPointerUp={(e) => { e.preventDefault(); if (recording) handleVoiceAppend() }}
              onPointerLeave={() => { if (recording) handleVoiceAppend() }}
              disabled={busy}
              title="Hold to append voice text"
              style={{ touchAction: 'none' }}
            >
              {recording ? '⏹' : '🎙'}
            </button>
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

import { useState } from 'react'
import { useRecorder } from '../hooks/useRecorder'
import { queryNotes, queryNotesVoice } from '../api/client'
import { VoiceButton } from './VoiceButton'

export function QueryPanel() {
  const [textInput, setTextInput] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const { recording, start, stop } = useRecorder()

  async function handleVoiceQuery() {
    if (recording) {
      setLoading(true)
      setError(null)
      try {
        const blob = await stop()
        const res = await queryNotesVoice(blob)
        setResult(res)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    } else {
      await start()
    }
  }

  async function handleTextQuery(e) {
    e.preventDefault()
    if (!textInput.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await queryNotes(textInput)
      setResult(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="query-panel">
      <h2>Ask your notes</h2>

      <VoiceButton
        recording={recording}
        onStart={start}
        onStop={async () => {
          setLoading(true)
          setError(null)
          try {
            const blob = await stop()
            const res = await queryNotesVoice(blob)
            setResult(res)
          } catch (e) {
            setError(e.message)
          } finally {
            setLoading(false)
          }
        }}
        label="Hold to ask"
        disabled={loading}
      />

      <form onSubmit={handleTextQuery} className="text-query-form">
        <input
          type="text"
          placeholder="Or type your question…"
          value={textInput}
          onChange={(e) => setTextInput(e.target.value)}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !textInput.trim()}>Ask</button>
      </form>

      {loading && <p className="status">Thinking…</p>}
      {error && <p className="error">{error}</p>}

      {result && (
        <div className="query-result">
          <p className="answer">{result.answer}</p>
          {result.sources.length > 0 && (
            <details>
              <summary>{result.sources.length} source note{result.sources.length > 1 ? 's' : ''}</summary>
              {result.sources.map((s) => (
                <p key={s.id} className="source-note">{s.summary}</p>
              ))}
            </details>
          )}
        </div>
      )}
    </div>
  )
}

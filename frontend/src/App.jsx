import { useState, useEffect, useCallback } from 'react'
import { hasApiKey, captureNote, listNotes, deleteNote } from './api/client'
import { useRecorder } from './hooks/useRecorder'
import { ApiKeySetup } from './components/ApiKeySetup'
import { NoteCard } from './components/NoteCard'
import { QueryPanel } from './components/QueryPanel'
import { CalendarTab } from './components/CalendarTab'
import { VoiceButton } from './components/VoiceButton'
import './App.css'

export default function App() {
  const [ready, setReady] = useState(hasApiKey())
  const [tab, setTab] = useState('notes')
  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [error, setError] = useState(null)
  const { recording, start, stop } = useRecorder()

  const fetchNotes = useCallback(async () => {
    setLoading(true)
    try {
      const data = await listNotes()
      setNotes(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (ready && tab === 'notes') fetchNotes()
  }, [ready, tab, fetchNotes])

  async function handleStop() {
    setCapturing(true)
    setError(null)
    try {
      const blob = await stop()
      await captureNote(blob)
      await fetchNotes()
    } catch (e) {
      setError(e.message)
    } finally {
      setCapturing(false)
    }
  }

  async function handleDelete(id) {
    try {
      await deleteNote(id)
      setNotes((prev) => prev.filter((n) => n.id !== id))
    } catch (e) {
      setError(e.message)
    }
  }

  if (!ready) return <ApiKeySetup onDone={() => setReady(true)} />

  return (
    <div className="app">
      <header>
        <h1>Assistant</h1>
        <nav>
          <button className={tab === 'notes' ? 'active' : ''} onClick={() => setTab('notes')}>Notes</button>
          <button className={tab === 'ask' ? 'active' : ''} onClick={() => setTab('ask')}>Ask</button>
          <button className={tab === 'calendar' ? 'active' : ''} onClick={() => setTab('calendar')}>Calendar</button>
        </nav>
      </header>

      <main>
        {tab === 'notes' && (
          <>
            <VoiceButton
              recording={recording}
              onStart={start}
              onStop={handleStop}
              label="Hold to record note"
              disabled={capturing}
            />

            {capturing && <p className="status">Saving note…</p>}
            {error && <p className="error">{error}</p>}
            {loading && <p className="status">Loading…</p>}

            <div className="notes-list">
              {notes.map((note) => (
                <NoteCard key={note.id} note={note} onDelete={handleDelete} />
              ))}
              {!loading && notes.length === 0 && (
                <p className="empty">No notes yet. Hold the button to record your first one.</p>
              )}
            </div>
          </>
        )}

        {tab === 'ask' && <QueryPanel />}
        {tab === 'calendar' && <CalendarTab />}
      </main>
    </div>
  )
}

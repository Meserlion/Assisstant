import { useState, useEffect, useCallback } from 'react'
import { hasApiKey, captureNote, listNotes, deleteNote } from './api/client'
import { useRecorder } from './hooks/useRecorder'
import { ApiKeySetup } from './components/ApiKeySetup'
import { NoteCard } from './components/NoteCard'
import { QueryPanel } from './components/QueryPanel'
import { CalendarTab } from './components/CalendarTab'
import { VoiceButton } from './components/VoiceButton'
import { ConsolidateTab } from './components/ConsolidateTab'
import { EditNoteModal } from './components/EditNoteModal'
import './App.css'

export default function App() {
  const [ready, setReady] = useState(hasApiKey())
  const [tab, setTab] = useState('notes')
  const [notes, setNotes] = useState([])
  const [loading, setLoading] = useState(false)
  const [capturing, setCapturing] = useState(false)
  const [editingNote, setEditingNote] = useState(null)
  const [activeTag, setActiveTag] = useState(null)
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
    if (ready && (tab === 'notes' || tab === 'consolidate')) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      fetchNotes()
    }
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

  function handleExport() {
    const lines = notes.map((n) => {
      const date = new Date(n.created_at).toLocaleString()
      const tags = n.tags.length ? `*Tags: ${n.tags.join(', ')}*` : ''
      return [`## ${date}`, '', `**${n.summary}**`, '', n.raw_text, '', tags, '', '---', ''].join('\n')
    })
    const md = `# My Notes\n\nExported ${new Date().toLocaleString()}\n\n---\n\n` + lines.join('\n')
    const blob = new Blob([md], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `notes-${new Date().toISOString().slice(0, 10)}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!ready) return <ApiKeySetup onDone={() => setReady(true)} />

  return (
    <div className="app">
      <header>
        <h1>Assistant</h1>
        <nav>
          <button className={tab === 'notes' ? 'active' : ''} onClick={() => setTab('notes')}>Notes</button>
          <button className={tab === 'consolidate' ? 'active' : ''} onClick={() => setTab('consolidate')}>Merge</button>
          <button className={tab === 'ask' ? 'active' : ''} onClick={() => setTab('ask')}>Ask</button>
          <button className={tab === 'calendar' ? 'active' : ''} onClick={() => setTab('calendar')}>Calendar</button>
        </nav>
      </header>

      <main>
        {tab === 'notes' && (
          <>
            {loading && <p className="status">Loading…</p>}

            <div className="notes-toolbar">
              {activeTag ? (
                <div className="tag-filter-banner">
                  <span>Filtered by: <strong>{activeTag}</strong></span>
                  <button className="clear-filter-btn" onClick={() => setActiveTag(null)}>✕ Clear</button>
                </div>
              ) : <div />}
              {notes.length > 0 && (
                <button className="export-btn" onClick={handleExport} title="Export all notes as Markdown">
                  ↓ Export
                </button>
              )}
            </div>

            <div className="notes-list">
              {notes
                .filter((n) => !activeTag || n.tags.includes(activeTag))
                .map((note) => (
                  <NoteCard
                    key={note.id}
                    note={note}
                    onDelete={handleDelete}
                    onEdit={() => setEditingNote(note)}
                    onTagClick={(tag) => setActiveTag(tag === activeTag ? null : tag)}
                    activeTag={activeTag}
                  />
                ))}
              {!loading && notes.filter((n) => !activeTag || n.tags.includes(activeTag)).length === 0 && (
                <p className="empty">{activeTag ? `No notes tagged "${activeTag}".` : 'No notes yet. Hold the button to record your first one.'}</p>
              )}
            </div>

            <div className="bottom-bar">
              {capturing && <p className="status">Saving note…</p>}
              {error && <p className="error">{error}</p>}
              <VoiceButton
                recording={recording}
                onStart={start}
                onStop={handleStop}
                label="Hold to record note"
                disabled={capturing}
              />
            </div>
          </>
        )}

        {tab === 'ask' && <QueryPanel />}
        {tab === 'calendar' && <CalendarTab />}
        {tab === 'consolidate' && <ConsolidateTab notes={notes} onMergeSuccess={fetchNotes} />}
      </main>

      {editingNote && (
        <EditNoteModal
          note={editingNote}
          onClose={() => setEditingNote(null)}
          onSave={(updated) => {
            setNotes((prev) => prev.map((n) => n.id === updated.id ? updated : n))
            setEditingNote(null)
          }}
        />
      )}
    </div>
  )
}

import { useState, useEffect } from 'react'
import { getNoteGroups, cleanupTrashNotes, mergeNoteGroup } from '../api/client'

export function ConsolidateTab({ notes, onMergeSuccess }) {
  const [groups, setGroups] = useState([])
  const [trashIds, setTrashIds] = useState([])
  const [loading, setLoading] = useState(true)
  const [mergingId, setMergingId] = useState(null)
  const [error, setError] = useState(null)
  const [successMsg, setSuccessMsg] = useState(null)

  async function fetchGroups() {
    setLoading(true)
    setError(null)
    try {
      const data = await getNoteGroups()
      setGroups(data.groups)
      setTrashIds(data.trash_ids || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchGroups()
  }, [])

  async function handleCleanupTrash() {
    if (!window.confirm(`Delete ${trashIds.length} empty or noise note${trashIds.length > 1 ? 's' : ''}? This cannot be undone.`)) return
    try {
      await cleanupTrashNotes(trashIds)
      setTrashIds([])
      setSuccessMsg(`Deleted ${trashIds.length} noise note${trashIds.length > 1 ? 's' : ''}.`)
      if (onMergeSuccess) onMergeSuccess()
    } catch (e) {
      setError(e.message)
    }
  }

  async function handleMerge(group) {
    if (window.confirm(`Are you sure you want to consolidate these notes into a single note?`)) {
      setMergingId(group.topic)
      setError(null)
      setSuccessMsg(null)
      try {
        await mergeNoteGroup(group.note_ids, group.topic, group.summary)
        setSuccessMsg(`Successfully consolidated notes into "${group.topic}"!`)
        // Filter out this group
        setGroups((prev) => prev.filter((g) => g.topic !== group.topic))
        // Trigger parent notes refresh
        if (onMergeSuccess) onMergeSuccess()
      } catch (e) {
        setError(e.message)
      } finally {
        setMergingId(null)
      }
    }
  }

  if (loading) return <p className="status">Scanning notes for topics…</p>

  return (
    <div className="consolidate-tab">
      <h2>Consolidate Similar Notes</h2>
      <p className="description">
        AI analyzes your notes to find semantically related items. You can merge them into a single, clean, chronological summary.
      </p>

      {error && <p className="error">{error}</p>}
      {successMsg && <p className="status" style={{ color: 'var(--success)', fontWeight: 'bold' }}>{successMsg}</p>}

      {trashIds.length > 0 && (
        <div className="trash-banner">
          <span>{trashIds.length} empty or noise note{trashIds.length > 1 ? 's' : ''} found.</span>
          <button className="secondary-btn" onClick={handleCleanupTrash}>Delete them</button>
        </div>
      )}

      <div className="groups-list">
        {groups.map((group) => {
          const matchedNotes = group.note_ids
            .map((id) => notes.find((n) => n.id === id))
            .filter(Boolean)

          if (matchedNotes.length === 0) return null

          return (
            <div key={group.topic} className="group-card">
              <div className="group-header">
                <span className="group-topic">📁 {group.topic}</span>
                <button
                  className="accent-btn"
                  onClick={() => handleMerge(group)}
                  disabled={mergingId !== null}
                >
                  {mergingId === group.topic ? 'Consolidating…' : 'Consolidate'}
                </button>
              </div>
              
              <p className="group-summary">{group.summary}</p>
              
              <details className="group-details">
                <summary>{matchedNotes.length} source note{matchedNotes.length > 1 ? 's' : ''}</summary>
                <div className="nested-notes">
                  {matchedNotes.map((n) => (
                    <div key={n.id} className="nested-note-card">
                      <div className="nested-note-header">
                        <span className="note-date">{new Date(n.created_at).toLocaleString()}</span>
                      </div>
                      <p className="note-summary">{n.summary}</p>
                      <p className="note-text">{n.raw_text}</p>
                    </div>
                  ))}
                </div>
              </details>
            </div>
          )
        })}

        {groups.length === 0 && (
          <p className="empty">
            All caught up! No duplicate or highly similar notes found to consolidate right now.
          </p>
        )}
      </div>
    </div>
  )
}

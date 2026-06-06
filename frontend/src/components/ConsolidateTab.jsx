import { useState, useEffect } from 'react'
import { getNoteGroups, cleanupTrashNotes, mergeNoteGroup, listNotes } from '../api/client'

export function ConsolidateTab({ notes, onMergeSuccess }) {
  const [groups, setGroups] = useState([])
  const [trashIds, setTrashIds] = useState([])
  const [loading, setLoading] = useState(true)
  const [mergingId, setMergingId] = useState(null)
  const [error, setError] = useState(null)
  const [successMsg, setSuccessMsg] = useState(null)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [allNotes, setAllNotes] = useState(notes)

  async function fetchGroups(withArchived = includeArchived) {
    setLoading(true)
    setError(null)
    try {
      const [data, archivedNotes] = await Promise.all([
        getNoteGroups(withArchived),
        withArchived ? listNotes(200, 0, true) : Promise.resolve([]),
      ])
      setGroups(data.groups)
      setTrashIds(data.trash_ids || [])
      const combined = [...notes]
      for (const n of archivedNotes) {
        if (!combined.find((x) => x.id === n.id)) combined.push(n)
      }
      setAllNotes(combined)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchGroups()
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        setGroups((prev) => prev.filter((g) => g.topic !== group.topic))
        if (onMergeSuccess) onMergeSuccess()
      } catch (e) {
        setError(e.message)
      } finally {
        setMergingId(null)
      }
    }
  }

  if (loading) return <p className="status">Scanning notes for topics...</p>

  return (
    <div className="consolidate-tab">
      <h2>Consolidate Similar Notes</h2>
      <p className="description">
        AI analyzes your notes to find semantically related items. You can merge them into a single, clean, chronological summary.
      </p>

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.875rem', color: 'var(--text-secondary)', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => {
              setIncludeArchived(e.target.checked)
              fetchGroups(e.target.checked)
            }}
          />
          Include archived notes
        </label>
        {includeArchived && (
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
            Merged results always appear in active notes
          </span>
        )}
      </div>

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
            .map((id) => allNotes.find((n) => n.id === id))
            .filter(Boolean)

          if (matchedNotes.length === 0) return null

          return (
            <div key={group.topic} className="group-card">
              <div className="group-header">
                <span className="group-topic">&#128193; {group.topic}</span>
                <button
                  className="accent-btn"
                  onClick={() => handleMerge(group)}
                  disabled={mergingId !== null}
                >
                  {mergingId === group.topic ? 'Consolidating...' : 'Consolidate'}
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
                        {n.archived && <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginLeft: '6px' }}>(archived)</span>}
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

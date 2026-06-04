export function NoteCard({ note, onDelete }) {
  const date = new Date(note.created_at).toLocaleString()

  return (
    <div className="note-card">
      <div className="note-header">
        <span className="note-date">{date}</span>
        <button className="delete-btn" onClick={() => onDelete(note.id)} aria-label="Delete note">×</button>
      </div>
      <p className="note-summary">{note.summary}</p>
      <p className="note-text">{note.raw_text}</p>
      <div className="note-tags">
        {note.tags.map((tag) => (
          <span key={tag} className="tag">{tag}</span>
        ))}
      </div>
    </div>
  )
}

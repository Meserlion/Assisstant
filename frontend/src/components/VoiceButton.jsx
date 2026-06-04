export function VoiceButton({ recording, onStart, onStop, label, disabled }) {
  return (
    <button
      className={`voice-btn ${recording ? 'recording' : ''}`}
      onPointerDown={onStart}
      onPointerUp={onStop}
      onPointerLeave={recording ? onStop : undefined}
      disabled={disabled}
      aria-label={label}
    >
      <span className="mic-icon">{recording ? '⏹' : '🎙'}</span>
      <span>{recording ? 'Release to send' : label}</span>
    </button>
  )
}

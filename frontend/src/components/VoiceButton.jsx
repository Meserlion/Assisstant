import { useRef, useState, useEffect } from 'react'

export function VoiceButton({ recording, onStart, onStop, label, disabled }) {
  const pointerDownTimeRef = useRef(0)
  const [isToggleMode, setIsToggleMode] = useState(false)
  const recordingRef = useRef(recording)

  // Keep ref in sync with the prop so event handlers always see the latest value
  useEffect(() => {
    recordingRef.current = recording
  }, [recording])

  // isToggleMode is only meaningful while recording; clear it when recording ends
  const activeToggleMode = isToggleMode && recording

  function handlePointerDown(e) {
    if (disabled) return
    e.preventDefault()

    if (recordingRef.current) {
      // Any press while recording stops it (covers toggle mode and the stuck-recording recovery case)
      onStop()
      setIsToggleMode(false)
      pointerDownTimeRef.current = 0
    } else {
      pointerDownTimeRef.current = Date.now()
      onStart()
    }
  }

  function handlePointerUp(e) {
    if (disabled) return
    e.preventDefault()

    if (pointerDownTimeRef.current > 0) {
      const duration = Date.now() - pointerDownTimeRef.current
      pointerDownTimeRef.current = 0

      if (duration < 250) {
        // Quick tap: stay in recording, activate toggle mode so user taps again to send
        setIsToggleMode(true)
      } else {
        // Hold: stop on release
        onStop()
        setIsToggleMode(false)
      }
    }
  }

  function handlePointerLeave() {
    if (disabled) return
    if (pointerDownTimeRef.current > 0) {
      const duration = Date.now() - pointerDownTimeRef.current
      pointerDownTimeRef.current = 0

      if (duration >= 250) {
        // Dragged off after a hold: stop recording
        onStop()
        setIsToggleMode(false)
      }
      // Fast drag-off (< 250ms): toggle mode is NOT activated — recording is active but
      // the next pointerDown (handled above) will always stop it, so no stuck state.
    }
  }

  return (
    <button
      className={`voice-btn ${recording ? 'recording' : ''}`}
      onPointerDown={handlePointerDown}
      onPointerUp={handlePointerUp}
      onPointerLeave={handlePointerLeave}
      disabled={disabled}
      aria-label={label}
      style={{ touchAction: 'none' }}
    >
      <span className="mic-icon">{recording ? '⏹' : '🎙'}</span>
      <span>
        {recording
          ? (activeToggleMode ? 'Tap to send' : 'Release to send')
          : label
        }
      </span>
    </button>
  )
}

import { useRef, useState, useEffect } from 'react'

export function VoiceButton({ recording, onStart, onStop, label, disabled }) {
  const pointerDownTimeRef = useRef(0)
  const [isToggleMode, setIsToggleMode] = useState(false)
  const recordingRef = useRef(recording)

  // Keep ref in sync
  useEffect(() => {
    recordingRef.current = recording
    if (!recording) {
      setIsToggleMode(false)
    }
  }, [recording])

  function handlePointerDown(e) {
    if (disabled) return
    e.preventDefault()
    
    if (recordingRef.current) {
      // If we are recording in toggle mode, clicking again stops the recording
      if (isToggleMode) {
        onStop()
        setIsToggleMode(false)
      }
    } else {
      // Start recording
      pointerDownTimeRef.current = Date.now()
      onStart()
    }
  }

  function handlePointerUp(e) {
    if (disabled) return
    e.preventDefault()
    
    if (pointerDownTimeRef.current > 0) {
      const duration = Date.now() - pointerDownTimeRef.current
      pointerDownTimeRef.current = 0 // Reset
      
      if (duration < 250) {
        // Quick press: activate toggle mode (keep recording active)
        setIsToggleMode(true)
      } else {
        // Hold press: stop recording immediately on release
        onStop()
        setIsToggleMode(false)
      }
    }
  }

  function handlePointerLeave(e) {
    if (disabled) return
    if (pointerDownTimeRef.current > 0) {
      const duration = Date.now() - pointerDownTimeRef.current
      pointerDownTimeRef.current = 0 // Reset
      
      if (duration >= 250) {
        onStop()
        setIsToggleMode(false)
      }
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
          ? (isToggleMode ? 'Tap to send' : 'Release to send') 
          : label
        }
      </span>
    </button>
  )
}

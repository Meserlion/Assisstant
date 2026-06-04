import { useState, useRef } from 'react'

export function useRecorder() {
  const [recording, setRecording] = useState(false)
  const mediaRef = useRef(null)
  const chunksRef = useRef([])

  async function start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream)
    chunksRef.current = []
    recorder.ondataavailable = (e) => chunksRef.current.push(e.data)
    recorder.start()
    mediaRef.current = recorder
    setRecording(true)
  }

  function stop() {
    return new Promise((resolve) => {
      const recorder = mediaRef.current
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        recorder.stream.getTracks().forEach((t) => t.stop())
        setRecording(false)
        resolve(blob)
      }
      recorder.stop()
    })
  }

  return { recording, start, stop }
}

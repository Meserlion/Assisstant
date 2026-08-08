import { useState, useRef } from 'react'

function getSupportedMimeType() {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
    'audio/ogg',
  ]
  for (const type of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(type)) {
      return type
    }
  }
  return ''
}

export function useRecorder() {
  const [recording, setRecording] = useState(false)
  const mediaRef = useRef(null)
  const chunksRef = useRef([])
  const mimeTypeRef = useRef('')

  async function start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const mimeType = getSupportedMimeType()
    mimeTypeRef.current = mimeType
    const options = mimeType ? { mimeType } : {}
    const recorder = new MediaRecorder(stream, options)
    chunksRef.current = []
    recorder.ondataavailable = (e) => chunksRef.current.push(e.data)
    recorder.start()
    mediaRef.current = recorder
    setRecording(true)
  }

  function stop() {
    return new Promise((resolve) => {
      const recorder = mediaRef.current
      const mimeType = mimeTypeRef.current || 'audio/webm'
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType })
        recorder.stream.getTracks().forEach((t) => t.stop())
        setRecording(false)
        resolve(blob)
      }
      recorder.stop()
    })
  }

  return { recording, start, stop }
}

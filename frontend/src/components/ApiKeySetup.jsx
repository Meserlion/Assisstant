import { useState } from 'react'
import { setApiKey } from '../api/client'

export function ApiKeySetup({ onDone }) {
  const [key, setKey] = useState('')

  function submit(e) {
    e.preventDefault()
    if (key.trim()) {
      setApiKey(key.trim())
      onDone()
    }
  }

  return (
    <div className="setup">
      <h1>Assistant</h1>
      <p>Enter your API key to continue.</p>
      <form onSubmit={submit}>
        <input
          type="password"
          placeholder="API key"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          autoFocus
        />
        <button type="submit" disabled={!key.trim()}>Connect</button>
      </form>
    </div>
  )
}

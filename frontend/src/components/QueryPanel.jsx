import { useState, useRef, useEffect } from 'react'
import { useRecorder } from '../hooks/useRecorder'
import { queryNotes, queryNotesVoice } from '../api/client'
import { VoiceButton } from './VoiceButton'

export function QueryPanel() {
  const [textInput, setTextInput] = useState('')
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hi! Ask me anything about your notes or calendar events.',
      sources: []
    }
  ])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const { recording, start, stop } = useRecorder()
  const chatEndRef = useRef(null)

  // Scroll to bottom of chat when new messages are added
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Helper to format history for API
  function getHistoryList() {
    return messages.map(m => ({
      role: m.role,
      content: m.content
    }))
  }

  async function handleTextQuery(e) {
    e.preventDefault()
    if (!textInput.trim() || loading) return

    const userText = textInput.trim()
    setTextInput('')
    setError(null)
    setLoading(true)

    // Add user message to history
    const updatedMessages = [...messages, { role: 'user', content: userText }]
    setMessages(updatedMessages)

    try {
      const history = updatedMessages.slice(0, -1).map(m => ({
        role: m.role,
        content: m.content
      }))
      const res = await queryNotes(userText, history)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.answer,
        sources: res.sources
      }])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="query-panel">
      <h2>Ask your notes</h2>
      
      <div className="chat-container">
        {messages.map((msg, index) => (
          <div key={index} className={`chat-message ${msg.role}`}>
            <div className="chat-bubble">
              <p className="message-text">{msg.content}</p>
              {msg.sources && msg.sources.length > 0 && (
                <details className="chat-sources">
                  <summary>{msg.sources.length} source note{msg.sources.length > 1 ? 's' : ''}</summary>
                  <div className="sources-list">
                    {msg.sources.map((s) => (
                      <p key={s.id} className="source-note-summary">{s.summary}</p>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="chat-message assistant loading-bubble">
            <div className="chat-bubble">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      <div className="bottom-bar">
        {error && <p className="error">{error}</p>}
        
        <form onSubmit={handleTextQuery} className="text-query-form chat-input-row">
          <input
            type="text"
            placeholder="Type your follow-up..."
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            disabled={loading}
          />
          
          <div className="voice-mic-wrapper">
            <VoiceButton
              recording={recording}
              onStart={start}
              onStop={async () => {
                setLoading(true)
                setError(null)
                try {
                  const blob = await stop()
                  const history = getHistoryList()
                  const res = await queryNotesVoice(blob, history)
                  
                  setMessages(prev => [
                    ...prev,
                    { role: 'user', content: res.query },
                    { role: 'assistant', content: res.answer, sources: res.sources }
                  ])
                } catch (e) {
                  setError(e.message)
                } finally {
                  setLoading(false)
                }
              }}
              label="Ask by voice"
              disabled={loading}
            />
          </div>

          <button type="submit" disabled={loading || !textInput.trim()}>Ask</button>
        </form>
      </div>
    </div>
  )
}

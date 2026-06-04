import { useState, useEffect } from 'react'
import { useRecorder } from '../hooks/useRecorder'
import {
  getCalendarStatus, startOAuth, getEvents,
  createReminderFromText, listReminders, deleteReminder,
  getVapidKey, subscribePush,
} from '../api/calendarClient'
import { VoiceButton } from './VoiceButton'

export function CalendarTab() {
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState([])
  const [reminders, setReminders] = useState([])
  const [notifEnabled, setNotifEnabled] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [lastResult, setLastResult] = useState(null)
  
  // New visual calendar states
  const [selectedDate, setSelectedDate] = useState(new Date())
  const [currentMonth, setCurrentMonth] = useState(new Date())
  const [quickAddText, setQuickAddText] = useState('')
  
  const { recording, start, stop } = useRecorder()

  useEffect(() => {
    loadAll()
    checkNotifStatus()
    // Handle redirect back from Google OAuth
    if (window.location.search.includes('connected=1')) {
      window.history.replaceState({}, '', '/')
    }
  }, [])

  async function loadAll() {
    setLoading(true)
    try {
      const status = await getCalendarStatus()
      setConnected(status.connected)
      if (status.connected) {
        const [evts, rems] = await Promise.all([getEvents(), listReminders()])
        setEvents(evts)
        setReminders(rems)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function checkNotifStatus() {
    if (!('Notification' in window)) return
    setNotifEnabled(Notification.permission === 'granted')
  }

  async function enableNotifications() {
    const perm = await Notification.requestPermission()
    if (perm !== 'granted') return
    const reg = await navigator.serviceWorker.ready
    const { public_key } = await getVapidKey()
    if (!public_key) return
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    })
    await subscribePush(sub.toJSON())
    setNotifEnabled(true)
  }

  const handlePrevMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))
  }

  const handleNextMonth = () => {
    setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))
  }

  const isSameDay = (d1, d2) => {
    return d1.getFullYear() === d2.getFullYear() &&
           d1.getMonth() === d2.getMonth() &&
           d1.getDate() === d2.getDate();
  }

  const getDaysInMonth = (date) => {
    const year = date.getFullYear()
    const month = date.getMonth()
    const firstDayIndex = new Date(year, month, 1).getDay() // 0 = Sun
    const totalDays = new Date(year, month + 1, 0).getDate()
    
    const days = []
    
    // Fill previous month days
    const prevMonthTotalDays = new Date(year, month, 0).getDate()
    for (let i = firstDayIndex - 1; i >= 0; i--) {
      days.push({
        date: new Date(year, month - 1, prevMonthTotalDays - i),
        isCurrentMonth: false,
      })
    }
    
    // Fill current month days
    for (let i = 1; i <= totalDays; i++) {
      days.push({
        date: new Date(year, month, i),
        isCurrentMonth: true,
      })
    }
    
    // Fill next month days
    const remainingCells = 42 - days.length
    for (let i = 1; i <= remainingCells; i++) {
      days.push({
        date: new Date(year, month + 1, i),
        isCurrentMonth: false,
      })
    }
    
    return days
  }

  async function handleQuickAdd(e) {
    if (e) e.preventDefault()
    if (!quickAddText.trim()) return
    setSaving(true)
    setError(null)
    setLastResult(null)
    try {
      const year = selectedDate.getFullYear()
      const month = String(selectedDate.getMonth() + 1).padStart(2, '0')
      const day = String(selectedDate.getDate()).padStart(2, '0')
      const dateStr = `${year}-${month}-${day}`
      
      const reminder = await createReminderFromText(quickAddText.trim(), dateStr)
      setLastResult(`Reminder set: "${reminder.title}" at ${new Date(reminder.remind_at).toLocaleString()}`)
      setQuickAddText('')
      await loadAll()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleVoiceReminder() {
    setSaving(true)
    setError(null)
    setLastResult(null)
    try {
      const blob = await stop()
      const transcribeForm = new FormData()
      transcribeForm.append('audio', blob, 'reminder.webm')
      const captureRes = await fetch('/api/notes/capture', {
        method: 'POST',
        headers: { 'X-API-Key': localStorage.getItem('api_key') || '' },
        body: transcribeForm,
      })
      const note = await captureRes.json()
      
      const year = selectedDate.getFullYear()
      const month = String(selectedDate.getMonth() + 1).padStart(2, '0')
      const day = String(selectedDate.getDate()).padStart(2, '0')
      const dateStr = `${year}-${month}-${day}`

      const reminder = await createReminderFromText(note.raw_text, dateStr)
      setLastResult(`Reminder set: "${reminder.title}" at ${new Date(reminder.remind_at).toLocaleString()}`)
      await loadAll()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDeleteReminder(id) {
    await deleteReminder(id)
    setReminders((prev) => prev.filter((r) => r.id !== id))
  }

  if (loading) return <p className="status">Loading…</p>

  return (
    <div className="calendar-tab">
      {!connected ? (
        <div className="connect-box">
          <p>Connect Google Calendar to add reminders and see your events.</p>
          <button className="accent-btn" onClick={startOAuth}>Connect Google Calendar</button>
        </div>
      ) : (
        <>
          {!notifEnabled && (
            <div className="notif-banner">
              <span>Enable push notifications to get reminders on this device.</span>
              <button onClick={enableNotifications}>Enable</button>
            </div>
          )}

          {/* Month Navigation Header */}
          <div className="calendar-header-nav">
            <button className="nav-btn" onClick={handlePrevMonth}>&larr;</button>
            <span className="month-title">
              {currentMonth.toLocaleString('default', { month: 'long', year: 'numeric' })}
            </span>
            <button className="nav-btn" onClick={handleNextMonth}>&rarr;</button>
          </div>

          {/* Weekday Labels Header */}
          <div className="weekdays-grid">
            {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((d) => (
              <div key={d} className="weekday-label">{d}</div>
            ))}
          </div>

          {/* Days Grid */}
          <div className="calendar-grid">
            {getDaysInMonth(currentMonth).map(({ date, isCurrentMonth }, i) => {
              const isSelected = isSameDay(date, selectedDate)
              const isToday = isSameDay(date, new Date())
              
              const dayEvents = events.filter((e) => isSameDay(new Date(e.start), date))
              const dayReminders = reminders.filter((r) => isSameDay(new Date(r.remind_at), date))
              
              // Cap total dots at 3: prioritize events, then fill with reminders
              const eventDotsCount = Math.min(dayEvents.length, 3)
              const reminderDotsCount = Math.min(dayReminders.length, 3 - eventDotsCount)
              
              return (
                <div
                  key={i}
                  className={`calendar-day ${isCurrentMonth ? '' : 'outside-month'} ${isSelected ? 'selected' : ''} ${isToday ? 'today' : ''}`}
                  onClick={() => setSelectedDate(date)}
                >
                  <span className="day-number">{date.getDate()}</span>
                  <div className="day-indicators">
                    {dayEvents.slice(0, eventDotsCount).map((e) => (
                      <span key={e.id} className="indicator event" title={e.title}></span>
                    ))}
                    {dayReminders.slice(0, reminderDotsCount).map((r) => (
                      <span key={r.id} className="indicator reminder" title={r.title}></span>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>

          {/* Selected Date Schedule details view */}
          <div className="selected-day-schedule">
            <h3>Schedule for {selectedDate.toLocaleDateString('default', { weekday: 'long', month: 'short', day: 'numeric' })}</h3>
            
            <div className="schedule-lists">
              {/* Events list */}
              <div className="schedule-section">
                <h4>📅 Calendar Events</h4>
                <div className="schedule-items">
                  {events.filter((e) => isSameDay(new Date(e.start), selectedDate)).map((e) => (
                    <div key={e.id} className="schedule-item event-item">
                      <span className="item-title">{e.title}</span>
                      <span className="item-time">
                        {new Date(e.start).toLocaleTimeString('default', { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                  ))}
                  {events.filter((e) => isSameDay(new Date(e.start), selectedDate)).length === 0 && (
                    <p className="no-items">No calendar events today.</p>
                  )}
                </div>
              </div>

              {/* Reminders list */}
              <div className="schedule-section">
                <h4>🔔 Reminders</h4>
                <div className="schedule-items">
                  {reminders.filter((r) => isSameDay(new Date(r.remind_at), selectedDate)).map((r) => (
                    <div key={r.id} className="schedule-item reminder-item">
                      <div className="item-content">
                        <span className="item-title">{r.title}</span>
                        <span className="item-time">
                          {new Date(r.remind_at).toLocaleTimeString('default', { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      </div>
                      <button className="delete-btn" onClick={() => handleDeleteReminder(r.id)}>×</button>
                    </div>
                  ))}
                  {reminders.filter((r) => isSameDay(new Date(r.remind_at), selectedDate)).length === 0 && (
                    <p className="no-items">No reminders scheduled today.</p>
                  )}
                </div>
              </div>
            </div>

            {/* Quick-Add voice & text inputs in bottom bar */}
            <div className="bottom-bar">
              {saving && <p className="status">Saving reminder…</p>}
              {lastResult && <p className="status">{lastResult}</p>}
              {error && <p className="error">{error}</p>}
              
              <div className="quick-add-container">
                <form onSubmit={handleQuickAdd} className="quick-add-form">
                  <input
                    type="text"
                    placeholder={`Add reminder for ${selectedDate.toLocaleDateString('default', { month: 'short', day: 'numeric' })}…`}
                    value={quickAddText}
                    onChange={(e) => setQuickAddText(e.target.value)}
                    disabled={saving}
                  />
                  <button type="submit" disabled={saving || !quickAddText.trim()}>Add</button>
                </form>
                <div className="voice-mic-wrapper">
                  <VoiceButton
                    recording={recording}
                    onStart={start}
                    onStop={handleVoiceReminder}
                    label="🎤"
                    disabled={saving}
                  />
                </div>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

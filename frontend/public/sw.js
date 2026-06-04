/* global clients */
self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : { title: 'Assistant', body: '' }
  
  const options = {
    body: data.body,
    icon: '/icon-192.png',
  }
  
  if (data.reminder_id && data.api_key) {
    options.actions = [
      { action: 'done', title: 'Done' },
      { action: 'snooze', title: 'Snooze 15m' }
    ]
    options.data = {
      reminder_id: data.reminder_id,
      api_key: data.api_key
    }
  }

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  
  if (event.action === 'done' || event.action === 'snooze') {
    const { reminder_id, api_key } = event.notification.data || {}
    if (reminder_id && api_key) {
      const url = `/api/calendar/reminders/${reminder_id}/${event.action}`
      event.waitUntil(
        fetch(url, {
          method: 'POST',
          headers: {
            'X-API-Key': api_key
          }
        })
        .then(res => {
          if (!res.ok) throw new Error('API response not OK')
        })
        .catch(err => console.error('Failed to process reminder action:', err))
      )
    }
  } else {
    event.waitUntil(clients.openWindow('/'))
  }
})

import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../api'

function timeAgo(iso) {
  if (!iso) return ''
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

export default function ActivityPanel({ open, onClose, onView, onActivity, currentUser }) {
  const [events, setEvents] = useState([])
  const lastIdRef = useRef(0)
  const onActivityRef = useRef(onActivity)
  useEffect(() => { onActivityRef.current = onActivity }, [onActivity])

  // Poll for near-real-time updates while the panel is open
  useEffect(() => {
    if (!open) return
    let active = true
    const poll = async () => {
      try {
        const res = await apiFetch('/api/activity')
        if (!res.ok || !active) return
        const evs = (await res.json()).events ?? []
        setEvents(evs)
        const newest = evs.length ? evs[0].id : 0
        if (newest > lastIdRef.current) {
          if (lastIdRef.current !== 0) onActivityRef.current?.()  // refresh lists on genuinely new events
          lastIdRef.current = newest
        }
      } catch {}
    }
    poll()
    const t = setInterval(poll, 4000)
    return () => { active = false; clearInterval(t) }
  }, [open])

  if (!open) return null

  return (
    <aside className="fixed right-0 top-0 z-40 flex h-full w-80 flex-col border-l border-gray-200 bg-white shadow-2xl">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2.5 w-2.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-green-500" />
          </span>
          <h2 className="text-sm font-semibold text-gray-900">Activity</h2>
          <span className="text-xs text-gray-400">live</span>
        </div>
        <button onClick={onClose} className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {events.length === 0 ? (
          <p className="px-3 py-8 text-center text-sm text-gray-400">No recent activity</p>
        ) : (
          <ul className="space-y-1">
            {events.map((e) => {
              const who = e.actor === currentUser ? 'You' : e.actor
              const removed = e.action === 'removed'
              return (
                <li key={e.id} className="rounded-lg px-3 py-2 hover:bg-gray-50">
                  <div className="flex items-start gap-2">
                    <span className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs ${removed ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'}`}>
                      {removed ? '🗑' : '⬆'}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-gray-700">
                        <span className="font-semibold text-gray-900">{who}</span>{' '}
                        {removed ? 'removed' : 'uploaded'}{' '}
                        <span className="text-gray-600">{e.doc_name}</span>
                      </p>
                      <p className="mt-0.5 flex items-center gap-2 text-xs text-gray-400">
                        <span>{timeAgo(e.created_at)}</span>
                        {!removed && (
                          <button onClick={() => onView(e.doc_id)} className="text-blue-500 hover:text-blue-700 hover:underline">view</button>
                        )}
                      </p>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </aside>
  )
}

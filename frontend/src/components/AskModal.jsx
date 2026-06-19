import { useState, useRef, useEffect } from 'react'
import { apiFetch } from '../api'

export default function AskModal({ onClose, onViewSource }) {
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [turns, setTurns] = useState([])   // { q, answer, score, sources, message }
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns, busy])

  const ask = async (e) => {
    e?.preventDefault()
    const q = question.trim()
    if (!q || busy) return
    setQuestion('')
    setBusy(true)
    try {
      const res = await apiFetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })
      const data = await res.json()
      setTurns((t) => [...t, { q, ...data }])
    } catch {
      setTurns((t) => [...t, { q, answer: null, message: 'Something went wrong answering that.', sources: [] }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="flex h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <div className="flex items-center gap-2">
            <span className="text-lg">✨</span>
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Ask your documents</h2>
              <p className="text-xs text-gray-400">Answers are extracted from your own documents, with sources</p>
            </div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {turns.length === 0 && !busy && (
            <div className="py-10 text-center text-sm text-gray-400">
              <p className="mb-3">Ask a question about your documents, e.g.</p>
              {['What medications is Anna on?', 'Who had a fracture?', 'What was the diagnosis for the STEMI patient?'].map((ex) => (
                <button key={ex} onClick={() => setQuestion(ex)} className="mx-1 my-1 inline-block rounded-full border border-gray-200 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50">{ex}</button>
              ))}
            </div>
          )}

          {turns.map((t, i) => (
            <div key={i} className="space-y-2">
              <div className="flex justify-end">
                <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-blue-600 px-4 py-2 text-sm text-white">{t.q}</div>
              </div>
              <div className="max-w-[90%]">
                {t.answer ? (
                  <div className="rounded-2xl rounded-bl-sm border border-gray-200 bg-gray-50 px-4 py-3">
                    <p className={`whitespace-pre-wrap text-gray-900 ${t.mode === 'generative' ? 'text-sm leading-relaxed' : 'text-base font-semibold'}`}>{t.answer}</p>
                    <div className="mt-1.5 flex items-center gap-2 text-xs text-gray-500">
                      {t.mode === 'generative' ? (
                        <span className="rounded-full bg-violet-100 px-1.5 py-0.5 font-medium text-violet-700">✨ AI answer · grounded in your docs</span>
                      ) : (
                        <>
                          {t.answer_filename && <span>from <span className="font-medium">{t.answer_filename}</span></span>}
                          {t.score != null && <span className="rounded-full bg-gray-200 px-1.5 py-0.5">{Math.round(t.score * 100)}% extracted</span>}
                        </>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl rounded-bl-sm border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                    {t.message || 'No answer found.'}
                  </div>
                )}

                {t.sources?.length > 0 && (
                  <div className="mt-2">
                    <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-400">Sources</p>
                    <div className="space-y-1.5">
                      {t.sources.map((s) => (
                        <button key={s.id} onClick={() => onViewSource(s.id)} className="block w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-left hover:border-blue-300 hover:bg-blue-50 transition-colors">
                          <div className="flex items-center gap-2 text-sm font-medium text-gray-800">
                            <span>📄</span>
                            <span className="truncate">{s.filename}</span>
                            {s.folder_name && <span className="shrink-0 rounded-full bg-indigo-100 px-1.5 py-0.5 text-xs text-indigo-700">📁 {s.folder_name}</span>}
                          </div>
                          {s.snippet && <p className="mt-0.5 line-clamp-2 text-xs text-gray-500">{s.snippet}</p>}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {busy && (
            <div className="flex items-center gap-2 text-sm text-gray-400">
              <svg className="h-4 w-4 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
              Searching your documents…
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={ask} className="flex items-center gap-2 border-t p-3">
          <input
            autoFocus
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question…"
            className="flex-1 rounded-xl border border-gray-200 px-4 py-2.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-200"
          />
          <button type="submit" disabled={busy || !question.trim()} className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
            Ask
          </button>
        </form>
      </div>
    </div>
  )
}

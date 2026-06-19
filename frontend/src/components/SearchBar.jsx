import { useState, useEffect, useRef } from 'react'
import { apiFetch } from '../api'

const PLACEHOLDERS = [
  'Try: reports mentioning Anna',
  'Try: lab reports with abnormal results',
  'Try: patients aged 50-60',
  'Try: Dr. Priya Nair',
]

const TYPE_STYLE = {
  patient: 'bg-blue-100 text-blue-600',
  doctor: 'bg-purple-100 text-purple-600',
  diagnosis: 'bg-emerald-100 text-emerald-700',
}

export default function SearchBar({ value, onChange, isLoading, semantic, onSemanticChange }) {
  const [phIdx, setPhIdx] = useState(0)
  const [suggestions, setSuggestions] = useState([])
  const [showSugg, setShowSugg] = useState(false)
  const suggTimer = useRef(null)

  useEffect(() => {
    if (value) return
    const id = setInterval(() => setPhIdx((i) => (i + 1) % PLACEHOLDERS.length), 3000)
    return () => clearInterval(id)
  }, [value])

  useEffect(() => {
    clearTimeout(suggTimer.current)
    if (!value || value.length < 2) { setSuggestions([]); return }
    suggTimer.current = setTimeout(async () => {
      try {
        const res = await apiFetch(`/api/suggest?q=${encodeURIComponent(value)}`)
        const data = await res.json()
        setSuggestions(data.suggestions ?? [])
        setShowSugg(true)
      } catch { setSuggestions([]) }
    }, 200)
  }, [value])

  const pick = (text) => { onChange(text); setShowSugg(false) }

  return (
    <div>
      <div className="mb-2 flex items-center justify-end gap-2">
        <span className="text-sm text-gray-600">Semantic Search</span>
        <button
          type="button"
          role="switch"
          aria-checked={semantic}
          onClick={() => onSemanticChange(!semantic)}
          title={semantic ? 'Hybrid keyword + meaning search (on)' : 'Keyword-only search (off)'}
          className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${semantic ? 'bg-blue-600' : 'bg-gray-300'}`}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${semantic ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </button>
      </div>

      <div className="relative">
        <div className="pointer-events-none absolute inset-y-0 left-4 flex items-center">
        {isLoading ? (
          <svg className="h-5 w-5 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <svg className="h-5 w-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        )}
      </div>

      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => suggestions.length > 0 && setShowSugg(true)}
        onBlur={() => setTimeout(() => setShowSugg(false), 150)}
        placeholder={PLACEHOLDERS[phIdx]}
        className="w-full rounded-xl border border-gray-200 bg-white py-4 pl-12 pr-10 text-base shadow-sm placeholder:text-gray-400 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-200 transition-all"
      />

      {value && (
        <button
          onClick={() => { onChange(''); setSuggestions([]) }}
          className="absolute inset-y-0 right-4 flex items-center text-gray-400 hover:text-gray-600"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}

      {showSugg && suggestions.length > 0 && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-xl border border-gray-200 bg-white shadow-lg">
          {suggestions.map((s, i) => (
            <button
              key={i}
              onMouseDown={() => pick(s.text)}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-sm hover:bg-gray-50 transition-colors"
            >
              <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium ${TYPE_STYLE[s.type] ?? 'bg-gray-100 text-gray-600'}`}>
                {s.type}
              </span>
              <span className="text-gray-800">{s.text}</span>
            </button>
          ))}
        </div>
      )}
      </div>
    </div>
  )
}

const FILE_TYPES = [{ value: 'pdf', label: 'PDF' }, { value: 'image', label: 'Image' }, { value: 'docx', label: 'DOCX' }]
const DOC_TYPES = [
  { value: 'lab_report', label: 'Lab Report' },
  { value: 'patient_report', label: 'Patient Report' },
  { value: 'prescription', label: 'Prescription' },
  { value: 'discharge_summary', label: 'Discharge' },
  { value: 'general', label: 'General' },
]

function Checkbox({ checked, onChange, label, count }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-2 group">
      <div className="flex items-center gap-2">
        <input type="checkbox" checked={checked} onChange={onChange} className="h-3.5 w-3.5 rounded border-gray-600 bg-gray-800 accent-blue-500" />
        <span className="text-sm text-gray-300 group-hover:text-white transition-colors">{label}</span>
      </div>
      {count != null && <span className="text-xs text-gray-500">{count}</span>}
    </label>
  )
}

export default function FilterSidebar({ filters, onChange, availableLanguages, aggregations, folders = [] }) {
  const update = (key, value) => onChange((prev) => ({ ...prev, [key]: value }))
  const toggleArr = (key, value) => onChange((prev) => ({
    ...prev,
    [key]: prev[key].includes(value) ? prev[key].filter((v) => v !== value) : [...prev[key], value],
  }))

  const clearAll = () => onChange({ fileTypes: [], language: '', dateFrom: '', dateTo: '', minConfidence: 0, documentTypes: [], ageMin: '', ageMax: '', onlyAbnormal: false, folderId: '' })

  const hasFilters = filters.fileTypes.length > 0 || filters.documentTypes.length > 0 || filters.language || filters.dateFrom || filters.dateTo || filters.minConfidence > 0 || filters.ageMin !== '' || filters.ageMax !== '' || filters.onlyAbnormal || filters.folderId

  const typeCount = (type) => aggregations?.by_document_type?.[type]

  return (
    <aside className="w-52 shrink-0">
      <div className="sticky top-4 rounded-xl bg-[#0f0f0f] p-4 text-white space-y-5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Filters</span>
          {hasFilters && <button onClick={clearAll} className="text-xs text-blue-400 hover:text-blue-300 transition-colors">Clear all</button>}
        </div>

        <div>
          <p className="mb-2 text-xs font-medium text-gray-400">Folders</p>
          <div className="space-y-1">
            {[{ id: '', label: 'All documents' }, { id: 'standalone', label: 'Standalone' }].map((o) => (
              <button
                key={o.id}
                onClick={() => update('folderId', o.id)}
                className={`flex w-full items-center justify-between rounded px-2 py-1 text-sm transition-colors ${String(filters.folderId) === o.id ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800'}`}
              >
                <span>{o.label}</span>
              </button>
            ))}
            {folders.map((f) => (
              <button
                key={f.id}
                onClick={() => update('folderId', f.id)}
                className={`flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-sm transition-colors ${String(filters.folderId) === String(f.id) ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800'}`}
              >
                <span className="truncate">📁 {f.name}</span>
                <span className="shrink-0 text-xs opacity-70">{f.doc_count}</span>
              </button>
            ))}
            {folders.length === 0 && <p className="px-2 text-xs text-gray-600">No folders yet</p>}
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium text-gray-400">Document Type</p>
          <div className="space-y-1.5">
            {DOC_TYPES.map(({ value, label }) => (
              <Checkbox key={value} checked={filters.documentTypes.includes(value)} onChange={() => toggleArr('documentTypes', value)} label={label} count={typeCount(value)} />
            ))}
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium text-gray-400">File Type</p>
          <div className="space-y-1.5">
            {FILE_TYPES.map(({ value, label }) => (
              <Checkbox key={value} checked={filters.fileTypes.includes(value)} onChange={() => toggleArr('fileTypes', value)} label={label} />
            ))}
          </div>
        </div>

        <Checkbox checked={filters.onlyAbnormal} onChange={(e) => update('onlyAbnormal', e.target.checked)} label="Abnormal results only" />

        <div>
          <p className="mb-2 text-xs font-medium text-gray-400">Patient Age</p>
          <div className="flex gap-2">
            <input type="number" min="0" max="130" value={filters.ageMin} onChange={(e) => update('ageMin', e.target.value)} placeholder="Min" className="w-full rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500" />
            <input type="number" min="0" max="130" value={filters.ageMax} onChange={(e) => update('ageMax', e.target.value)} placeholder="Max" className="w-full rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500" />
          </div>
        </div>

        {availableLanguages.length > 0 && (
          <div>
            <p className="mb-2 text-xs font-medium text-gray-400">Language</p>
            <select value={filters.language} onChange={(e) => update('language', e.target.value)} className="w-full rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500">
              <option value="">All</option>
              {availableLanguages.map((lang) => <option key={lang} value={lang}>{lang.toUpperCase()}</option>)}
            </select>
          </div>
        )}

        <div>
          <p className="mb-2 text-xs font-medium text-gray-400">Upload Date</p>
          <div className="space-y-2">
            <input type="date" value={filters.dateFrom} onChange={(e) => update('dateFrom', e.target.value)} className="w-full rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500" />
            <input type="date" value={filters.dateTo} onChange={(e) => update('dateTo', e.target.value)} className="w-full rounded-lg border border-gray-700 bg-gray-800 px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-blue-500" />
          </div>
        </div>

        <div>
          <p className="mb-2 text-xs font-medium text-gray-400">Min Confidence: <span className="font-semibold text-white">{filters.minConfidence}%</span></p>
          <input type="range" min="0" max="100" value={filters.minConfidence} onChange={(e) => update('minConfidence', Number(e.target.value))} className="w-full accent-blue-500" />
        </div>
      </div>
    </aside>
  )
}

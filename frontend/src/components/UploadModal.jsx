import { useState, useRef, useCallback } from 'react'
import { apiFetch } from '../api'

const DOC_TYPE_LABEL = {
  lab_report: 'Lab Report',
  patient_report: 'Patient Report',
  prescription: 'Prescription',
  discharge_summary: 'Discharge Summary',
  general: 'General',
}

const DOC_TYPE_COLOR = {
  lab_report: 'bg-emerald-100 text-emerald-700',
  patient_report: 'bg-blue-100 text-blue-700',
  prescription: 'bg-purple-100 text-purple-700',
  discharge_summary: 'bg-amber-100 text-amber-700',
  general: 'bg-gray-100 text-gray-600',
}

function MetadataPreview({ meta }) {
  const docType = meta.document_type ?? 'general'

  return (
    <div className="mt-4 rounded-xl border border-green-200 bg-green-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-semibold text-green-800">Document processed</p>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${DOC_TYPE_COLOR[docType]}`}>
          {DOC_TYPE_LABEL[docType]}
        </span>
      </div>

      {meta.has_abnormal_results && (
        <div className="mb-3 flex items-center gap-1.5 rounded-lg bg-red-100 px-3 py-2 text-xs font-semibold text-red-700">
          <svg className="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
          {meta.critical_flags_count} abnormal lab result{meta.critical_flags_count !== 1 ? 's' : ''} detected
        </div>
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        {meta.patient_name && (
          <div className="col-span-2">
            <span className="text-gray-500">Patient: </span>
            <span className="font-medium">{meta.patient_name}</span>
          </div>
        )}
        {meta.doctor_name && (
          <div className="col-span-2">
            <span className="text-gray-500">Doctor: </span>
            <span className="font-medium">{meta.doctor_name}</span>
          </div>
        )}
        {meta.patient_age != null && (
          <div>
            <span className="text-gray-500">Age: </span>
            <span className="font-medium">{meta.patient_age}</span>
          </div>
        )}
        {meta.language && (
          <div>
            <span className="text-gray-500">Language: </span>
            <span className="font-medium">{meta.language.toUpperCase()}</span>
          </div>
        )}
        {meta.word_count != null && (
          <div>
            <span className="text-gray-500">Words: </span>
            <span className="font-medium">{meta.word_count.toLocaleString()}</span>
          </div>
        )}
        {meta.page_count != null && (
          <div>
            <span className="text-gray-500">Pages: </span>
            <span className="font-medium">{meta.page_count}</span>
          </div>
        )}
        {meta.confidence_score != null && (
          <div>
            <span className="text-gray-500">Confidence: </span>
            <span className="font-medium">
              {meta.confidence_score > 0 ? `${Math.round(meta.confidence_score)}%` : 'N/A'}
            </span>
          </div>
        )}
      </div>

      {meta.diagnoses?.length > 0 && (
        <div className="mt-2 text-xs">
          <span className="text-gray-500">Diagnoses: </span>
          <span className="font-medium">{meta.diagnoses.slice(0, 3).join('; ')}</span>
        </div>
      )}
      {meta.medications?.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {meta.medications.slice(0, 6).map((m, i) => (
            <span key={i} className="rounded-full border border-purple-200 bg-white px-2 py-0.5 text-xs text-purple-700">
              {m}
            </span>
          ))}
        </div>
      )}
      {meta.persons_mentioned?.length > 0 && (
        <div className="mt-1 text-xs">
          <span className="text-gray-500">Persons: </span>
          <span className="font-medium">{meta.persons_mentioned.join(', ')}</span>
        </div>
      )}
      {meta.keywords?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {meta.keywords.map((kw, i) => (
            <span key={i} className="rounded-full border border-green-300 bg-white px-2 py-0.5 text-xs text-green-700">
              {kw}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

export default function UploadModal({ isOpen, onClose, onUploadSuccess }) {
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [uploadedMeta, setUploadedMeta] = useState(null)
  const [error, setError] = useState(null)
  const [uploadedId, setUploadedId] = useState(null)
  const [suggestion, setSuggestion] = useState(null)
  const [folders, setFolders] = useState([])
  const [assigned, setAssigned] = useState(null)
  const [assigning, setAssigning] = useState(false)
  const [selectedFolder, setSelectedFolder] = useState('')
  const [newFolderName, setNewFolderName] = useState('')
  const [creatingNew, setCreatingNew] = useState(false)
  const fileInputRef = useRef(null)
  const progressRef = useRef(null)

  const uploadFile = useCallback(async (file) => {
    setIsUploading(true)
    setProgress(0)
    setError(null)
    setUploadedMeta(null)
    setUploadedId(null)
    setSuggestion(null)
    setAssigned(null)
    setSelectedFolder('')
    setNewFolderName('')
    setCreatingNew(false)

    const formData = new FormData()
    formData.append('file', file)

    progressRef.current = setInterval(() => {
      setProgress((p) => Math.min(p + 8, 88))
    }, 400)

    try {
      const res = await apiFetch('/api/upload', { method: 'POST', body: formData })
      clearInterval(progressRef.current)
      setProgress(100)

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail ?? `Upload failed (${res.status})`)
      }

      const data = await res.json()
      setUploadedMeta(data.metadata)
      setUploadedId(data.id)
      setSuggestion(data.folder_suggestion ?? null)
      setFolders(data.folders ?? [])
      setSelectedFolder(data.folder_suggestion ? String(data.folder_suggestion.id) : '')
      onUploadSuccess()
    } catch (err) {
      clearInterval(progressRef.current)
      setProgress(0)
      setError(err.message)
    } finally {
      setIsUploading(false)
    }
  }, [onUploadSuccess])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadFile(file)
  }, [uploadFile])

  const handleFileChange = (e) => {
    const file = e.target.files[0]
    if (file) uploadFile(file)
    e.target.value = ''
  }

  const assign = useCallback(async (payload) => {
    if (!uploadedId) return
    setAssigning(true)
    setError(null)
    try {
      const res = await apiFetch(`/api/documents/${uploadedId}/folder`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error()
      const data = await res.json()
      setAssigned(data.folder_name ?? 'standalone')
      onUploadSuccess()
    } catch { setError('Could not save folder choice.') }
    finally { setAssigning(false) }
  }, [uploadedId, onUploadSuccess])

  const handleClose = () => {
    if (isUploading || assigning) return
    setUploadedMeta(null)
    setUploadedId(null)
    setSuggestion(null)
    setAssigned(null)
    setError(null)
    setProgress(0)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <h2 className="text-lg font-semibold">Upload Document</h2>
          <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 transition-colors">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="p-6">
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`cursor-pointer rounded-xl border-2 border-dashed p-8 text-center transition-colors ${
              isDragging ? 'border-blue-400 bg-blue-50' : 'border-gray-200 hover:border-blue-300 hover:bg-gray-50'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,.docx"
              onChange={handleFileChange}
              className="hidden"
            />
            <svg className="mx-auto mb-3 h-10 w-10 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            <p className="text-sm font-medium text-gray-700">Drop file here or click to browse</p>
            <p className="mt-1 text-xs text-gray-400">PDF, PNG, JPG, JPEG, DOCX · Max 50 MB</p>
          </div>

          {isUploading && (
            <div className="mt-4">
              <div className="mb-1 flex justify-between text-xs text-gray-500">
                <span>Running OCR &amp; extracting metadata…</span>
                <span>{progress}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-gray-100">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {error && (
            <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {uploadedMeta && <MetadataPreview meta={uploadedMeta} />}

          {uploadedMeta && assigned == null && (
            <div className="mt-4 rounded-xl border border-blue-200 bg-blue-50 p-4">
              <p className="mb-2 text-sm font-semibold text-blue-900">Organize into a folder</p>

              {suggestion && (
                <button
                  onClick={() => assign({ folder_id: suggestion.id })}
                  disabled={assigning}
                  className={`mb-3 flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left text-sm transition-colors disabled:opacity-50 ${suggestion.confident ? 'border-blue-300 bg-white hover:bg-blue-100' : 'border-gray-200 bg-white hover:bg-gray-50'}`}
                >
                  <span>📁 {suggestion.confident ? 'Looks like' : 'Closest match:'} <span className="font-semibold">{suggestion.name}</span></span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${suggestion.confident ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-600'}`}>{Math.round(suggestion.score * 100)}% · Add</span>
                </button>
              )}

              <p className="mb-1 text-xs text-gray-500">{suggestion ? 'Or choose:' : 'Choose:'}</p>

              {creatingNew ? (
                <div className="flex gap-2">
                  <input
                    autoFocus
                    value={newFolderName}
                    onChange={(e) => setNewFolderName(e.target.value)}
                    placeholder="New folder name"
                    className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-200"
                  />
                  <button onClick={() => newFolderName.trim() && assign({ new_folder: newFolderName.trim() })} disabled={assigning || !newFolderName.trim()} className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">Create</button>
                  <button onClick={() => setCreatingNew(false)} className="rounded-lg px-2 text-sm text-gray-500 hover:text-gray-700">✕</button>
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <select
                    value={selectedFolder}
                    onChange={(e) => setSelectedFolder(e.target.value)}
                    className="flex-1 rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-200"
                  >
                    <option value="">Select a folder…</option>
                    {folders.map((f) => <option key={f.id} value={f.id}>{f.name} ({f.doc_count})</option>)}
                  </select>
                  <button onClick={() => selectedFolder && assign({ folder_id: Number(selectedFolder) })} disabled={assigning || !selectedFolder} className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">Add</button>
                  <button onClick={() => setCreatingNew(true)} className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50">+ New</button>
                </div>
              )}

              <button
                onClick={() => assign({})}
                disabled={assigning}
                className="mt-3 w-full rounded-lg border border-gray-200 bg-white py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                Keep as standalone document
              </button>
            </div>
          )}

          {assigned != null && (
            <div className="mt-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
              {assigned === 'standalone' ? '✓ Kept as a standalone document.' : <>✓ Added to <span className="font-semibold">{assigned}</span>.</>}
            </div>
          )}

          {uploadedMeta && (
            <button
              onClick={handleClose}
              className="mt-4 w-full rounded-lg bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
            >
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

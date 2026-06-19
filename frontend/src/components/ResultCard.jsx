const FILE_TYPE_BADGE = {
  pdf: 'bg-red-100 text-red-700',
  image: 'bg-emerald-100 text-emerald-700',
  docx: 'bg-blue-100 text-blue-700',
}
const DOC_TYPE_BADGE = {
  lab_report: 'bg-emerald-100 text-emerald-700',
  patient_report: 'bg-blue-100 text-blue-700',
  prescription: 'bg-purple-100 text-purple-700',
  discharge_summary: 'bg-amber-100 text-amber-700',
  general: 'bg-gray-100 text-gray-600',
}
const DOC_TYPE_LABEL = {
  lab_report: 'Lab Report', patient_report: 'Patient Report',
  prescription: 'Prescription', discharge_summary: 'Discharge', general: 'General',
}
const MATCH_BADGE = {
  keyword: { label: '🔵 Keyword', cls: 'bg-blue-100 text-blue-700', title: 'Matched by exact words' },
  semantic: { label: '🟣 Semantic', cls: 'bg-purple-100 text-purple-700', title: 'Matched by meaning' },
  both: { label: '🟢 Both', cls: 'bg-green-100 text-green-700', title: 'Matched by words and meaning' },
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

function highlight(text, query) {
  if (!query || !text) return <span>{text}</span>
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const parts = text.split(new RegExp(`(${escaped})`, 'gi'))
  return <>{parts.map((p, i) => i % 2 === 1 ? <mark key={i} className="bg-yellow-200 rounded px-0.5">{p}</mark> : <span key={i}>{p}</span>)}</>
}

function HighlightedSnippet({ raw }) {
  const parts = raw.split(/(<em>[\s\S]*?<\/em>)/g)
  return <span>{parts.map((p, i) => p.startsWith('<em>') ? <mark key={i} className="rounded bg-yellow-200 px-0.5 not-italic">{p.slice(4, -5)}</mark> : <span key={i}>{p}</span>)}</span>
}

export default function ResultCard({ document: doc, searchQuery, onViewDetails, onDelete, onIcd10Click, onSimilarDocs, onPreview, currentUser }) {
  const snippets = doc.highlight?.content ?? []
  const fallback = doc.content?.slice(0, 300) ?? ''
  const docType = doc.document_type ?? 'general'

  return (
    <article className="rounded-xl border border-gray-200 bg-white p-5 transition-all hover:border-blue-200 hover:shadow-sm">
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          {/* Badge row */}
          <div className="flex flex-wrap items-center gap-2 mb-1">
            {doc.match_type && MATCH_BADGE[doc.match_type] && (
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${MATCH_BADGE[doc.match_type].cls}`} title={MATCH_BADGE[doc.match_type].title}>
                {MATCH_BADGE[doc.match_type].label}
              </span>
            )}
            <span className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase ${FILE_TYPE_BADGE[doc.file_type] ?? 'bg-gray-100 text-gray-600'}`}>{doc.file_type}</span>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${DOC_TYPE_BADGE[docType]}`}>{DOC_TYPE_LABEL[docType] ?? docType}</span>
            {doc.low_ocr_quality && (
              <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-semibold text-orange-700">Low OCR Quality</span>
            )}
            {doc.has_abnormal_results && (
              <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700 flex items-center gap-1">
                <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" /></svg>
                Abnormal
              </span>
            )}
            {doc.folder_name && (
              <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">📁 {doc.folder_name}</span>
            )}
            {doc.owner && (
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">👤 {doc.owner === currentUser ? 'You' : doc.owner}</span>
            )}
            <h3 className="truncate text-base font-semibold text-gray-900">{doc.filename}</h3>
          </div>

          {/* Patient / doctor */}
          {(doc.patient_name || doc.doctor_name) && (
            <div className="mt-1.5 flex flex-wrap gap-3 text-xs text-gray-600">
              {doc.patient_name && (
                <span>
                  {doc.patient_gender === 'male' ? '♂ ' : doc.patient_gender === 'female' ? '♀ ' : ''}
                  <span className="text-gray-400">Patient: </span>
                  <span className="font-semibold text-gray-800">{highlight(doc.patient_name, searchQuery)}</span>
                </span>
              )}
              {doc.doctor_name && (
                <span>
                  <span className="text-gray-400">Doctor: </span>
                  <span className="font-semibold text-gray-800">{highlight(doc.doctor_name, searchQuery)}</span>
                </span>
              )}
              {doc.patient_age != null && <span><span className="text-gray-400">Age: </span><span className="font-medium text-gray-800">{doc.patient_age}</span></span>}
            </div>
          )}

          {/* Snippet */}
          <p className="mt-2 line-clamp-3 font-mono text-sm leading-relaxed text-gray-600">
            {snippets.length > 0 ? <HighlightedSnippet raw={snippets[0]} /> : fallback}
          </p>

          {/* Diagnoses */}
          {doc.diagnoses?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {doc.diagnoses.slice(0, 3).map((d, i) => (
                <span key={i} className="rounded-full border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs text-blue-700">{d}</span>
              ))}
            </div>
          )}

          {/* ICD-10 codes — clickable */}
          {doc.icd10_codes?.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {doc.icd10_codes.slice(0, 6).map((code, i) => (
                <button
                  key={i}
                  onClick={() => onIcd10Click(code)}
                  className="rounded-full border border-gray-300 bg-gray-50 px-2 py-0.5 text-xs font-mono text-gray-700 hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700 transition-colors"
                  title={`Search for ${code}`}
                >
                  {code}
                </button>
              ))}
            </div>
          )}

          {/* Medications */}
          {doc.medications?.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {doc.medications.slice(0, 4).map((m, i) => (
                <span key={i} className="rounded-full border border-purple-200 bg-purple-50 px-2 py-0.5 text-xs text-purple-700">{m}</span>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="shrink-0 flex flex-col items-end gap-2">
          <button onClick={() => onPreview(doc)} className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors whitespace-nowrap">
            <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
            View
          </button>
          <button onClick={() => onViewDetails(doc)} className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition-colors whitespace-nowrap">
            Full text
          </button>
          <button onClick={() => onSimilarDocs(doc)} className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition-colors whitespace-nowrap">
            Similar docs
          </button>
          <button onClick={() => onDelete(doc.id)} className="text-sm text-gray-400 hover:text-red-500 transition-colors">Delete</button>
        </div>
      </div>

      {/* Metadata row */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-gray-100 pt-3 text-xs text-gray-500">
        <span>{formatDate(doc.uploaded_at)}</span>
        {doc.word_count > 0 && <span>{doc.word_count.toLocaleString()} words</span>}
        {doc.page_count > 0 && <span>{doc.page_count} page{doc.page_count !== 1 ? 's' : ''}</span>}
        {doc.confidence_score > 0 && <span>OCR {Math.round(doc.confidence_score)}%</span>}
        {doc.critical_flags_count > 0 && <span className="text-red-600 font-medium">{doc.critical_flags_count} abnormal flag{doc.critical_flags_count !== 1 ? 's' : ''}</span>}
        {doc.language && <span className="uppercase">{doc.language}</span>}
      </div>
    </article>
  )
}

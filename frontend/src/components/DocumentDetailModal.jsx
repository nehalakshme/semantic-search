const DOC_TYPE_LABEL = { lab_report: 'Lab Report', patient_report: 'Patient Report', prescription: 'Prescription', discharge_summary: 'Discharge Summary', general: 'General' }
const DOC_TYPE_COLOR = { lab_report: 'bg-emerald-100 text-emerald-700', patient_report: 'bg-blue-100 text-blue-700', prescription: 'bg-purple-100 text-purple-700', discharge_summary: 'bg-amber-100 text-amber-700', general: 'bg-gray-100 text-gray-600' }

function MetaItem({ label, value }) {
  if (value == null || value === '') return null
  return <div><dt className="text-xs uppercase tracking-wider text-gray-500">{label}</dt><dd className="mt-0.5 text-sm text-gray-900">{value}</dd></div>
}

function TagGroup({ label, items }) {
  if (!items?.length) return null
  return (
    <div>
      <dt className="mb-1 text-xs uppercase tracking-wider text-gray-500">{label}</dt>
      <dd className="flex flex-wrap gap-1">{items.map((item, i) => <span key={i} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700">{item}</span>)}</dd>
    </div>
  )
}

function VitalsGrid({ doc }) {
  const vitals = [
    { label: 'Blood Pressure', value: doc.vital_blood_pressure, icon: '🫀' },
    { label: 'Heart Rate', value: doc.vital_heart_rate, icon: '💓' },
    { label: 'Temperature', value: doc.vital_temperature, icon: '🌡' },
    { label: 'SpO₂', value: doc.vital_spo2, icon: '🫁' },
    { label: 'BMI', value: doc.vital_bmi, icon: '⚖' },
  ].filter((v) => v.value)

  if (!vitals.length) return null

  return (
    <div>
      <dt className="mb-2 text-xs uppercase tracking-wider text-gray-500">Vital Signs</dt>
      <dd className="grid grid-cols-2 gap-2">
        {vitals.map((v) => (
          <div key={v.label} className="rounded-lg bg-blue-50 border border-blue-100 px-3 py-2">
            <div className="text-xs text-gray-500">{v.icon} {v.label}</div>
            <div className="font-semibold text-gray-900 text-sm mt-0.5">{v.value}</div>
          </div>
        ))}
      </dd>
    </div>
  )
}

function LabResultsTable({ tests }) {
  if (!tests?.length) return null
  const FLAG_STYLE = { HIGH: 'bg-red-100 text-red-700', LOW: 'bg-orange-100 text-orange-700', NORMAL: 'bg-green-100 text-green-700' }
  return (
    <div className="mt-4">
      <h4 className="mb-2 text-sm font-semibold text-gray-900">
        Lab Results
        {tests.some((t) => t.flag !== 'NORMAL') && (
          <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
            {tests.filter((t) => t.flag !== 'NORMAL').length} abnormal
          </span>
        )}
      </h4>
      <div className="overflow-hidden rounded-lg border border-gray-200">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50 text-left text-gray-500">
              <th className="border-b border-gray-200 p-2 font-medium">Test</th>
              <th className="border-b border-gray-200 p-2 font-medium">Result</th>
              <th className="border-b border-gray-200 p-2 font-medium text-center">Flag</th>
            </tr>
          </thead>
          <tbody>
            {tests.map((test, i) => (
              <tr key={i} className={test.flag !== 'NORMAL' ? 'bg-red-50' : i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                <td className="border-b border-gray-100 p-2 text-gray-800">{test.name}</td>
                <td className="border-b border-gray-100 p-2 font-mono text-gray-800">{test.result}</td>
                <td className="border-b border-gray-100 p-2 text-center">
                  <span className={`inline-block rounded-full px-2 py-0.5 font-semibold ${FLAG_STYLE[test.flag] ?? FLAG_STYLE.NORMAL}`}>{test.flag}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

import { getToken } from '../api'

export default function DocumentDetailModal({ document: doc, onClose }) {
  if (!doc) return null
  const downloadUrl = `/api/files/${doc.id}?token=${encodeURIComponent(getToken() ?? '')}`
  const docType = doc.document_type ?? 'general'

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-black/60 px-4 py-10" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="mx-auto w-full max-w-4xl rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b px-6 py-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${DOC_TYPE_COLOR[docType]}`}>{DOC_TYPE_LABEL[docType]}</span>
              {doc.has_abnormal_results && <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-semibold text-red-700">⚠ Abnormal Results</span>}
              {doc.low_ocr_quality && <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-semibold text-orange-700">Low OCR Quality</span>}
            </div>
            <h2 className="truncate text-lg font-semibold text-gray-900">{doc.filename}</h2>
            <p className="mt-0.5 text-sm text-gray-500">
              {doc.file_type?.toUpperCase()}{doc.word_count ? ` · ${doc.word_count.toLocaleString()} words` : ''}{doc.uploaded_at ? ` · ${new Date(doc.uploaded_at).toLocaleString()}` : ''}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <a href={downloadUrl} download={doc.filename} className="inline-flex items-center gap-1.5 rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200 transition-colors">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
              Download
            </a>
            <button onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-6 p-6">
          <div className="col-span-1 space-y-4 overflow-y-auto max-h-[540px] pr-1">
            <h3 className="font-semibold text-gray-900">Metadata</h3>
            <dl className="space-y-3">
              <MetaItem label="Patient" value={doc.patient_name} />
              <MetaItem label="Gender" value={doc.patient_gender} />
              <MetaItem label="Doctor" value={doc.doctor_name} />
              <MetaItem label="Age" value={doc.patient_age} />
              <MetaItem label="Language" value={doc.language?.toUpperCase()} />
              <MetaItem label="Pages" value={doc.page_count} />
              <MetaItem label="Words" value={doc.word_count?.toLocaleString()} />
              <MetaItem label="OCR Confidence" value={doc.confidence_score > 0 ? `${Math.round(doc.confidence_score)}%` : 'N/A'} />
              <MetaItem label="Processing Time" value={doc.processing_time_seconds ? `${doc.processing_time_seconds}s` : null} />
              <VitalsGrid doc={doc} />
              <TagGroup label="ICD-10 Codes" items={doc.icd10_codes} />
              <TagGroup label="Diagnoses" items={doc.diagnoses} />
              <TagGroup label="Medications" items={doc.medications} />
              <TagGroup label="Dosages" items={doc.dosage_mentioned} />
              <TagGroup label="Persons" items={doc.persons_mentioned} />
              <TagGroup label="Organizations" items={doc.organizations_mentioned} />
              <TagGroup label="Dates" items={doc.dates_in_document} />
              <TagGroup label="Keywords" items={doc.keywords} />
            </dl>
            {doc.lab_tests?.length > 0 && <LabResultsTable tests={doc.lab_tests} />}
          </div>

          <div className="col-span-2">
            <h3 className="mb-3 font-semibold text-gray-900">Extracted Text</h3>
            <div className="h-[540px] overflow-y-auto rounded-xl border border-gray-200 bg-gray-50 p-4 font-mono text-sm leading-relaxed text-gray-700 whitespace-pre-wrap">
              {doc.content?.trim() || 'No text was extracted from this document.'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

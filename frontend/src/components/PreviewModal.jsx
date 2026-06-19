import { getToken } from '../api'

export default function PreviewModal({ document: doc, onClose }) {
  if (!doc) return null
  const token = encodeURIComponent(getToken() ?? '')
  const previewUrl = `/api/files/${doc.id}?token=${token}&inline=1`
  const downloadUrl = `/api/files/${doc.id}?token=${token}`
  const type = doc.file_type

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/70 p-4 sm:p-8" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="mx-auto flex h-full w-full max-w-4xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between gap-4 border-b px-5 py-3">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-gray-900">{doc.filename}</h2>
            <p className="text-xs text-gray-400">{type?.toUpperCase()} preview</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <a href={downloadUrl} download={doc.filename} className="inline-flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 transition-colors">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
              Download
            </a>
            <button onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto bg-gray-100">
          {type === 'image' ? (
            <div className="flex h-full items-center justify-center p-4">
              <img src={previewUrl} alt={doc.filename} className="max-h-full max-w-full object-contain shadow" />
            </div>
          ) : type === 'pdf' ? (
            <iframe src={previewUrl} title={doc.filename} className="h-full w-full" />
          ) : (
            // DOCX and anything else can't render in-browser — show extracted text
            <div className="h-full overflow-auto p-6">
              <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                In-browser preview isn’t available for {type?.toUpperCase()} files — showing the extracted text. Use Download for the original.
              </div>
              <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-gray-700">
                {doc.content?.trim() || 'No text was extracted from this document.'}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function EmptyState({ hasQuery, onUploadClick }) {
  return (
    <div className="flex flex-col items-center justify-center py-28 text-center">
      <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-gray-100">
        <svg className="h-8 w-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      </div>

      {hasQuery ? (
        <>
          <h3 className="text-lg font-semibold text-gray-900">No results found</h3>
          <p className="mt-1 max-w-sm text-sm text-gray-500">
            No documents matched your query. Try different keywords, person names, or dates.
          </p>
        </>
      ) : (
        <>
          <h3 className="text-lg font-semibold text-gray-900">No documents yet</h3>
          <p className="mt-1 max-w-sm text-sm text-gray-500">
            Upload a PDF, image, or DOCX file to get started. DocuSearch will run OCR and extract
            people, dates, and organizations automatically.
          </p>
          <button
            onClick={onUploadClick}
            className="mt-5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            Upload your first document
          </button>
        </>
      )}
    </div>
  )
}

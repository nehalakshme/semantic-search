import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import Header from './components/Header'
import StatsBar from './components/StatsBar'
import UploadModal from './components/UploadModal'
import SearchBar from './components/SearchBar'
import FilterSidebar from './components/FilterSidebar'
import ResultCard from './components/ResultCard'
import DocumentDetailModal from './components/DocumentDetailModal'
import PreviewModal from './components/PreviewModal'
import EmptyState from './components/EmptyState'
import Login from './components/Login'
import ActivityPanel from './components/ActivityPanel'
import AskModal from './components/AskModal'
import { apiFetch, getUser, clearAuth } from './api'

const DEFAULT_FILTERS = {
  fileTypes: [], language: '', dateFrom: '', dateTo: '', minConfidence: 0,
  documentTypes: [], ageMin: '', ageMax: '', onlyAbnormal: false, folderId: '',
}

function FolderGlyph({ className = 'text-amber-400 group-hover:text-amber-500' }) {
  return (
    <svg className={`h-14 w-14 transition-colors ${className}`} viewBox="0 0 24 24" fill="currentColor">
      <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z" />
    </svg>
  )
}

// Split a list of docs into document-folders (by folder_id) and standalone docs.
function splitByFolder(docs) {
  const map = new Map()
  const standalone = []
  for (const d of docs) {
    if (d.folder_id != null) {
      if (!map.has(d.folder_id)) map.set(d.folder_id, { id: d.folder_id, name: d.folder_name || `Folder ${d.folder_id}`, docs: [] })
      map.get(d.folder_id).docs.push(d)
    } else standalone.push(d)
  }
  return { folders: [...map.values()].sort((a, b) => a.name.localeCompare(b.name)), standalone }
}

// Group documents by uploader; the current user's group sorts first.
function groupByOwner(docs, currentUser) {
  const groups = {}
  for (const d of docs) {
    const owner = d.owner || 'unknown'
    ;(groups[owner] ??= []).push(d)
  }
  return Object.entries(groups).sort(([a], [b]) => {
    if (a === currentUser) return -1
    if (b === currentUser) return 1
    return a.localeCompare(b)
  })
}

const SORT_OPTIONS = [
  { value: 'relevance', label: 'Relevance' },
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'confidence', label: 'OCR Quality' },
  { value: 'age', label: 'Patient Age' },
]

export default function App() {
  const [user, setUser] = useState(getUser())
  const [documents, setDocuments] = useState([])
  const [searchResults, setSearchResults] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [semantic, setSemantic] = useState(true)
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [sortBy, setSortBy] = useState('relevance')
  const [stats, setStats] = useState(null)
  const [folders, setFolders] = useState([])
  const [searchAggs, setSearchAggs] = useState(null)
  const [noMatchHint, setNoMatchHint] = useState(null)
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [askOpen, setAskOpen] = useState(false)
  const [groupByUploader, setGroupByUploader] = useState(true)
  const [openUploader, setOpenUploader] = useState(null)
  const [openFolder, setOpenFolder] = useState(null)
  const [selectedDocument, setSelectedDocument] = useState(null)
  const [previewDocument, setPreviewDocument] = useState(null)
  const [openSearchFolder, setOpenSearchFolder] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isFetching, setIsFetching] = useState(true)
  const [error, setError] = useState(null)
  const searchTimerRef = useRef(null)
  const semanticRef = useRef(semantic)
  useEffect(() => { semanticRef.current = semantic }, [semantic])

  const fetchDocuments = useCallback(async () => {
    setIsFetching(true)
    try {
      const res = await apiFetch('/api/documents')
      if (!res.ok) throw new Error()
      const data = await res.json()
      setDocuments(data.documents ?? [])
    } catch { setError('Could not load documents.') }
    finally { setIsFetching(false) }
  }, [])

  const fetchStats = useCallback(async () => {
    try {
      const res = await apiFetch('/api/stats')
      if (res.ok) setStats(await res.json())
    } catch {}
  }, [])

  const fetchFolders = useCallback(async () => {
    try {
      const res = await apiFetch('/api/folders')
      if (res.ok) setFolders((await res.json()).folders ?? [])
    } catch {}
  }, [])

  const handleLogout = useCallback(() => {
    clearAuth()
    setUser(null)
  }, [])

  useEffect(() => {
    if (!user) return
    fetchDocuments()
    fetchStats()
    fetchFolders()
  }, [user, fetchDocuments, fetchStats, fetchFolders])

  const runSearch = useCallback(async (query) => {
    setIsLoading(true); setError(null)
    try {
      const res = await apiFetch(`/api/search?q=${encodeURIComponent(query)}&semantic=${semanticRef.current}`)
      if (!res.ok) throw new Error()
      const data = await res.json()
      setSearchResults(data.results ?? [])
      setSearchAggs(data.aggregations ?? null)
      setNoMatchHint(data.no_match_hint ?? null)
    } catch { setError('Search failed.'); setSearchResults([]) }
    finally { setIsLoading(false) }
  }, [])

  const handleSearchChange = useCallback((query) => {
    setSearchQuery(query)
    clearTimeout(searchTimerRef.current)
    if (!query.trim()) {
      setSearchResults(null); setNoMatchHint(null); setSearchAggs(null); setError(null); return
    }
    searchTimerRef.current = setTimeout(() => runSearch(query), 400)
  }, [runSearch])

  // Re-run the active search when the semantic toggle flips
  useEffect(() => {
    if (searchQuery.trim()) runSearch(searchQuery)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [semantic])

  // Reset the search-folder drill-in whenever the query changes
  useEffect(() => { setOpenSearchFolder(null) }, [searchQuery])

  const handleDelete = useCallback(async (docId) => {
    try {
      await apiFetch(`/api/documents/${docId}`, { method: 'DELETE' })
      setDocuments((p) => p.filter((d) => d.id !== docId))
      setSearchResults((p) => p ? p.filter((d) => d.id !== docId) : null)
      if (selectedDocument?.id === docId) setSelectedDocument(null)
      fetchStats()
    } catch { setError('Failed to delete document.') }
  }, [selectedDocument, fetchStats])

  const handleTypeClick = useCallback((type) => {
    setFilters((prev) => ({
      ...prev,
      documentTypes: prev.documentTypes.includes(type)
        ? prev.documentTypes.filter((t) => t !== type)
        : [...prev.documentTypes, type],
    }))
  }, [])

  const handleIcd10Click = useCallback((code) => {
    handleSearchChange(code)
  }, [handleSearchChange])

  const handleSimilarDocs = useCallback((doc) => {
    const terms = [...(doc.diagnoses?.slice(0, 1) ?? []), ...(doc.icd10_codes?.slice(0, 1) ?? [])]
    if (terms.length > 0) handleSearchChange(terms[0])
  }, [handleSearchChange])

  const handleActivityView = useCallback((docId) => {
    const doc = documents.find((d) => d.id === docId) || searchResults?.find((d) => d.id === docId)
    if (doc) setSelectedDocument(doc)
    else fetchDocuments()
  }, [documents, searchResults, fetchDocuments])

  const renderCards = (docs) => docs.map((doc) => (
    <ResultCard
      key={doc.id}
      document={doc}
      searchQuery={searchQuery}
      currentUser={user.username}
      onViewDetails={setSelectedDocument}
      onPreview={setPreviewDocument}
      onDelete={handleDelete}
      onIcd10Click={handleIcd10Click}
      onSimilarDocs={handleSimilarDocs}
    />
  ))

  const activeItems = searchResults !== null ? searchResults : documents

  const filteredItems = useMemo(() => activeItems.filter((doc) => {
    if (filters.fileTypes.length > 0 && !filters.fileTypes.includes(doc.file_type)) return false
    if (filters.language && doc.language !== filters.language) return false
    if (filters.dateFrom && new Date(doc.uploaded_at) < new Date(filters.dateFrom)) return false
    if (filters.dateTo && new Date(doc.uploaded_at) > new Date(filters.dateTo + 'T23:59:59')) return false
    if (filters.minConfidence > 0 && (doc.confidence_score ?? 0) < filters.minConfidence) return false
    if (filters.documentTypes.length > 0 && !filters.documentTypes.includes(doc.document_type ?? 'general')) return false
    if (filters.ageMin !== '' && (doc.patient_age == null || doc.patient_age < Number(filters.ageMin))) return false
    if (filters.ageMax !== '' && (doc.patient_age == null || doc.patient_age > Number(filters.ageMax))) return false
    if (filters.onlyAbnormal && !doc.has_abnormal_results) return false
    if (filters.folderId === 'standalone' && doc.folder_id != null) return false
    if (filters.folderId !== '' && filters.folderId !== 'standalone' && String(doc.folder_id) !== String(filters.folderId)) return false
    return true
  }), [activeItems, filters])

  const sortedItems = useMemo(() => {
    return [...filteredItems].sort((a, b) => {
      switch (sortBy) {
        case 'newest': return new Date(b.uploaded_at) - new Date(a.uploaded_at)
        case 'oldest': return new Date(a.uploaded_at) - new Date(b.uploaded_at)
        case 'confidence': return (b.confidence_score ?? 0) - (a.confidence_score ?? 0)
        case 'age': return (a.patient_age ?? 999) - (b.patient_age ?? 999)
        default: return (b.score ?? 0) - (a.score ?? 0)
      }
    })
  }, [filteredItems, sortBy])

  const availableLanguages = [...new Set(documents.map((d) => d.language).filter(Boolean))]

  if (!user) {
    return <Login onLogin={setUser} />
  }

  // Nested browse data: uploader -> document-folders + standalone -> folder docs
  const ownerGroups = groupByOwner(sortedItems, user.username)
  const uploaderDocs = openUploader ? (ownerGroups.find(([o]) => o === openUploader)?.[1] ?? []) : []
  const { folders: folderGroups, standalone: standaloneDocs } = splitByFolder(uploaderDocs)
  const openFolderObj = openFolder != null ? folderGroups.find((f) => String(f.id) === String(openFolder)) : null
  const uploaderLabel = openUploader === user.username ? 'you' : openUploader

  // Search view: group the matches into folders; remember the rest of each folder's docs
  const { folders: searchFolderGroups, standalone: searchStandalone } =
    searchQuery ? splitByFolder(sortedItems) : { folders: [], standalone: [] }
  const openSearchFolderObj = openSearchFolder != null
    ? searchFolderGroups.find((f) => String(f.id) === String(openSearchFolder)) : null
  const searchFolderMatches = openSearchFolderObj?.docs ?? []
  const searchMatchIds = new Set(searchFolderMatches.map((d) => d.id))
  const searchFolderNonMatches = openSearchFolderObj
    ? documents.filter((d) => String(d.folder_id) === String(openSearchFolder) && !searchMatchIds.has(d.id))
    : []

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header
        onUploadClick={() => setIsUploadModalOpen(true)}
        user={user}
        onLogout={handleLogout}
        onActivityClick={() => setActivityOpen((o) => !o)}
        activityOpen={activityOpen}
        onAskClick={() => setAskOpen(true)}
      />
      <StatsBar stats={stats} activeTypes={filters.documentTypes} onTypeClick={handleTypeClick} />

      <main className="flex-1 flex flex-col w-full max-w-screen-xl mx-auto">
        <div className="px-6 py-5">
          <SearchBar value={searchQuery} onChange={handleSearchChange} isLoading={isLoading} semantic={semantic} onSemanticChange={setSemantic} />
        </div>

        {error && (
          <div className="mx-6 mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">{error}</div>
        )}

        <div className="flex flex-1 gap-6 px-6 pb-10">
          <FilterSidebar
            filters={filters}
            onChange={setFilters}
            availableLanguages={availableLanguages}
            aggregations={searchAggs}
            folders={folders}
          />

          <section className="flex-1 min-w-0">
            {/* Results header + sort */}
            {(searchQuery || sortedItems.length > 0) && (
              <div className="mb-4 flex items-center justify-between">
                <p className="text-sm text-gray-500">
                  {isLoading ? 'Searching…' : (
                    <>
                      <span className="font-medium text-gray-700">{sortedItems.length}</span> result{sortedItems.length !== 1 ? 's' : ''}
                      {searchQuery && <> for <span className="font-medium text-gray-700">"{searchQuery}"</span></>}
                    </>
                  )}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => { setGroupByUploader((g) => !g); setOpenUploader(null); setOpenFolder(null) }}
                    title="Show documents as folders grouped by uploader"
                    className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${groupByUploader ? 'border-blue-300 bg-blue-50 text-blue-700' : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'}`}
                  >
                    📁 Folder view
                  </button>
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value)}
                    className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-200"
                  >
                    {SORT_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            {noMatchHint && (
              <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                {noMatchHint}
              </div>
            )}

            {isFetching && !searchQuery ? (
              <div className="flex items-center justify-center py-24 text-gray-400 text-sm">Loading documents…</div>
            ) : searchQuery ? (
              /* SEARCH VIEW — matches that live in a folder are shown AS the folder */
              openSearchFolderObj ? (
                <div>
                  <button onClick={() => setOpenSearchFolder(null)} className="mb-4 inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-800">
                    ← Search results
                  </button>
                  <h3 className="mb-3 flex items-center gap-2 text-base font-semibold text-gray-800">
                    📁 {openSearchFolderObj.name}
                    <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">{searchFolderMatches.length} match{searchFolderMatches.length !== 1 ? 'es' : ''}</span>
                  </h3>
                  <div className="space-y-4">{renderCards(searchFolderMatches)}</div>
                  {searchFolderNonMatches.length > 0 && (
                    <div className="mt-6">
                      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">Other documents in this folder · no match</h4>
                      <div className="space-y-4 opacity-50">{renderCards(searchFolderNonMatches)}</div>
                    </div>
                  )}
                </div>
              ) : sortedItems.length > 0 ? (
                <div>
                  {searchFolderGroups.length > 0 && (
                    <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                      {searchFolderGroups.map((f) => (
                        <button
                          key={f.id}
                          onClick={() => setOpenSearchFolder(f.id)}
                          className="group flex flex-col items-center rounded-xl border border-gray-200 bg-white p-5 text-center transition-all hover:border-indigo-300 hover:shadow-sm"
                        >
                          <FolderGlyph className="text-indigo-400 group-hover:text-indigo-500" />
                          <span className="mt-2 w-full truncate text-sm font-medium text-gray-800">{f.name}</span>
                          <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">{f.docs.length} match{f.docs.length !== 1 ? 'es' : ''}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {searchStandalone.length > 0 && (
                    <div>
                      {searchFolderGroups.length > 0 && (
                        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">Other matches</h4>
                      )}
                      <div className="space-y-4">{renderCards(searchStandalone)}</div>
                    </div>
                  )}
                </div>
              ) : (
                <EmptyState hasQuery onUploadClick={() => setIsUploadModalOpen(true)} />
              )
            ) : !groupByUploader ? (
              /* Flat browse (folder view off) */
              sortedItems.length > 0 ? (
                <div className="space-y-4">{renderCards(sortedItems)}</div>
              ) : (
                <EmptyState hasQuery={false} onUploadClick={() => setIsUploadModalOpen(true)} />
              )
            ) : openUploader && openFolderObj ? (
              /* Level 3 — inside a document folder */
              <div>
                <button onClick={() => setOpenFolder(null)} className="mb-4 inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-800">
                  ← Uploaded by {uploaderLabel}
                </button>
                <h3 className="mb-3 flex items-center gap-2 text-base font-semibold text-gray-800">
                  📁 {openFolderObj.name} <span className="text-xs font-normal text-gray-400">({openFolderObj.docs.length})</span>
                </h3>
                <div className="space-y-4">{renderCards(openFolderObj.docs)}</div>
              </div>
            ) : openUploader ? (
              /* Level 2 — an uploader: document folders first, then standalone docs */
              <div>
                <button onClick={() => { setOpenUploader(null); setOpenFolder(null) }} className="mb-4 inline-flex items-center gap-1 text-sm font-medium text-blue-600 hover:text-blue-800">
                  ← All folders
                </button>
                <h3 className="mb-3 flex items-center gap-2 text-base font-semibold text-gray-800">
                  👤 Uploaded by {uploaderLabel}
                </h3>

                {folderGroups.length > 0 && (
                  <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                    {folderGroups.map((f) => (
                      <button
                        key={f.id}
                        onClick={() => setOpenFolder(f.id)}
                        className="group flex flex-col items-center rounded-xl border border-gray-200 bg-white p-5 text-center transition-all hover:border-indigo-300 hover:shadow-sm"
                      >
                        <FolderGlyph className="text-indigo-400 group-hover:text-indigo-500" />
                        <span className="mt-2 w-full truncate text-sm font-medium text-gray-800">{f.name}</span>
                        <span className="text-xs text-gray-400">{f.docs.length} document{f.docs.length !== 1 ? 's' : ''}</span>
                      </button>
                    ))}
                  </div>
                )}

                {standaloneDocs.length > 0 && (
                  <div>
                    {folderGroups.length > 0 && (
                      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">Standalone documents</h4>
                    )}
                    <div className="space-y-4">{renderCards(standaloneDocs)}</div>
                  </div>
                )}

                {folderGroups.length === 0 && standaloneDocs.length === 0 && (
                  <p className="py-8 text-center text-sm text-gray-400">No documents.</p>
                )}
              </div>
            ) : ownerGroups.length > 0 ? (
              /* Level 1 — folder grid, one folder per uploader */
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                {ownerGroups.map(([owner, docs]) => (
                  <button
                    key={owner}
                    onClick={() => { setOpenUploader(owner); setOpenFolder(null) }}
                    className="group flex flex-col items-center rounded-xl border border-gray-200 bg-white p-5 text-center transition-all hover:border-blue-300 hover:shadow-sm"
                  >
                    <FolderGlyph />
                    <span className="mt-2 w-full truncate text-sm font-medium text-gray-800">
                      Uploaded by {owner === user.username ? 'you' : owner}
                    </span>
                    <span className="text-xs text-gray-400">{docs.length} document{docs.length !== 1 ? 's' : ''}</span>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState hasQuery={!!searchQuery} onUploadClick={() => setIsUploadModalOpen(true)} />
            )}
          </section>
        </div>
      </main>

      <UploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onUploadSuccess={() => { fetchDocuments(); fetchStats(); fetchFolders() }}
      />

      {selectedDocument && (
        <DocumentDetailModal document={selectedDocument} onClose={() => setSelectedDocument(null)} />
      )}

      {previewDocument && (
        <PreviewModal document={previewDocument} onClose={() => setPreviewDocument(null)} />
      )}

      {askOpen && (
        <AskModal onClose={() => setAskOpen(false)} onViewSource={(id) => { const d = documents.find((x) => x.id === id); if (d) setPreviewDocument(d) }} />
      )}

      <ActivityPanel
        open={activityOpen}
        onClose={() => setActivityOpen(false)}
        onView={handleActivityView}
        onActivity={() => { fetchDocuments(); fetchStats(); fetchFolders() }}
        currentUser={user.username}
      />
    </div>
  )
}

const TYPE_LABELS = {
  lab_report: 'Lab Report',
  patient_report: 'Patient Report',
  prescription: 'Prescription',
  discharge_summary: 'Discharge',
  general: 'General',
}

const TYPE_COLORS = {
  lab_report: 'bg-emerald-100 text-emerald-700 hover:bg-emerald-200',
  patient_report: 'bg-blue-100 text-blue-700 hover:bg-blue-200',
  prescription: 'bg-purple-100 text-purple-700 hover:bg-purple-200',
  discharge_summary: 'bg-amber-100 text-amber-700 hover:bg-amber-200',
  general: 'bg-gray-100 text-gray-600 hover:bg-gray-200',
}

export default function StatsBar({ stats, activeTypes, onTypeClick }) {
  if (!stats) return null

  const entries = Object.entries(stats.by_document_type ?? {})

  return (
    <div className="border-b border-gray-100 bg-white px-6 py-2 flex items-center gap-3 text-sm">
      <span className="text-gray-500 shrink-0">
        <span className="font-semibold text-gray-800">{stats.total}</span>{' '}
        document{stats.total !== 1 ? 's' : ''} indexed
      </span>

      {entries.length > 0 && (
        <>
          <div className="h-4 w-px bg-gray-200 shrink-0" />
          <div className="flex flex-wrap gap-1.5">
            {entries.map(([type, count]) => (
              <button
                key={type}
                onClick={() => onTypeClick(type)}
                className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors ${
                  TYPE_COLORS[type] ?? TYPE_COLORS.general
                } ${activeTypes.includes(type) ? 'ring-2 ring-offset-1 ring-current' : ''}`}
              >
                {TYPE_LABELS[type] ?? type} ({count})
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

import { useState, useEffect } from 'react'
import {
  Activity,
  RotateCcw,
  Search,
  Filter,
  ChevronLeft,
  ChevronRight,
  Calendar,
  X,
} from 'lucide-react'
import { getAgentActivity } from '../api/client'
import ActivityCard from '../components/activity/ActivityCard'

export default function AgentActivity() {
  const [activities, setActivities] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)

  // Pagination State
  const [page, setPage] = useState(1)
  const [pageSize] = useState(10)
  const [totalCount, setTotalCount] = useState(0)
  const [totalPages, setTotalPages] = useState(1)

  // Filters State
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [actionTypeFilter, setActionTypeFilter] = useState('ALL')
  const [dateFilter, setDateFilter] = useState('ALL') // 'ALL', 'TODAY', 'WEEK', 'MONTH'

  const computeDateRange = (rangeType) => {
    if (rangeType === 'TODAY') {
      const today = new Date().toISOString().split('T')[0]
      return { startDate: today, endDate: today }
    }
    if (rangeType === 'WEEK') {
      const d = new Date()
      d.setDate(d.getDate() - 7)
      return { startDate: d.toISOString().split('T')[0] }
    }
    if (rangeType === 'MONTH') {
      const d = new Date()
      d.setDate(d.getDate() - 30)
      return { startDate: d.toISOString().split('T')[0] }
    }
    return {}
  }

  const loadData = async (targetPage = page) => {
    setLoading(true)
    try {
      const { startDate, endDate } = computeDateRange(dateFilter)
      const data = await getAgentActivity(targetPage, pageSize, {
        search: searchQuery.trim(),
        status: statusFilter,
        actionType: actionTypeFilter,
        startDate,
        endDate,
      })
      setActivities(data.items || [])
      setTotalCount(data.total || 0)
      setTotalPages(data.total_pages || 1)
      setPage(data.page || 1)
    } catch (err) {
      console.error('Failed to load activity logs:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData(1)
  }, [statusFilter, actionTypeFilter, dateFilter])

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    loadData(1)
  }

  const handleResetFilters = () => {
    setSearchQuery('')
    setStatusFilter('ALL')
    setActionTypeFilter('ALL')
    setDateFilter('ALL')
  }

  const toggleExpand = (id) => {
    setExpandedId(expandedId === id ? null : id)
  }

  const isFiltered = searchQuery.trim() || statusFilter !== 'ALL' || actionTypeFilter !== 'ALL' || dateFilter !== 'ALL'

  return (
    <div className="space-y-6 max-w-full overflow-hidden">
      {/* Top Header Actions */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-1">
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          <span className="font-semibold text-primary">{totalCount} Recorded Operations</span>
          <span>•</span>
          <span>Real-time Financial Ledger Auditing</span>
        </div>
        <button
          className="btn-secondary flex items-center gap-1.5 text-xs font-semibold py-2 px-3.5 self-start sm:self-auto"
          onClick={() => loadData(page)}
        >
          <RotateCcw size={14} /> Refresh Log
        </button>
      </div>

      {/* Filter and Search Toolbar */}
      <div className="card p-4 space-y-3.5">
        <form onSubmit={handleSearchSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1 max-w-md">
            <Search size={16} className="search-icon" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by action, tool, invoice, or keyword..."
              className="search-input w-full"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <div className="flex items-center gap-1.5">
              <label className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>Action:</label>
              <select
                value={actionTypeFilter}
                onChange={(e) => setActionTypeFilter(e.target.value)}
                className="input text-xs py-1.5 px-2.5 h-9"
              >
                <option value="ALL">All Actions</option>
                <option value="REMINDER">Reminders Dispatched</option>
                <option value="ESCALAT">Escalations Flagged</option>
                <option value="PAYMENT">Payments Settled</option>
                <option value="DISPUTE">Disputes Logged</option>
                <option value="CALCULATE">Penalty Calculations</option>
                <option value="QUERY">Database Inspections</option>
              </select>
            </div>

            <button type="submit" className="btn-primary text-xs px-3.5 py-2">
              Apply Search
            </button>

            {isFiltered && (
              <button
                type="button"
                onClick={handleResetFilters}
                className="btn-secondary text-xs px-2.5 py-2 flex items-center gap-1 text-danger"
                title="Reset all filters"
              >
                <X size={13} /> Clear
              </button>
            )}
          </div>
        </form>

        {/* Secondary Filter Pills: Status & Date Ranges */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2.5 border-t text-xs" style={{ borderColor: 'var(--border)' }}>
          {/* Status Filter */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold mr-1" style={{ color: 'var(--text-muted)' }}>Status:</span>
            {[
              { id: 'ALL', label: 'All' },
              { id: 'SUCCESS', label: 'Success' },
              { id: 'PENDING_APPROVAL', label: 'Pending Approval' },
              { id: 'BLOCKED_BY_GUARDRAIL', label: 'Blocked by Policy' },
              { id: 'ERROR', label: 'Errors' },
            ].map((st) => (
              <button
                type="button"
                key={st.id}
                onClick={() => setStatusFilter(st.id)}
                className={`filter-pill ${statusFilter === st.id ? 'active' : ''}`}
              >
                {st.label}
              </button>
            ))}
          </div>

          {/* Date Filter */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-semibold mr-1 flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
              <Calendar size={12} /> Time:
            </span>
            {[
              { id: 'ALL', label: 'All Time' },
              { id: 'TODAY', label: 'Today' },
              { id: 'WEEK', label: 'Last 7 Days' },
              { id: 'MONTH', label: 'Last 30 Days' },
            ].map((d) => (
              <button
                type="button"
                key={d.id}
                onClick={() => setDateFilter(d.id)}
                className={`filter-pill ${dateFilter === d.id ? 'active' : ''}`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Main Activity Log Feed */}
      {loading ? (
        <div className="flex flex-col items-center justify-center min-h-[350px] space-y-3 card p-12">
          <div className="h-9 w-9 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
            Loading audit records and execution verifications...
          </p>
        </div>
      ) : activities.length === 0 ? (
        <div className="card p-12 text-center space-y-3">
          <Activity size={32} className="mx-auto text-muted opacity-40" />
          <p className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
            {isFiltered ? 'No audit actions match your active filters.' : 'No autonomous actions recorded yet.'}
          </p>
          <p className="text-xs max-w-sm mx-auto" style={{ color: 'var(--text-muted)' }}>
            {isFiltered
              ? 'Try widening your date range or clearing keyword search.'
              : 'Trigger a collection cycle from Dashboard or interact in Agent Chat to log decisions.'}
          </p>
          {isFiltered && (
            <button onClick={handleResetFilters} className="btn-secondary text-xs px-3 py-1.5 mx-auto">
              Reset Filters
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {activities.map((act) => (
            <ActivityCard
              key={act.action_id}
              act={act}
              isExpanded={expandedId === act.action_id}
              onToggle={() => toggleExpand(act.action_id)}
            />
          ))}

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div
              className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-4 border-t text-xs card p-4"
              style={{ borderColor: 'var(--border)' }}
            >
              <p style={{ color: 'var(--text-muted)' }}>
                Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, totalCount)} of {totalCount} records
              </p>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => {
                    const prev = Math.max(1, page - 1)
                    setPage(prev)
                    loadData(prev)
                  }}
                  disabled={page === 1}
                  className="btn-secondary px-3 py-1.5 flex items-center gap-1 disabled:opacity-40"
                >
                  <ChevronLeft size={13} />
                  <span>Previous</span>
                </button>

                <span className="px-3 py-1 font-semibold" style={{ color: 'var(--text)' }}>
                  Page {page} of {totalPages}
                </span>

                <button
                  onClick={() => {
                    const next = Math.min(totalPages, page + 1)
                    setPage(next)
                    loadData(next)
                  }}
                  disabled={page === totalPages}
                  className="btn-secondary px-3 py-1.5 flex items-center gap-1 disabled:opacity-40"
                >
                  <span>Next</span>
                  <ChevronRight size={13} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

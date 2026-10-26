import { useState, useEffect } from 'react'
import {
  CheckCircle2,
  ShieldAlert,
  XCircle,
  Clock,
  AlertTriangle,
  UserCheck,
  Edit3,
  RotateCcw,
  Search,
  Filter,
} from 'lucide-react'
import { getPendingApprovals, reviewApproval } from '../api/client'
import { formatISTDateTime } from '../utils/date'
import { formatINR } from '../utils/currency'

export default function Approvals() {
  const [approvals, setApprovals] = useState([])
  const [loading, setLoading] = useState(true)
  const [feedback, setFeedback] = useState(null)
  const [actionLoading, setActionLoading] = useState(null)
  const [edits, setEdits] = useState({}) // { [id]: { isEditing, subject, body, notes } }

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState('')
  const [actionFilter, setActionFilter] = useState('ALL')
  const [sortBy, setSortBy] = useState('NEWEST')

  const loadData = async () => {
    setLoading(true)
    try {
      const data = await getPendingApprovals()
      setApprovals(data)

      // Initialize edit draft cache for each approval item
      const initialEdits = {}
      data.forEach((appr) => {
        initialEdits[appr.approval_id] = {
          isEditing: false,
          subject: appr.details?.subject || 'Payment Notice',
          body: appr.details?.body || '',
          notes: '',
          partialAmount: appr.details?.claimed_amount || appr.details?.amount || '',
        }
      })
      setEdits(initialEdits)
    } catch (err) {
      console.error('Failed to load approvals:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Auto-dismiss feedback after 5 seconds
  useEffect(() => {
    if (feedback) {
      const timer = setTimeout(() => setFeedback(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [feedback])

  const toggleEditing = (id) => {
    setEdits((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        isEditing: !prev[id]?.isEditing,
      },
    }))
  }

  const handleFieldChange = (id, field, value) => {
    setEdits((prev) => ({
      ...prev,
      [id]: {
        ...prev[id],
        [field]: value,
      },
    }))
  }

  const handleDecision = async (approvalId, status, overrideAmount = null) => {
    setActionLoading(approvalId)
    const itemEdit = edits[approvalId] || {}
    const amountVal = overrideAmount !== null ? overrideAmount : (itemEdit.partialAmount || null)
    try {
      const res = await reviewApproval(
        approvalId,
        status,
        itemEdit.notes || `Decision ${status} recorded by Supervisor`,
        'Ashish Gokani (Admin)',
        itemEdit.isEditing ? itemEdit.subject : null,
        itemEdit.isEditing ? itemEdit.body : null,
        amountVal
      )
      setFeedback({ type: 'success', message: res.message })
      await loadData()
    } catch (err) {
      setFeedback({ type: 'error', message: err.message || 'Action failed.' })
    } finally {
      setActionLoading(null)
    }
  }

  const filteredApprovals = approvals
    .filter((appr) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matchInvoice = appr.invoice_id?.toLowerCase().includes(q)
        const matchCompany = appr.company_name?.toLowerCase().includes(q)
        const matchReason = appr.details?.reason?.toLowerCase().includes(q)
        const matchSubject = appr.details?.subject?.toLowerCase().includes(q)
        const matchUtr = appr.details?.utr_reference?.toLowerCase().includes(q)
        if (!matchInvoice && !matchCompany && !matchReason && !matchSubject && !matchUtr) {
          return false
        }
      }

      if (actionFilter === 'PAYMENT') {
        return appr.action_type.includes('PAYMENT') || appr.action_type.includes('REMITTANCE')
      }
      if (actionFilter === 'REMINDER') {
        return appr.action_type.includes('REMINDER')
      }
      if (actionFilter === 'ESCALATE') {
        return appr.action_type.includes('ESCALAT')
      }
      if (actionFilter === 'DISPUTE') {
        return appr.action_type.includes('DISPUTE')
      }
      return true
    })
    .sort((a, b) => {
      if (sortBy === 'AMOUNT_DESC') {
        return (Number(b.details?.amount) || 0) - (Number(a.details?.amount) || 0)
      }
      if (sortBy === 'OLDEST') {
        return new Date(a.created_at) - new Date(b.created_at)
      }
      return new Date(b.created_at) - new Date(a.created_at)
    })

  if (loading && approvals.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[420px] space-y-3">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
          Loading pending authorization items...
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Top Header Actions */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-1">
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          <span className="font-semibold text-primary">{approvals.length} Actions Awaiting Review</span>
          <span>•</span>
          <span>Dual Supervisory Control Active</span>
        </div>
        <button className="btn-secondary flex items-center gap-1.5 text-xs font-semibold py-2 px-3.5 self-start sm:self-auto" onClick={loadData}>
          <RotateCcw size={14} /> Refresh
        </button>
      </div>

      {/* Search & Filter Toolbar */}
      <div className="card p-4 space-y-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1 max-w-md">
            <Search size={16} className="search-icon" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by invoice ID, customer company, or justification..."
              className="search-input w-full"
            />
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto">
            <label className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
              Sort:
            </label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              className="input text-xs py-1.5 px-2.5 h-9"
            >
              <option value="NEWEST">Newest First</option>
              <option value="OLDEST">Oldest First</option>
              <option value="AMOUNT_DESC">Highest Amount</option>
            </select>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-1.5 text-xs mr-2" style={{ color: 'var(--text-muted)' }}>
            <Filter size={13} />
            <span className="font-semibold">Filter:</span>
          </div>
          {[
            { id: 'ALL', label: `All (${approvals.length})` },
            { id: 'PAYMENT', label: '💳 Payment Verifications' },
            { id: 'REMINDER', label: '✉️ Reminders' },
            { id: 'ESCALATE', label: '⚠️ Escalations' },
            { id: 'DISPUTE', label: '⚖️ Disputes' },
          ].map((cat) => (
            <button
              type="button"
              key={cat.id}
              onClick={() => setActionFilter(cat.id)}
              className={`filter-pill ${actionFilter === cat.id ? 'active' : ''}`}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {feedback && (
        <div
          className={`border p-4 rounded-card text-xs flex items-center justify-between ${
            feedback.type === 'success'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600'
              : 'bg-red-500/10 border-red-500/30 text-danger'
          }`}
        >
          <div className="flex items-center gap-2">
            {feedback.type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            <span>{feedback.message}</span>
          </div>
          <button className="text-xs font-semibold" onClick={() => setFeedback(null)}>
            Dismiss
          </button>
        </div>
      )}

      {approvals.length === 0 ? (
        <div className="card p-12 text-center space-y-3">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600">
            <UserCheck size={24} />
          </div>
          <h3 className="text-base font-bold" style={{ color: 'var(--text)' }}>
            All High-Value Authorizations Resolved
          </h3>
          <p className="text-xs max-w-sm mx-auto" style={{ color: 'var(--text-muted)' }}>
            There are currently no proposals held for managerial review. All accounts are processing according to policy.
          </p>
        </div>
      ) : filteredApprovals.length === 0 ? (
        <div className="card p-12 text-center space-y-3">
          <p className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
            No authorization requests match your current filters.
          </p>
          <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
            Try clearing your search query or switching to 'All' category.
          </p>
          <button
            onClick={() => {
              setSearchQuery('')
              setActionFilter('ALL')
            }}
            className="btn-secondary text-xs px-3 py-1.5 mx-auto"
          >
            Reset Filters
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {filteredApprovals.map((appr) => {
            const currentEdit = edits[appr.approval_id] || {}
            const isEditing = currentEdit.isEditing
            const isPaymentClaim =
              appr.action_type === 'VERIFY_PAYMENT_REMITTANCE' ||
              appr.action_type === 'PAYMENT_CLAIMED'

            return (
              <div key={appr.approval_id} className="card p-5 space-y-4">
                <div
                  className="flex flex-wrap items-center justify-between gap-2 border-b pb-3"
                  style={{ borderColor: 'var(--border)' }}
                >
                  <div className="flex items-center gap-2">
                    <span className={`badge flex items-center gap-1 ${isPaymentClaim ? 'badge-paid' : 'badge-overdue'}`}>
                      <ShieldAlert size={12} />
                      {appr.action_type.replace(/_/g, ' ')}
                    </span>
                    <span className="text-xs font-bold" style={{ color: 'var(--text)' }}>
                      Invoice {appr.invoice_id} · {appr.company_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-muted)' }}>
                      <Clock size={13} />
                      <span>Requested: {formatISTDateTime(appr.created_at)}</span>
                    </div>
                    {appr.details?.body && !isPaymentClaim && (
                      <button
                        type="button"
                        className={`text-xs px-2.5 py-1 rounded border flex items-center gap-1 transition-all ${
                          isEditing
                            ? 'bg-primary text-white border-primary'
                            : 'btn-secondary text-primary'
                        }`}
                        onClick={() => toggleEditing(appr.approval_id)}
                      >
                        <Edit3 size={12} />
                        <span>{isEditing ? 'Close Customizer' : 'Customize Email'}</span>
                      </button>
                    )}
                  </div>
                </div>

                {/* Specialized Payment Remittance View */}
                {isPaymentClaim ? (
                  <div
                    className="rounded p-4 text-xs space-y-3 border"
                    style={{ background: 'rgba(16, 185, 129, 0.04)', borderColor: 'rgba(16, 185, 129, 0.25)' }}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-emerald-600 text-xs">
                          💳 Debtor Remittance Claim Details
                        </span>
                        {appr.details?.email_received_at && (
                          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                            • Received: {formatISTDateTime(appr.details.email_received_at)}
                          </span>
                        )}
                      </div>
                      <span className="badge bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 text-xs font-mono font-bold">
                        UTR: {appr.details?.utr_reference || 'Unspecified'}
                      </span>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-3 pt-1">
                      <div>
                        <span className="font-semibold block text-[11px]" style={{ color: 'var(--text-muted)' }}>
                          Claimed Payment Amount:
                        </span>
                        <span className="text-base font-extrabold text-emerald-600">
                          {formatINR(appr.details?.claimed_amount || appr.details?.amount || 0)}
                        </span>
                      </div>
                      <div>
                        <span className="font-semibold block text-[11px]" style={{ color: 'var(--text-muted)' }}>
                          Sender Address:
                        </span>
                        <span className="font-mono text-xs font-semibold" style={{ color: 'var(--text)' }}>
                          {appr.details?.sender_email || 'Registered Customer'}
                        </span>
                      </div>
                      <div>
                        <span className="font-semibold block text-[11px]" style={{ color: 'var(--text-muted)' }}>
                          Ledger Protection:
                        </span>
                        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                          Original invoice amount permanently preserved.
                        </span>
                      </div>
                    </div>

                    {appr.details?.ai_rationale && (
                      <div className="pt-2 border-t" style={{ borderColor: 'rgba(16, 185, 129, 0.15)' }}>
                        <span className="font-semibold block text-[11px] text-primary">
                          AI Semantic Assessment:
                        </span>
                        <p className="text-secondary leading-relaxed pt-0.5">
                          {appr.details.ai_rationale}
                        </p>
                      </div>
                    )}

                    {appr.details?.customer_reply_snippet && (
                      <div className="rounded p-2.5 bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/5">
                        <span className="text-[10px] uppercase font-bold tracking-wider" style={{ color: 'var(--text-muted)' }}>
                          Inbound Customer Message:
                        </span>
                        <p className="italic text-secondary pt-1 font-mono text-[11px]">
                          "{appr.details.customer_reply_snippet}"
                        </p>
                      </div>
                    )}

                    <div className="pt-2 flex flex-wrap items-center gap-3">
                      <label className="text-xs font-semibold" style={{ color: 'var(--text)' }}>
                        Verified Credit Amount (₹):
                      </label>
                      <input
                        type="number"
                        step="any"
                        value={currentEdit.partialAmount}
                        onChange={(e) => handleFieldChange(appr.approval_id, 'partialAmount', e.target.value)}
                        placeholder="Amount cleared in bank"
                        className="search-input text-xs font-bold max-w-[180px]"
                      />
                      <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                        For partial payment, specify actual bank credit. Balance will update deterministically.
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="grid gap-4 sm:grid-cols-2 text-xs">
                    <div className="space-y-1">
                      <p className="font-semibold" style={{ color: 'var(--text-secondary)' }}>
                        Condition & Trigger Justification
                      </p>
                      <p style={{ color: 'var(--text)' }}>
                        {appr.details?.reason || appr.details?.subject || 'Policy threshold requires supervisory authorization.'}
                      </p>
                    </div>
                    <div className="space-y-1">
                      <p className="font-semibold" style={{ color: 'var(--text-secondary)' }}>
                        Outstanding Principal & Penalties
                      </p>
                      <p className="text-sm font-bold text-danger">
                        {formatINR(appr.details?.amount || 0)}
                      </p>
                      {appr.details?.days_overdue && (
                        <p style={{ color: 'var(--text-muted)' }}>
                          Overdue Aging: {appr.details.days_overdue} days
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* Email Draft View / Customizer for non-payment approvals */}
                {!isPaymentClaim && appr.details?.body && (
                  <div
                    className="rounded p-4 text-xs space-y-3 border"
                    style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}
                  >
                    <div className="flex items-center justify-between">
                      <p className="font-semibold text-primary">
                        {isEditing ? '✏️ Customize Email Draft Before Dispatch:' : 'Drafted Notification Message:'}
                      </p>
                      {isEditing && (
                        <span className="text-[11px] text-amber-500 font-semibold">
                          Customized version will be sent upon approval
                        </span>
                      )}
                    </div>

                    {isEditing ? (
                      <div className="space-y-2">
                        <div>
                          <label className="block text-[11px] font-semibold mb-1" style={{ color: 'var(--text-muted)' }}>
                            Subject Line:
                          </label>
                          <input
                            value={currentEdit.subject}
                            onChange={(e) => handleFieldChange(appr.approval_id, 'subject', e.target.value)}
                            className="search-input w-full font-semibold"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-semibold mb-1" style={{ color: 'var(--text-muted)' }}>
                            Email Body:
                          </label>
                          <textarea
                            rows={6}
                            value={currentEdit.body}
                            onChange={(e) => handleFieldChange(appr.approval_id, 'body', e.target.value)}
                            className="search-input w-full resize-none font-mono text-xs leading-relaxed"
                          />
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-1">
                        <p className="font-semibold" style={{ color: 'var(--text)' }}>
                          Subject: {currentEdit.subject || appr.details.subject}
                        </p>
                        <p className="whitespace-pre-line text-secondary leading-relaxed pt-1">
                          {currentEdit.body || appr.details.body}
                        </p>
                      </div>
                    )}
                  </div>
                )}

                {/* Supervisor Notes Input */}
                <div className="text-xs">
                  <label className="block mb-1 font-semibold" style={{ color: 'var(--text-muted)' }}>
                    Supervisor Review Notes (Optional):
                  </label>
                  <input
                    value={currentEdit.notes || ''}
                    onChange={(e) => handleFieldChange(appr.approval_id, 'notes', e.target.value)}
                    placeholder="e.g. Bank credit verified against Axis statement line #428."
                    className="search-input w-full text-xs"
                  />
                </div>

                {/* Decision Actions */}
                <div className="flex flex-wrap justify-end gap-2 pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                  {isPaymentClaim ? (
                    <>
                      <button
                        type="button"
                        className="btn-secondary text-xs flex items-center gap-1.5 px-3 py-2 text-danger hover:border-red-500/50"
                        onClick={() => handleDecision(appr.approval_id, 'REJECTED')}
                        disabled={actionLoading === appr.approval_id}
                      >
                        <XCircle size={14} />
                        <span>Reject Payment Claim</span>
                      </button>
                      <button
                        type="button"
                        className="btn-secondary text-xs flex items-center gap-1.5 px-3 py-2 text-amber-500 hover:border-amber-500/50"
                        onClick={() => handleDecision(appr.approval_id, 'PARTIAL_PAYMENT_APPROVED', currentEdit.partialAmount)}
                        disabled={actionLoading === appr.approval_id}
                      >
                        <CheckCircle2 size={14} />
                        <span>Approve Partial ({formatINR(currentEdit.partialAmount || 0)})</span>
                      </button>
                      <button
                        type="button"
                        className="btn-primary text-xs flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-500"
                        onClick={() => handleDecision(appr.approval_id, 'FULL_PAYMENT_APPROVED')}
                        disabled={actionLoading === appr.approval_id}
                      >
                        <CheckCircle2 size={14} />
                        <span>{actionLoading === appr.approval_id ? 'Recording...' : 'Approve Full Payment'}</span>
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="btn-secondary text-xs flex items-center gap-1.5 px-4 py-2"
                        onClick={() => handleDecision(appr.approval_id, 'REJECTED')}
                        disabled={actionLoading === appr.approval_id}
                      >
                        <XCircle size={14} className="text-danger" />
                        <span>Reject Proposal</span>
                      </button>
                      <button
                        type="button"
                        className="btn-primary text-xs flex items-center gap-1.5 px-4 py-2"
                        onClick={() => handleDecision(appr.approval_id, 'APPROVED')}
                        disabled={actionLoading === appr.approval_id}
                      >
                        <CheckCircle2 size={14} />
                        <span>
                          {actionLoading === appr.approval_id
                            ? 'Executing...'
                            : isEditing
                            ? 'Approve & Dispatch Custom Email'
                            : 'Approve & Dispatch'}
                        </span>
                      </button>
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

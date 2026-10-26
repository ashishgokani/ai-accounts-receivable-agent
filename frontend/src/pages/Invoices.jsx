import { useState, useEffect } from 'react'
import {
  Eye,
  Filter,
  MessageSquareText,
  Banknote,
  Search,
  Send,
  AlertTriangle,
  CheckCircle,
  Clock,
  RotateCcw,
  Plus,
  Edit3,
} from 'lucide-react'
import { getInvoices, sendInvoiceReminder } from '../api/client'
import ReplySimulatorModal from '../components/ReplySimulatorModal'
import PaymentModal from '../components/PaymentModal'
import CreateInvoiceModal from '../components/CreateInvoiceModal'
import EditInvoiceModal from '../components/EditInvoiceModal'
import { formatISTDate } from '../utils/date'
import { formatINR } from '../utils/currency'

const statusBadge = {
  PAID: 'badge-paid',
  PENDING: 'badge-pending',
  OVERDUE: 'badge-overdue',
  PAYMENT_PROMISED: 'badge-processing',
  DISPUTED: 'badge-overdue',
  ESCALATED: 'badge-overdue',
}

function money(value) {
  return formatINR(value)
}

export default function Invoices() {
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('All')
  const [notice, setNotice] = useState(null)
  const [selected, setSelected] = useState(null)
  const [replyModalInv, setReplyModalInv] = useState(null)
  const [payModalInv, setPayModalInv] = useState(null)
  const [actionLoading, setActionLoading] = useState(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editInvoice, setEditInvoice] = useState(null)

  const loadData = async () => {
    setLoading(true)
    try {
      const data = await getInvoices({ status, search: query })
      setInvoices(data)
    } catch (err) {
      console.error('Failed to load invoices:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [status])

  // Auto-dismiss notice after 5 seconds
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [notice])

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    loadData()
  }

  const handleSendReminder = async (inv) => {
    setActionLoading(inv.invoice_id)
    try {
      const res = await sendInvoiceReminder(inv.invoice_id)
      if (res.status === 'PENDING_APPROVAL') {
        setNotice({
          type: 'warning',
          text: `Action for ${inv.invoice_id} paused: ${res.message}. Please approve in Approvals tab.`,
        })
      } else if (res.status === 'BLOCKED_BY_GUARDRAIL') {
        setNotice({
          type: 'error',
          text: `Guardrail blocked action: ${res.reason}`,
        })
      } else {
        setNotice({
          type: 'success',
          text: `Reminder #${res.reminder_count} dispatched to ${inv.company_name} for ${inv.invoice_id}.`,
        })
      }
      await loadData()
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Failed to dispatch reminder.' })
    } finally {
      setActionLoading(null)
    }
  }

  const counts = {
    Total: invoices.length,
    Paid: invoices.filter((i) => i.status === 'PAID').length,
    Pending: invoices.filter((i) => i.status === 'PENDING').length,
    Overdue: invoices.filter((i) => i.status === 'OVERDUE').length,
  }

  if (loading && invoices.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[420px] space-y-3">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
          Loading invoice portfolio and accrued penalties...
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-1">
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          <span className="font-semibold text-primary">{counts.Total} Total Invoices</span>
          <span>•</span>
          <span>{counts.Overdue} Overdue Accounts</span>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary flex items-center gap-1.5 text-xs font-semibold py-2 px-3.5" onClick={loadData}>
            <RotateCcw size={14} /> Refresh
          </button>
          <button
            className="btn-primary flex items-center gap-1.5 px-4 py-2 text-xs font-semibold shadow-sm"
            onClick={() => setShowCreateModal(true)}
          >
            <Plus size={14} /> Create Invoice
          </button>
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['Total Invoices', counts.Total, '#2563EB'],
          ['Paid / Settled', counts.Paid, '#22C55E'],
          ['Pending Regular', counts.Pending, '#F59E0B'],
          ['Overdue Invoices', counts.Overdue, '#EF4444'],
        ].map(([label, value, textColor]) => (
          <div key={label} className="kpi-card">
            <p className="kpi-label">{label}</p>
            <p className="kpi-value mt-2" style={{ color: textColor }}>{value}</p>
          </div>
        ))}
      </div>

      {/* Main Table Container */}
      <section className="card overflow-hidden">
        {/* Search & Filter Toolbar */}
        <form onSubmit={handleSearchSubmit} className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between" style={{ borderColor: 'var(--border)' }}>
          <div className="relative w-full max-w-md">
            <Search size={16} className="search-icon" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search invoice number or company name..."
              className="search-input w-full"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Filter size={14} style={{ color: 'var(--text-muted)' }} />
            {['All', 'Paid', 'Pending', 'Overdue', 'Disputed', 'Payment_Promised'].map((item) => (
              <button
                type="button"
                key={item}
                onClick={() => setStatus(item)}
                className={`filter-pill ${status.toLowerCase() === item.toLowerCase() ? 'active' : ''}`}
              >
                {item.replace('_', ' ')}
              </button>
            ))}
          </div>
        </form>

        {/* Action Notice Bar */}
        {notice && (
          <div
            className={`flex items-center justify-between border-b px-4 py-2.5 text-xs ${
              notice.type === 'success'
                ? 'bg-emerald-500/10 text-emerald-600'
                : notice.type === 'warning'
                ? 'bg-amber-500/10 text-amber-600'
                : 'bg-red-500/10 text-danger'
            }`}
            style={{ borderColor: 'var(--border)' }}
          >
            <div className="flex items-center gap-2">
              {notice.type === 'success' ? <CheckCircle size={14} /> : <AlertTriangle size={14} />}
              <span>{notice.text}</span>
            </div>
            <button className="font-semibold" onClick={() => setNotice(null)}>Dismiss</button>
          </div>
        )}

        {/* Invoices Table */}
        <div className="table-wrapper" style={{ maxHeight: '600px' }}>
          <table className="table">
            <thead>
              <tr>
                <th className="font-semibold">Invoice No</th>
                <th className="font-semibold">Customer</th>
                <th className="font-semibold">Principal</th>
                <th className="font-semibold">Accrued Penalty</th>
                <th className="font-semibold">Total Due</th>
                <th className="font-semibold">Due Date</th>
                <th className="font-semibold">Aging</th>
                <th className="font-semibold">Reminders</th>
                <th className="font-semibold">Status</th>
                <th className="font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={10} className="text-center py-10" style={{ color: 'var(--text-muted)' }}>
                    Loading invoices from database...
                  </td>
                </tr>
              ) : invoices.length === 0 ? (
                <tr>
                  <td colSpan={10} className="text-center py-10" style={{ color: 'var(--text-muted)' }}>
                    No matching invoices found.
                  </td>
                </tr>
              ) : (
                invoices.map((row) => (
                  <tr key={row.invoice_id}>
                    <td className="font-semibold" style={{ color: '#2563EB' }}>{row.invoice_id}</td>
                    <td style={{ color: 'var(--text)', fontWeight: 500 }}>{row.company_name}</td>
                    <td style={{ color: 'var(--text)' }}>{money(row.amount)}</td>
                    <td style={{ color: row.penalty_amount > 0 ? '#EF4444' : 'var(--text-muted)' }}>
                      <span className="font-semibold">{money(row.penalty_amount)}</span>
                      {row.penalty_amount > 0 && row.penalty_rate_percent && (
                        <span className="ml-1.5 text-[11px] font-normal opacity-80">
                          ({row.penalty_rate_percent}%)
                        </span>
                      )}
                    </td>
                    <td className="font-bold" style={{ color: 'var(--text)' }}>{money(row.total_amount)}</td>
                    <td style={{ color: 'var(--text-muted)' }}>{formatISTDate(row.due_date)}</td>
                    <td>
                      {row.days_overdue > 0 ? (
                        <span className="font-semibold text-danger">+{row.days_overdue} days</span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)' }}>Current</span>
                      )}
                    </td>
                    <td>
                      <span className="text-xs px-2 py-0.5 rounded bg-secondary" style={{ background: 'var(--bg-secondary)', color: 'var(--text)' }}>
                        {row.reminder_count}/3
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${statusBadge[row.status] || 'badge-processing'}`}>
                        <span className="h-1.5 w-1.5 rounded-full bg-current" />
                        {row.status.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          className="icon-btn h-8 w-8"
                          title="View Invoice Dossier"
                          onClick={() => setSelected(row)}
                        >
                          <Eye size={14} />
                        </button>

                        <button
                          className="icon-btn h-8 w-8 text-amber-500"
                          title="Edit Invoice Details"
                          onClick={() => setEditInvoice(row)}
                        >
                          <Edit3 size={14} />
                        </button>

                        {row.status !== 'PAID' && (
                          <>
                            <button
                              className="icon-btn h-8 w-8 text-primary"
                              title="Send Reminder"
                              onClick={() => handleSendReminder(row)}
                              disabled={actionLoading === row.invoice_id}
                            >
                              <Send size={14} />
                            </button>

                            <button
                              className="icon-btn h-8 w-8 text-purple-600"
                              title="Simulate Customer Reply (Demo)"
                              onClick={() => setReplyModalInv(row)}
                            >
                              <MessageSquareText size={14} />
                            </button>

                            <button
                              className="icon-btn h-8 w-8 text-success"
                              title="Record Payment Settlement"
                              onClick={() => setPayModalInv(row)}
                            >
                              <Banknote size={14} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Invoice Detail Modal */}
      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal-content max-w-lg" onClick={(e) => e.stopPropagation()}>
            <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
              Invoice Dossier & Financial Audit
            </p>
            <h3 className="mt-1 text-2xl font-bold" style={{ color: 'var(--text)' }}>
              {selected.invoice_id}
            </h3>

            <div className="mt-5 grid grid-cols-2 gap-4 text-xs">
              <div>
                <p className="form-label">Client Company</p>
                <p className="font-semibold" style={{ color: 'var(--text)' }}>{selected.company_name}</p>
                <p style={{ color: 'var(--text-muted)' }}>{selected.customer_name}</p>
              </div>
              <div>
                <p className="form-label">Workflow Status</p>
                <span className={`badge ${statusBadge[selected.status] || 'badge-processing'}`}>
                  {selected.status}
                </span>
              </div>
              <div>
                <p className="form-label">Principal Amount</p>
                <p className="font-semibold" style={{ color: 'var(--text)' }}>{money(selected.amount)}</p>
              </div>
              <div>
                <p className="form-label">
                  Accrued Late Penalty {selected.penalty_rate_percent ? `(${selected.penalty_rate_percent}% • ${selected.risk_level || ''} Tier)` : ''}
                </p>
                <p className="font-semibold text-danger">{money(selected.penalty_amount)}</p>
              </div>
              <div>
                <p className="form-label">Total Outstanding Balance</p>
                <p className="text-base font-bold text-primary">{money(selected.total_amount)}</p>
              </div>
              <div>
                <p className="form-label">Due Date & Aging</p>
                <p style={{ color: 'var(--text)' }}>{selected.due_date} ({selected.days_overdue} days overdue)</p>
              </div>
            </div>

            {selected.dispute_reason && (
              <div className="mt-4 p-3 rounded bg-red-500/10 border border-red-500/20 text-xs">
                <p className="font-bold text-danger">Dispute Notice on File:</p>
                <p className="mt-1" style={{ color: 'var(--text)' }}>{selected.dispute_reason}</p>
              </div>
            )}

            {selected.promised_payment_date && (
              <div className="mt-4 p-3 rounded bg-blue-500/10 border border-blue-500/20 text-xs">
                <p className="font-bold text-primary">Promise-to-Pay Date:</p>
                <p className="mt-1" style={{ color: 'var(--text)' }}>Customer committed payment by {selected.promised_payment_date}</p>
              </div>
            )}

            <div className="mt-6 flex flex-wrap gap-2 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
              <button className="btn-secondary flex-1" onClick={() => setSelected(null)}>
                Close
              </button>
              {selected.status !== 'PAID' && (
                <>
                  <button
                    className="btn-secondary flex-1 text-purple-600 flex items-center justify-center gap-1.5"
                    onClick={() => {
                      setReplyModalInv(selected)
                      setSelected(null)
                    }}
                  >
                    <MessageSquareText size={14} /> Simulate Reply
                  </button>
                  <button
                    className="btn-primary flex-1 flex items-center justify-center gap-1.5"
                    onClick={() => {
                      handleSendReminder(selected)
                      setSelected(null)
                    }}
                  >
                    <Send size={14} /> Send Reminder
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Customer Reply Simulator Modal */}
      {replyModalInv && (
        <ReplySimulatorModal
          invoice={replyModalInv}
          onClose={() => setReplyModalInv(null)}
          onProcessed={() => loadData()}
        />
      )}

      {/* Payment Settlement Modal */}
      {payModalInv && (
        <PaymentModal
          invoice={payModalInv}
          onClose={() => setPayModalInv(null)}
          onSettled={() => loadData()}
        />
      )}

      {/* Create New Invoice Modal */}
      {showCreateModal && (
        <CreateInvoiceModal
          onClose={() => setShowCreateModal(false)}
          onCreated={() => loadData()}
        />
      )}

      {/* Edit Invoice Modal */}
      {editInvoice && (
        <EditInvoiceModal
          invoice={editInvoice}
          onClose={() => setEditInvoice(null)}
          onUpdated={() => loadData()}
        />
      )}
    </div>
  )
}

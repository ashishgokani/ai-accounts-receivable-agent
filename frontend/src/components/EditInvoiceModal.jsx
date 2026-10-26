import { useState, useEffect } from 'react'
import { Edit3, X } from 'lucide-react'
import { updateInvoice } from '../api/client'

export default function EditInvoiceModal({ invoice, onClose, onUpdated }) {
  const [dueDate, setDueDate] = useState(invoice.due_date || '')
  const [amount, setAmount] = useState(invoice.amount || '')
  const [status, setStatus] = useState(invoice.status || 'PENDING')
  const [disputeReason, setDisputeReason] = useState(invoice.dispute_reason || '')
  const [promisedDate, setPromisedDate] = useState(invoice.promised_payment_date || '')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // Auto-dismiss error alert after 5 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [error])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      await updateInvoice(invoice.invoice_id, {
        due_date: dueDate,
        amount: parseFloat(amount),
        status,
        dispute_reason: disputeReason || null,
        promised_payment_date: promisedDate || null,
      })
      onUpdated()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to update invoice.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        className="w-full max-w-md rounded-card border p-6 space-y-4 shadow-xl"
        style={{ background: 'var(--card)', borderColor: 'var(--border)' }}
      >
        <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <Edit3 size={18} className="text-primary" />
            <h3 className="font-bold text-sm" style={{ color: 'var(--text)' }}>
              Edit Invoice {invoice.invoice_id}
            </h3>
          </div>
          <button onClick={onClose} className="text-muted hover:text-text">
            <X size={18} />
          </button>
        </div>

        {error && (
          <div className="p-2.5 rounded bg-red-500/10 border border-red-500/20 text-danger text-xs">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Billing Amount (₹)
              </label>
              <input
                type="number"
                step="0.01"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="search-input w-full"
              />
            </div>
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Due Date
              </label>
              <input
                type="date"
                required
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="search-input w-full"
              />
            </div>
          </div>

          <div>
            <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Status
            </label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="search-input w-full"
            >
              <option value="PENDING">PENDING</option>
              <option value="OVERDUE">OVERDUE</option>
              <option value="PAID">PAID</option>
              <option value="PAYMENT_PROMISED">PAYMENT_PROMISED</option>
              <option value="DISPUTED">DISPUTED</option>
              <option value="ESCALATED">ESCALATED</option>
            </select>
          </div>

          {status === 'DISPUTED' && (
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Dispute Reason
              </label>
              <textarea
                value={disputeReason}
                onChange={(e) => setDisputeReason(e.target.value)}
                rows={2}
                placeholder="Reason customer disputes billing..."
                className="search-input w-full resize-none"
              />
            </div>
          )}

          {status === 'PAYMENT_PROMISED' && (
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Promised Settlement Date
              </label>
              <input
                type="date"
                value={promisedDate}
                onChange={(e) => setPromisedDate(e.target.value)}
                className="search-input w-full"
              />
            </div>
          )}

          <div className="flex justify-end gap-2 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
            <button type="button" onClick={onClose} className="btn-secondary px-4 py-2">
              Cancel
            </button>
            <button type="submit" disabled={submitting} className="btn-primary px-4 py-2">
              {submitting ? 'Saving...' : 'Update Invoice'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { Banknote, CheckCircle, X, AlertTriangle } from 'lucide-react'
import { simulatePayment } from '../api/client'
import { formatINR } from '../utils/currency'

export default function PaymentModal({ invoice, onClose, onSettled }) {
  const [amount, setAmount] = useState(invoice.total_amount || invoice.amount)
  const [method, setMethod] = useState('NEFT')
  const [refNo, setRefNo] = useState(`REF/${Date.now().toString().slice(-6)}`)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  // Auto-dismiss error alert after 5 seconds
  useEffect(() => {
    if (!error) return
    const timer = setTimeout(() => setError(null), 5000)
    return () => clearTimeout(timer)
  }, [error])

  const handlePay = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const res = await simulatePayment(invoice.invoice_id, amount, method, refNo)
      setResult(res)
      if (onSettled) onSettled(res)
    } catch (err) {
      setError(err.message || 'Payment recording failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-btn bg-success text-white">
              <Banknote size={16} />
            </div>
            <div>
              <h3 className="text-base font-bold" style={{ color: 'var(--text)' }}>
                Record Customer Payment
              </h3>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Settles {invoice.invoice_id} ({invoice.company_name})
              </p>
            </div>
          </div>
          <button className="icon-btn-ghost h-8 w-8" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        {result ? (
          <div className="mt-4 space-y-4">
            <div className="rounded-card border p-4 bg-emerald-500/10 border-emerald-500/30">
              <div className="flex items-center gap-2 text-emerald-600 font-bold text-sm">
                <CheckCircle size={18} />
                <span>Payment Settlement Recorded</span>
              </div>
              <div className="mt-3 space-y-1.5 text-xs" style={{ color: 'var(--text)' }}>
                <p><strong>Payment ID:</strong> {result.payment_id}</p>
                <p><strong>Amount Credited:</strong> {formatINR(result.amount_received)}</p>
                <p><strong>Invoice Status:</strong> <span className="badge badge-paid">PAID</span></p>
                <p><strong>Pending Follow-ups Cancelled:</strong> {result.followups_cancelled}</p>
                <p><strong>Confirmation Notice:</strong> Dispatched via Email</p>
              </div>
            </div>

            <button className="btn-primary w-full" onClick={onClose}>
              Done & Refresh
            </button>
          </div>
        ) : (
          <form onSubmit={handlePay} className="mt-4 space-y-3">
            <div>
              <label className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Settlement Amount (₹)
              </label>
              <input
                type="number"
                step="any"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="search-input w-full mt-1"
              />
            </div>

            <div>
              <label className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Payment Method
              </label>
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value)}
                className="search-input w-full mt-1"
              >
                <option value="NEFT">NEFT (National Electronic Funds Transfer)</option>
                <option value="RTGS">RTGS (Real Time Gross Settlement)</option>
                <option value="UPI">UPI (Unified Payments Interface)</option>
                <option value="Wire Transfer">Direct Wire Transfer</option>
                <option value="Cheque">Corporate Cheque</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Bank Reference / UTR Number
              </label>
              <input
                type="text"
                required
                value={refNo}
                onChange={(e) => setRefNo(e.target.value)}
                className="search-input w-full mt-1"
              />
            </div>

            {error && (
              <div className="flex items-center justify-between gap-2 p-2 rounded-btn bg-danger/10 border border-danger/20 text-xs text-danger animate-fadeIn">
                <div className="flex items-center gap-2">
                  <AlertTriangle size={14} className="shrink-0" />
                  <span>{error}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setError(null)}
                  className="opacity-70 hover:opacity-100 transition-opacity ml-2"
                  title="Dismiss"
                >
                  <X size={12} />
                </button>
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <button type="button" className="btn-secondary flex-1" onClick={onClose} disabled={loading}>
                Cancel
              </button>
              <button type="submit" className="btn-primary flex-1" disabled={loading}>
                {loading ? 'Recording...' : 'Confirm Payment'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

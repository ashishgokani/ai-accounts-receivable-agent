import { useState, useEffect } from 'react'
import { MessageSquareText, Send, Sparkles, X, CheckCircle, AlertTriangle } from 'lucide-react'
import { simulateCustomerReply } from '../api/client'

const PRESETS = [
  {
    label: 'Promise Payment (Next Friday)',
    text: 'We apologize for the delay. Our finance department has scheduled the payment run for next Friday.',
  },
  {
    label: 'Dispute Invoice Amount (PO Discrepancy)',
    text: 'The invoice amount of ₹75,000 is incorrect. Our approved Purchase Order was for ₹70,000. Please revise.',
  },
  {
    label: 'Request 14-Day Extension',
    text: 'Due to ongoing quarterly cash flow audits, we request a 14-day grace extension on this invoice.',
  },
  {
    label: 'Claim Payment Already Sent',
    text: 'We have already remitted this payment via NEFT yesterday under reference UTR/992810482.',
  },
]

export default function ReplySimulatorModal({ invoice, onClose, onProcessed }) {
  const [message, setMessage] = useState(PRESETS[0].text)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  // Auto-dismiss error alert after 5 seconds
  useEffect(() => {
    if (!error) return
    const timer = setTimeout(() => setError(null), 5000)
    return () => clearTimeout(timer)
  }, [error])

  const handleSimulate = async () => {
    if (!message.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await simulateCustomerReply(invoice.invoice_id, message)
      setResult(res)
      if (onProcessed) onProcessed(res)
    } catch (err) {
      setError(err.message || 'Simulation failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content max-w-lg" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-btn bg-primary text-white">
              <MessageSquareText size={16} />
            </div>
            <div>
              <h3 className="text-base font-bold" style={{ color: 'var(--text)' }}>
                Simulate Customer Reply
              </h3>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Testing AI reply classification on {invoice.invoice_id} ({invoice.company_name})
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
                <span>AI Intent Classified Successfully</span>
              </div>
              <div className="mt-3 space-y-1.5 text-xs" style={{ color: 'var(--text)' }}>
                <p><strong>Detected Intent:</strong> <span className="badge badge-paid">{result.intent}</span></p>
                <p><strong>Confidence:</strong> {(result.confidence * 100).toFixed(1)}%</p>
                <p><strong>New Invoice Status:</strong> <span className="font-semibold">{result.new_invoice_status}</span></p>
                <p><strong>Action Executed:</strong> {result.action_taken}</p>
              </div>
            </div>

            <button className="btn-primary w-full" onClick={onClose}>
              Done & Refresh
            </button>
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            <div>
              <label className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Quick Preset Scenarios (Viva Demo)
              </label>
              <div className="mt-2 flex flex-col gap-1.5">
                {PRESETS.map((p, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => setMessage(p.text)}
                    className="text-left text-xs p-2 rounded border hover:bg-primary/5 transition-colors"
                    style={{ borderColor: 'var(--border)', color: 'var(--text)' }}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Inbound Email Message Body
              </label>
              <textarea
                rows={4}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                className="search-input w-full mt-1.5 text-xs"
                placeholder="Type incoming email message from client..."
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
              <button className="btn-secondary flex-1" onClick={onClose} disabled={loading}>
                Cancel
              </button>
              <button
                className="btn-primary flex-1 flex items-center justify-center gap-2"
                onClick={handleSimulate}
                disabled={loading}
              >
                {loading ? (
                  <span className="flex items-center gap-1.5">
                    <Sparkles size={14} className="animate-spin" /> Classifying...
                  </span>
                ) : (
                  <>
                    <Send size={14} /> Submit Simulation
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

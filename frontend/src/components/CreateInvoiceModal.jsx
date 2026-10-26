import { useState, useEffect } from 'react'
import { FilePlus, X } from 'lucide-react'
import { getCustomers, createInvoice } from '../api/client'
import { getISTTodayString } from '../utils/date'

export default function CreateInvoiceModal({ onClose, onCreated }) {
  const [customers, setCustomers] = useState([])
  const [customerId, setCustomerId] = useState('')
  const [invoiceNumber, setInvoiceNumber] = useState('')
  const [invoiceDate, setInvoiceDate] = useState(getISTTodayString())
  const [dueDate, setDueDate] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 30)
    return d.toISOString().split('T')[0]
  })
  const [amount, setAmount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // Auto-dismiss error alert after 5 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [error])

  useEffect(() => {
    async function loadCusts() {
      try {
        const list = await getCustomers({ status: 'ACTIVE' })
        setCustomers(list)
        if (list.length > 0) {
          setCustomerId(list[0].customer_id)
        }
      } catch (err) {
        console.error('Failed to load active customers:', err)
      }
    }
    loadCusts()

    // Generate random default invoice number
    setInvoiceNumber(`INV-${new Date().getFullYear()}-${Math.floor(1000 + Math.random() * 9000)}`)
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!amount || parseFloat(amount) <= 0) {
      setError('Please enter a valid billing amount greater than zero.')
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      await createInvoice({
        customer_id: customerId,
        invoice_number: invoiceNumber,
        invoice_date: invoiceDate,
        due_date: dueDate,
        amount: parseFloat(amount),
      })
      onCreated()
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to create invoice.')
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
            <FilePlus size={18} className="text-primary" />
            <h3 className="font-bold text-sm" style={{ color: 'var(--text)' }}>
              Create New Invoice
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
          <div>
            <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Select Customer *
            </label>
            <select
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              className="search-input w-full"
              required
            >
              {customers.map((c) => (
                <option key={c.customer_id} value={c.customer_id}>
                  {c.company_name} ({c.name})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Invoice Number *
            </label>
            <input
              required
              value={invoiceNumber}
              onChange={(e) => setInvoiceNumber(e.target.value)}
              placeholder="e.g. INV-2026-1045"
              className="search-input w-full"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Issue Date *
              </label>
              <input
                type="date"
                required
                value={invoiceDate}
                onChange={(e) => setInvoiceDate(e.target.value)}
                className="search-input w-full"
              />
            </div>
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Due Date *
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
              Principal Billing Amount (₹) *
            </label>
            <input
              type="number"
              step="0.01"
              required
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="e.g. 50000"
              className="search-input w-full font-bold"
            />
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
            <button type="button" onClick={onClose} className="btn-secondary px-4 py-2">
              Cancel
            </button>
            <button type="submit" disabled={submitting} className="btn-primary px-4 py-2">
              {submitting ? 'Generating...' : 'Create Invoice'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

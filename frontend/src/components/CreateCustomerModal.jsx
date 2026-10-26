import { useState, useEffect } from 'react'
import { UserPlus, X } from 'lucide-react'
import { createCustomer } from '../api/client'

/**
 * Modal dialog for onboarding a new corporate customer into the AR database.
 */
export default function CreateCustomerModal({ isOpen, onClose, onCreated }) {
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // Auto-dismiss error alert after 5 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [error])

  const [form, setForm] = useState({
    name: '',
    company_name: '',
    email: '',
    phone: '',
    address: '',
    risk_level: 'Low',
    risk_score: 25,
  })

  if (!isOpen) return null

  const handleRiskTierChange = (tier) => {
    let suggestedScore = 20
    if (tier === 'High') suggestedScore = 85
    else if (tier === 'Medium') suggestedScore = 50
    setForm((prev) => ({
      ...prev,
      risk_level: tier,
      risk_score: suggestedScore,
    }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await createCustomer({
        ...form,
        risk_score: parseInt(form.risk_score, 10) || 25,
      })
      onCreated(`Customer '${form.company_name}' successfully onboarded into database!`)
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to onboard corporate customer.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div
        className="card w-full max-w-lg p-6 space-y-4 animate-slideUp"
        style={{ background: 'var(--card)' }}
      >
        <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <UserPlus size={18} className="text-primary" />
            <h3 className="font-bold text-sm" style={{ color: 'var(--text)' }}>
              Add Corporate Customer
            </h3>
          </div>
          <button onClick={onClose} className="text-muted hover:text-text cursor-pointer">
            <X size={18} />
          </button>
        </div>

        {error && (
          <div className="p-3 text-xs font-semibold rounded-card bg-red-500/10 text-danger border border-danger/20">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3 text-xs">
          <div>
            <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Company Legal Name *
            </label>
            <input
              required
              value={form.company_name}
              onChange={(e) => setForm({ ...form, company_name: e.target.value })}
              placeholder="e.g. Apex Global Logistics Ltd"
              className="search-input w-full"
            />
          </div>

          <div>
            <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Billing Contact Name *
            </label>
            <input
              required
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="e.g. Rajesh Kumar"
              className="search-input w-full"
            />
          </div>

          <div>
            <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Corporate Email *
            </label>
            <input
              type="email"
              required
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              placeholder="accounts@apexlogistics.com"
              className="search-input w-full"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Phone Number
              </label>
              <input
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="+91 98765 43210"
                className="search-input w-full"
              />
            </div>
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Corporate Address
              </label>
              <input
                value={form.address}
                onChange={(e) => setForm({ ...form, address: e.target.value })}
                placeholder="Bandra Kurla Complex, Mumbai"
                className="search-input w-full"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Credit Risk Tier
              </label>
              <select
                value={form.risk_level}
                onChange={(e) => handleRiskTierChange(e.target.value)}
                className="search-input w-full"
              >
                <option value="Low">Low Risk</option>
                <option value="Medium">Medium Risk</option>
                <option value="High">High Risk</option>
              </select>
            </div>
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Credit Risk Score (0-100) *
              </label>
              <input
                type="number"
                min="0"
                max="100"
                required
                value={form.risk_score}
                onChange={(e) => setForm({ ...form, risk_score: e.target.value })}
                placeholder="25"
                className="search-input w-full"
              />
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary px-4 py-2 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary px-4 py-2 cursor-pointer"
            >
              {submitting ? 'Onboarding...' : 'Save Customer'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { Edit3, X } from 'lucide-react'
import { updateCustomer } from '../api/client'

/**
 * EditCustomerModal Component
 * Allows managers to update customer details, contact info, and credit risk tier.
 */
export default function EditCustomerModal({ customer, onClose, onUpdated }) {
  const [name, setName] = useState(customer.name || '')
  const [companyName, setCompanyName] = useState(customer.company_name || '')
  const [email, setEmail] = useState(customer.email || '')
  const [phone, setPhone] = useState(customer.phone || '')
  const [address, setAddress] = useState(customer.address || '')
  const [riskLevel, setRiskLevel] = useState(customer.risk_level || 'Low')
  const [riskScore, setRiskScore] = useState(customer.risk_score || 25)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // Auto-dismiss error alert after 5 seconds
  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [error])

  const handleRiskLevelChange = (newLevel) => {
    setRiskLevel(newLevel)
    if (newLevel === 'High') setRiskScore(85)
    else if (newLevel === 'Medium') setRiskScore(50)
    else setRiskScore(20)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      await updateCustomer(customer.customer_id, {
        name,
        company_name: companyName,
        email,
        phone,
        address,
        risk_level: riskLevel,
        risk_score: parseInt(riskScore, 10),
      })
      onUpdated(`Customer '${companyName}' profile successfully updated!`)
      onClose()
    } catch (err) {
      setError(err.message || 'Failed to update customer profile.')
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
              Edit Customer {customer.customer_id}
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
              Company Legal Name *
            </label>
            <input
              required
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              className="search-input w-full"
            />
          </div>

          <div>
            <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Billing Contact Person *
            </label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
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
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="search-input w-full"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Phone / Mobile
              </label>
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                className="search-input w-full"
                placeholder="+91 98765 43210"
              />
            </div>
            <div>
              <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
                Credit Risk Tier
              </label>
              <select
                value={riskLevel}
                onChange={(e) => handleRiskLevelChange(e.target.value)}
                className="search-input w-full"
              >
                <option value="Low">Low Risk</option>
                <option value="Medium">Medium Risk</option>
                <option value="High">High Risk</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Credit Risk Score (0-100)
            </label>
            <input
              type="number"
              min="0"
              max="100"
              value={riskScore}
              onChange={(e) => setRiskScore(e.target.value)}
              className="search-input w-full"
            />
          </div>

          <div>
            <label className="block mb-1 font-semibold" style={{ color: 'var(--text-secondary)' }}>
              Corporate Address
            </label>
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              className="search-input w-full"
              placeholder="Corporate Office Address"
            />
          </div>

          <div className="flex justify-end gap-2 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
            <button
              type="button"
              onClick={onClose}
              className="btn-secondary px-4 py-2"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="btn-primary px-4 py-2"
            >
              {submitting ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

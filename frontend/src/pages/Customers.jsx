import { useState, useEffect } from 'react'
import {
  Building2,
  Mail,
  Phone,
  Search,
  UserPlus,
  Trash2,
  RotateCcw,
  AlertTriangle,
  CheckCircle2,
  X,
  Archive,
  RefreshCw,
  Edit3,
} from 'lucide-react'
import {
  getCustomers,
  removeCustomer,
  restoreCustomer,
} from '../api/client'
import EditCustomerModal from '../components/EditCustomerModal'
import CreateCustomerModal from '../components/CreateCustomerModal'

const riskBadge = {
  Low: 'badge-risk-low',
  Medium: 'badge-risk-medium',
  High: 'badge-risk-high',
}

const riskBarColor = {
  Low: '#22C55E',
  Medium: '#F59E0B',
  High: '#EF4444',
}

export default function Customers() {
  const [activeTab, setActiveTab] = useState('ACTIVE') // 'ACTIVE' or 'ARCHIVED'
  const [customers, setCustomers] = useState([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [risk, setRisk] = useState('All')
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingCustomer, setEditingCustomer] = useState(null)
  const [notice, setNotice] = useState(null)
  const [fetchError, setFetchError] = useState(null)

  const loadData = async () => {
    setLoading(true)
    setFetchError(null)
    try {
      const data = await getCustomers({
        status: activeTab,
        risk,
        search: query,
      })
      setCustomers(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error('Failed to load customers:', err)
      setFetchError(err.message || 'Unable to connect to the database or retrieve customers.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [activeTab, risk])

  // Auto-dismiss notice feedback after 5 seconds
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

  const handleRemove = async (cust) => {
    if (!window.confirm(`Are you sure you want to move '${cust.company_name}' to the Removed Section?`)) {
      return
    }

    try {
      await removeCustomer(cust.customer_id)
      setNotice({
        type: 'success',
        text: `Customer '${cust.company_name}' moved to Removed Section.`,
      })
      await loadData()
    } catch (err) {
      setNotice({
        type: 'error',
        text: err.message || 'Customer removal blocked by business policy.',
      })
    }
  }

  const handleRestore = async (cust) => {
    try {
      await restoreCustomer(cust.customer_id)
      setNotice({
        type: 'success',
        text: `Customer '${cust.company_name}' restored to Active status.`,
      })
      await loadData()
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Failed to restore customer.' })
    }
  }

  if (loading && customers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[420px] space-y-3">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
          Loading corporate customer directory and risk scores...
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Top Header Actions */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-1">
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-muted)' }}>
          <span className="font-semibold text-primary">{customers.length} Corporate Accounts</span>
          <span>•</span>
          <span>{activeTab === 'ACTIVE' ? 'Active Directory' : 'Removed Archive'}</span>
        </div>
        <div className="flex items-center gap-2">
          <button className="btn-secondary flex items-center gap-1.5 text-xs font-semibold py-2 px-3.5" onClick={loadData}>
            <RotateCcw size={14} /> Refresh
          </button>
          <button
            className="btn-primary flex items-center gap-1.5 px-4 py-2 text-xs font-semibold shadow-sm"
            onClick={() => setShowAddModal(true)}
          >
            <UserPlus size={14} /> Add Customer
          </button>
        </div>
      </div>

      {/* Tabs: Active Customers vs Removed Section */}
      <div className="flex border-b text-xs font-semibold" style={{ borderColor: 'var(--border)' }}>
        <button
          onClick={() => setActiveTab('ACTIVE')}
          className={`px-4 py-2.5 border-b-2 flex items-center gap-2 transition-all ${
            activeTab === 'ACTIVE'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted hover:text-text'
          }`}
        >
          <Building2 size={14} />
          Active Directory
        </button>
        <button
          onClick={() => setActiveTab('ARCHIVED')}
          className={`px-4 py-2.5 border-b-2 flex items-center gap-2 transition-all ${
            activeTab === 'ARCHIVED'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted hover:text-text'
          }`}
        >
          <Archive size={14} />
          Removed Section
        </button>
      </div>

      {/* Notice Feedback Banner */}
      {notice && (
        <div
          className={`flex items-center justify-between p-3 rounded-card text-xs border ${
            notice.type === 'success'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600'
              : 'bg-red-500/10 border-red-500/30 text-danger'
          }`}
        >
          <div className="flex items-center gap-2">
            {notice.type === 'success' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            <span>{notice.text}</span>
          </div>
          <button onClick={() => setNotice(null)} className="font-bold">
            Dismiss
          </button>
        </div>
      )}

      {/* Search and Risk Filter Toolbar */}
      <form onSubmit={handleSearchSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search size={16} className="search-icon" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by company name, contact, or email..."
            className="search-input w-full"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {['All', 'Low', 'Medium', 'High'].map((item) => (
            <button
              type="button"
              key={item}
              onClick={() => setRisk(item)}
              className={`filter-pill ${risk === item ? 'active' : ''}`}
            >
              {item} Risk
            </button>
          ))}
        </div>
      </form>

      {/* Customer Profile Cards Grid */}
      {loading ? (
        <div className="card p-12 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
          <div className="h-8 w-8 mx-auto mb-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          Loading corporate customer directory from database...
        </div>
      ) : fetchError ? (
        <div className="card p-10 text-center space-y-3" style={{ borderColor: 'var(--danger)', background: 'var(--card)' }}>
          <AlertTriangle size={28} className="mx-auto text-danger" />
          <p className="text-sm font-semibold text-danger">{fetchError}</p>
          <button
            type="button"
            onClick={loadData}
            className="btn-secondary text-xs px-4 py-2 mx-auto rounded-btn shadow-sm"
          >
            Retry Loading Customers
          </button>
        </div>
      ) : customers.length === 0 ? (
        <div className="card p-12 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
          {activeTab === 'ACTIVE'
            ? 'No active customers found matching your filters.'
            : 'No archived customers in Removed Section.'}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {customers.map((cust) => (
            <div key={cust.customer_id} className="card p-5 space-y-4 flex flex-col justify-between">
              <div>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-btn bg-primary/10 text-primary">
                      <Building2 size={20} />
                    </div>
                    <div>
                      <h3 className="font-bold text-sm" style={{ color: 'var(--text)' }}>
                        {cust.company_name}
                      </h3>
                      <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                        Contact: {cust.name} ({cust.customer_id})
                      </p>
                    </div>
                  </div>
                  <span className={`badge ${riskBadge[cust.risk_level] || 'badge-risk-low'}`}>
                    {cust.risk_level} Risk
                  </span>
                </div>

                {/* Credit Risk Meter */}
                <div className="mt-4">
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span style={{ color: 'var(--text-muted)' }}>Credit Risk Score</span>
                    <span className="font-semibold" style={{ color: riskBarColor[cust.risk_level] }}>
                      {cust.risk_score} / 100
                    </span>
                  </div>
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{
                        width: `${cust.risk_score}%`,
                        background: riskBarColor[cust.risk_level],
                      }}
                    />
                  </div>
                </div>

                {/* Contact Details */}
                <div className="pt-3 mt-3 border-t space-y-1.5 text-xs" style={{ borderColor: 'var(--border)' }}>
                  <div className="flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
                    <Mail size={13} className="text-primary" />
                    <span className="truncate">{cust.email}</span>
                  </div>
                  {cust.phone && (
                    <div className="flex items-center gap-2" style={{ color: 'var(--text-secondary)' }}>
                      <Phone size={13} className="text-emerald-500" />
                      <span>{cust.phone}</span>
                    </div>
                  )}
                  {cust.address && (
                    <p className="text-[11px] pt-1 truncate" style={{ color: 'var(--text-muted)' }}>
                      📍 {cust.address}
                    </p>
                  )}
                </div>
              </div>

              {/* Action Buttons: Edit, Remove Guardrail vs Restore */}
              <div className="pt-3 border-t flex justify-end gap-2" style={{ borderColor: 'var(--border)' }}>
                {activeTab === 'ACTIVE' && (
                  <button
                    onClick={() => setEditingCustomer(cust)}
                    className="btn-secondary text-xs flex items-center gap-1.5 text-primary border-primary/20 hover:bg-primary/10"
                    title="Edit customer details, address, or credit risk tier"
                  >
                    <Edit3 size={13} />
                    <span>Edit</span>
                  </button>
                )}
                {activeTab === 'ACTIVE' ? (
                  <button
                    onClick={() => handleRemove(cust)}
                    className="btn-secondary text-xs flex items-center gap-1.5 text-danger border-red-500/20 hover:bg-red-500/10"
                    title="Remove customer (Requires zero pending invoices)"
                  >
                    <Trash2 size={13} />
                    <span>Remove</span>
                  </button>
                ) : (
                  <button
                    onClick={() => handleRestore(cust)}
                    className="btn-secondary text-xs flex items-center gap-1.5 text-emerald-600 border-emerald-500/20 hover:bg-emerald-500/10"
                  >
                    <RefreshCw size={13} />
                    <span>Restore to Active</span>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ================= ADD CUSTOMER MODAL ================= */}
      <CreateCustomerModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onCreated={(msg) => {
          setNotice({ type: 'success', text: msg })
          loadData()
        }}
      />

      {/* ================= EDIT CUSTOMER MODAL ================= */}
      {editingCustomer && (
        <EditCustomerModal
          customer={editingCustomer}
          onClose={() => setEditingCustomer(null)}
          onUpdated={(msg) => {
            setNotice({ type: 'success', text: msg })
            loadData()
          }}
        />
      )}
    </div>
  )
}

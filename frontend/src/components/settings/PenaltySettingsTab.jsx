import { HelpCircle, Save, CheckCircle, AlertCircle } from 'lucide-react'

/**
 * Penalty & Financial Rules Tab Component
 *
 * Configures late payment penalty percentages and grace periods
 * separately for Low Risk, Medium Risk, and High Risk customer tiers.
 * Penalties apply strictly to the principal amount (non-compounding).
 */
export default function PenaltySettingsTab({
  penaltyForm,
  setPenaltyForm,
  penaltyRiskTab,
  setPenaltyRiskTab,
  riskLabels,
  handleSavePenalty,
  saving,
  notice,
}) {
  return (
    <form onSubmit={handleSavePenalty} className="space-y-6">
      <div className="card p-6 sm:p-7 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b pb-4" style={{ borderColor: 'var(--border)' }}>
          <div>
            <h2 className="text-base sm:text-lg font-bold" style={{ color: 'var(--text)' }}>
              Late Payment Penalty & Grace Periods
            </h2>
            <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Configure interest rates and grace periods separately based on customer credit risk tiers.
            </p>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-600 dark:text-blue-400 text-xs font-semibold self-start sm:self-auto">
            <HelpCircle size={15} />
            <span>Non-Compounding (Principal Only)</span>
          </div>
        </div>

        {/* Risk Tier Tabs */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider mb-2.5" style={{ color: 'var(--text-muted)' }}>
            Select Customer Risk Tier
          </label>
          <div className="flex gap-2.5">
            {['low_risk', 'medium_risk', 'high_risk'].map((tier) => (
              <button
                type="button"
                key={tier}
                onClick={() => setPenaltyRiskTab(tier)}
                className={`px-4 py-2 text-sm font-semibold rounded-btn transition-colors ${
                  penaltyRiskTab === tier ? 'btn-primary' : 'btn-secondary'
                }`}
              >
                {riskLabels[tier]}
              </button>
            ))}
          </div>
        </div>

        {/* Config Fields for Selected Risk Tier */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-1">
          <div>
            <label className="form-label font-semibold text-sm">
              Late Payment Penalty Rate (% per 30-day cycle)
            </label>
            <input
              type="number"
              step="0.1"
              min="0"
              max="100"
              required
              value={penaltyForm[penaltyRiskTab].penalty_rate_percent}
              onChange={(e) =>
                setPenaltyForm({
                  ...penaltyForm,
                  [penaltyRiskTab]: {
                    ...penaltyForm[penaltyRiskTab],
                    penalty_rate_percent: parseFloat(e.target.value) || 0,
                  },
                })
              }
              className="input"
            />
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              Deterministic monthly interest rate calculated exclusively on outstanding principal.
            </p>
          </div>

          <div>
            <label className="form-label font-semibold text-sm">
              Grace Period (Days after Due Date)
            </label>
            <input
              type="number"
              min="0"
              max="365"
              required
              value={penaltyForm[penaltyRiskTab].grace_period_days}
              onChange={(e) =>
                setPenaltyForm({
                  ...penaltyForm,
                  [penaltyRiskTab]: {
                    ...penaltyForm[penaltyRiskTab],
                    grace_period_days: parseInt(e.target.value, 10) || 0,
                  },
                })
              }
              className="input"
            />
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              Zero penalties accrue until overdue days strictly exceed this threshold.
            </p>
          </div>
        </div>

        <div
          className="p-4 rounded-card border text-sm leading-relaxed"
          style={{ background: 'var(--card-secondary)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
        >
          💡 <strong className="font-semibold" style={{ color: 'var(--text)' }}>Calculation Policy:</strong> Penalties apply strictly to the invoice principal amount.
          Previously accrued penalties are excluded to prevent compounding. Cycle timing is managed internally in the backend.
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
        <div className="flex-1 min-w-0">
          {notice && (
            <div
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded text-xs font-semibold animate-fadeIn ${
                notice.type === 'success'
                  ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                  : 'bg-red-500/15 text-danger border border-red-500/30'
              }`}
            >
              {notice.type === 'success' ? <CheckCircle size={15} /> : <AlertCircle size={15} />}
              <span>{notice.text}</span>
            </div>
          )}
        </div>
        <button type="submit" disabled={saving} className="btn-primary px-6 py-2.5 text-sm font-semibold flex items-center gap-2 shadow-sm shrink-0 ml-auto">
          <Save size={16} /> {saving ? 'Saving Rules...' : 'Save Penalty Rules'}
        </button>
      </div>
    </form>
  )
}

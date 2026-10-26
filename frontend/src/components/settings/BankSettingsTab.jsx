import { Landmark, Save, CheckCircle, AlertCircle } from 'lucide-react'

/**
 * Payment & Bank Details Tab Component
 *
 * Configures corporate remittance coordinates dynamically injected
 * into customer reminder notices and early settlement agreements.
 * Validates that Account Number and Confirm Account Number match before submission.
 */
export default function BankSettingsTab({
  bankForm,
  setBankForm,
  handleSaveBank,
  saving,
  notice,
}) {
  return (
    <form onSubmit={handleSaveBank} className="space-y-6">
      <div className="card p-6 sm:p-7 space-y-6">
        <div className="border-b pb-4" style={{ borderColor: 'var(--border)' }}>
          <h2 className="text-base sm:text-lg font-bold" style={{ color: 'var(--text)' }}>
            Corporate Remittance Bank Details
          </h2>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            These banking credentials are dynamically embedded into automated reminder notices and settlement agreements.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div>
            <label className="form-label font-semibold text-sm">
              Beneficiary / Account Holder Name *
            </label>
            <input
              required
              value={bankForm.beneficiary_name}
              onChange={(e) => setBankForm({ ...bankForm, beneficiary_name: e.target.value })}
              placeholder="e.g. Accounts Receivable Management"
              className="input"
            />
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              Legal entity name as registered on corporate bank records.
            </p>
          </div>

          <div>
            <label className="form-label font-semibold text-sm">
              Bank Legal Name *
            </label>
            <input
              required
              value={bankForm.bank_name}
              onChange={(e) => setBankForm({ ...bankForm, bank_name: e.target.value })}
              placeholder="e.g. HDFC Corporate Banking"
              className="input"
            />
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              Name of the commercial banking institution.
            </p>
          </div>

          <div>
            <label className="form-label font-semibold text-sm">
              Account Number *
            </label>
            <input
              required
              value={bankForm.account_number}
              onChange={(e) => setBankForm({ ...bankForm, account_number: e.target.value })}
              placeholder="e.g. 9182309182301"
              className="input font-mono"
            />
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              Primary receiving business current or escrow account.
            </p>
          </div>

          <div>
            <label className="form-label font-semibold text-sm">
              Confirm Account Number *
            </label>
            <input
              required
              value={bankForm.confirm_account_number}
              onChange={(e) => setBankForm({ ...bankForm, confirm_account_number: e.target.value })}
              placeholder="Re-enter account number"
              className={`input font-mono ${
                bankForm.confirm_account_number &&
                bankForm.confirm_account_number !== bankForm.account_number
                  ? 'border-red-500 ring-2 ring-red-500/20'
                  : ''
              }`}
            />
            {bankForm.confirm_account_number &&
              bankForm.confirm_account_number !== bankForm.account_number ? (
                <span className="text-xs text-red-500 block mt-1.5 font-medium">
                  Account numbers do not match.
                </span>
              ) : (
                <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
                  Verification field to prevent typos in remittance details.
                </p>
              )}
          </div>

          <div className="sm:col-span-2">
            <label className="form-label font-semibold text-sm">
              IFSC / Swift Code *
            </label>
            <input
              required
              value={bankForm.ifsc_code}
              onChange={(e) => setBankForm({ ...bankForm, ifsc_code: e.target.value.toUpperCase() })}
              placeholder="e.g. HDFC0001234"
              className="input font-mono uppercase"
            />
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              11-character Indian Financial System Code for NEFT/RTGS/IMPS settlement.
            </p>
          </div>
        </div>

        <div>
          <label className="form-label font-semibold text-sm">
            Payment Reference Instructions (Displayed in all emails)
          </label>
          <textarea
            rows={2}
            value={bankForm.payment_instructions}
            onChange={(e) => setBankForm({ ...bankForm, payment_instructions: e.target.value })}
            placeholder="e.g. Please quote invoice number in the transfer remarks and email UTR receipt."
            className="input min-h-[85px] text-sm"
          />
        </div>
      </div>

      {/* Live Preview Card */}
      <div
        className="rounded-card border p-5 space-y-3"
        style={{ background: 'var(--card-secondary)', borderColor: 'var(--border)' }}
      >
        <p className="font-semibold text-sm sm:text-base flex items-center gap-2" style={{ color: 'var(--text)' }}>
          <Landmark size={18} className="text-primary" /> Remittance Preview as Displayed in Notices
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-1 font-mono text-sm" style={{ color: 'var(--text-secondary)' }}>
          <div>
            <span className="text-xs text-muted block mb-0.5">Bank:</span>
            <strong className="text-sm font-semibold" style={{ color: 'var(--text)' }}>{bankForm.bank_name || '—'}</strong>
          </div>
          <div>
            <span className="text-xs text-muted block mb-0.5">Account:</span>
            <strong className="text-sm font-semibold" style={{ color: 'var(--text)' }}>{bankForm.account_number || '—'}</strong>
          </div>
          <div>
            <span className="text-xs text-muted block mb-0.5">IFSC:</span>
            <strong className="text-sm font-semibold" style={{ color: 'var(--text)' }}>{bankForm.ifsc_code || '—'}</strong>
          </div>
          <div>
            <span className="text-xs text-muted block mb-0.5">Beneficiary:</span>
            <strong className="text-sm font-semibold" style={{ color: 'var(--text)' }}>{bankForm.beneficiary_name || '—'}</strong>
          </div>
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
          <Save size={16} /> {saving ? 'Saving Bank Details...' : 'Save Bank Details'}
        </button>
      </div>
    </form>
  )
}

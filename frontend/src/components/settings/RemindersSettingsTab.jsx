import { Save, CheckCircle, AlertCircle } from 'lucide-react'

/**
 * Payment Reminders & Escalation Tab Component
 *
 * Configures global collection automation toggles and frequency, as well as
 * risk-tiered reminder schedules, interval cadences, escalation thresholds,
 * human approval requirements, and dispute pause rules.
 */
export default function RemindersSettingsTab({
  reminderForm,
  setReminderForm,
  reminderRiskTab,
  setReminderRiskTab,
  riskLabels,
  handleSaveReminders,
  saving,
  notice,
}) {
  return (
    <form onSubmit={handleSaveReminders} className="space-y-6">
      {/* Global Automation Bar */}
      <div className="card p-6 sm:p-7 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b pb-4 gap-3" style={{ borderColor: 'var(--border)' }}>
          <div>
            <h2 className="text-base sm:text-lg font-bold" style={{ color: 'var(--text)' }}>
              Global Collection Automation
            </h2>
            <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Master controls that govern background collection scheduler execution across all accounts.
            </p>
          </div>
          <div className="flex items-center gap-3 self-start sm:self-auto">
            <span
              className="text-sm font-semibold"
              style={{ color: reminderForm.automation_enabled ? 'var(--primary)' : 'var(--text-muted)' }}
            >
              {reminderForm.automation_enabled ? 'Automation Enabled' : 'Automation Disabled'}
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={reminderForm.automation_enabled}
              onClick={() =>
                setReminderForm({ ...reminderForm, automation_enabled: !reminderForm.automation_enabled })
              }
              className={`relative inline-flex h-8 w-14 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
                reminderForm.automation_enabled ? 'bg-primary' : 'bg-gray-300 dark:bg-gray-600'
              }`}
              title={reminderForm.automation_enabled ? 'Click to disable automation' : 'Click to enable automation'}
            >
              <span
                aria-hidden="true"
                className={`pointer-events-none inline-block h-7 w-7 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                  reminderForm.automation_enabled ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <div>
            <label className="form-label font-semibold text-sm">
              Background Automation Frequency
            </label>
            <select
              value={reminderForm.automation_interval_minutes}
              onChange={(e) =>
                setReminderForm({
                  ...reminderForm,
                  automation_interval_minutes: parseInt(e.target.value, 10),
                })
              }
              className="input"
            >
              <option value={15}>Every 15 Minutes (Recommended)</option>
              <option value={30}>Every 30 Minutes</option>
              <option value={60}>Every 1 Hour</option>
              <option value={120}>Every 2 Hours</option>
              <option value={1440}>Once Daily (24 Hours)</option>
            </select>
            <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
              Interval at which the background engine scans overdue invoices and updates follow-up queues.
            </p>
          </div>
        </div>
      </div>

      {/* Risk Tier Specific Reminder Rules */}
      <div className="card p-6 sm:p-7 space-y-6">
        <div className="border-b pb-4" style={{ borderColor: 'var(--border)' }}>
          <h2 className="text-base sm:text-lg font-bold" style={{ color: 'var(--text)' }}>
            Cadence & Escalation Thresholds by Risk Tier
          </h2>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Select a customer risk tier to configure its automated reminder timeline and escalation limits.
          </p>
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
                onClick={() => setReminderRiskTab(tier)}
                className={`px-4 py-2 text-sm font-semibold rounded-btn transition-colors ${
                  reminderRiskTab === tier ? 'btn-primary' : 'btn-secondary'
                }`}
              >
                {riskLabels[tier]}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-6 pt-1">
          <label className="flex items-center gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={reminderForm[reminderRiskTab].auto_reminders_enabled}
              onChange={(e) =>
                setReminderForm({
                  ...reminderForm,
                  [reminderRiskTab]: {
                    ...reminderForm[reminderRiskTab],
                    auto_reminders_enabled: e.target.checked,
                  },
                })
              }
              className="h-4 w-4 rounded text-primary focus:ring-0"
            />
            <span className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
              Enable Automated Reminders for {riskLabels[reminderRiskTab]} Customers
            </span>
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            <div>
              <label className="form-label font-semibold text-sm">
                First Reminder (Days after Due Date)
              </label>
              <input
                type="number"
                min="0"
                max="90"
                required
                value={reminderForm[reminderRiskTab].first_reminder_days}
                onChange={(e) =>
                  setReminderForm({
                    ...reminderForm,
                    [reminderRiskTab]: {
                      ...reminderForm[reminderRiskTab],
                      first_reminder_days: parseInt(e.target.value, 10) || 0,
                    },
                  })
                }
                className="input"
              />
              <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
                Days to wait after invoice due date before sending initial notice.
              </p>
            </div>

            <div>
              <label className="form-label font-semibold text-sm">
                Reminder Interval (Days between notices)
              </label>
              <input
                type="number"
                min="1"
                max="90"
                required
                value={reminderForm[reminderRiskTab].reminder_interval_days}
                onChange={(e) =>
                  setReminderForm({
                    ...reminderForm,
                    [reminderRiskTab]: {
                      ...reminderForm[reminderRiskTab],
                      reminder_interval_days: parseInt(e.target.value, 10) || 1,
                    },
                  })
                }
                className="input"
              />
              <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
                Cadence between subsequent follow-up communications.
              </p>
            </div>

            <div>
              <label className="form-label font-semibold text-sm">
                Max Reminders before Escalation
              </label>
              <input
                type="number"
                min="1"
                max="10"
                required
                value={reminderForm[reminderRiskTab].max_reminders_before_escalation}
                onChange={(e) =>
                  setReminderForm({
                    ...reminderForm,
                    [reminderRiskTab]: {
                      ...reminderForm[reminderRiskTab],
                      max_reminders_before_escalation: parseInt(e.target.value, 10) || 1,
                    },
                  })
                }
                className="input"
              />
              <p className="text-xs mt-1.5" style={{ color: 'var(--text-muted)' }}>
                Maximum notices before the invoice is flagged for administrative escalation.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-1">
            <label
              className="flex items-start gap-3 cursor-pointer p-4 rounded-card border transition-colors"
              style={{ background: 'var(--card-secondary)', borderColor: 'var(--border)' }}
            >
              <input
                type="checkbox"
                checked={reminderForm[reminderRiskTab].final_reminder_approval_required}
                onChange={(e) =>
                  setReminderForm({
                    ...reminderForm,
                    [reminderRiskTab]: {
                      ...reminderForm[reminderRiskTab],
                      final_reminder_approval_required: e.target.checked,
                    },
                  })
                }
                className="h-4 w-4 rounded text-primary focus:ring-0 mt-0.5"
              />
              <div>
                <p className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
                  Final Notice Requires Human Approval
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  Routes the final pre-escalation notice to the Approvals queue for review before sending.
                </p>
              </div>
            </label>

            <label
              className="flex items-start gap-3 cursor-pointer p-4 rounded-card border transition-colors"
              style={{ background: 'var(--card-secondary)', borderColor: 'var(--border)' }}
            >
              <input
                type="checkbox"
                checked={reminderForm[reminderRiskTab].pause_on_dispute}
                onChange={(e) =>
                  setReminderForm({
                    ...reminderForm,
                    [reminderRiskTab]: {
                      ...reminderForm[reminderRiskTab],
                      pause_on_dispute: e.target.checked,
                    },
                  })
                }
                className="h-4 w-4 rounded text-primary focus:ring-0 mt-0.5"
              />
              <div>
                <p className="text-sm font-semibold" style={{ color: 'var(--text)' }}>
                  Pause Reminders on Disputed Invoices
                </p>
                <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  Immediately freezes automated collection emails while an invoice is marked as disputed.
                </p>
              </div>
            </label>
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
          <Save size={16} /> {saving ? 'Saving Reminders...' : 'Save Reminder Cadence'}
        </button>
      </div>
    </form>
  )
}

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ShieldAlert,
  BellRing,
  Landmark,
  Bot,
  CheckCircle,
  AlertCircle,
  ArrowLeft,
  Sparkles,
} from 'lucide-react'
import {
  getAdminSettings,
  updatePenaltySettings,
  updateReminderSettings,
  updateBankSettings,
  updateAgentSettings,
} from '../api/client'

import PenaltySettingsTab from '../components/settings/PenaltySettingsTab'
import RemindersSettingsTab from '../components/settings/RemindersSettingsTab'
import BankSettingsTab from '../components/settings/BankSettingsTab'
import AgentSettingsTab from '../components/settings/AgentSettingsTab'

/**
 * Admin Settings Management Page
 *
 * Coordinates configuration across:
 * 1. Penalty & Financial Rules
 * 2. Payment Reminders & Escalation
 * 3. Payment & Bank Details
 * 4. Agent Settings
 */
export default function Settings() {
  const navigate = useNavigate()
  const [activeSection, setActiveSection] = useState('penalty')
  const [penaltyRiskTab, setPenaltyRiskTab] = useState('medium_risk')
  const [reminderRiskTab, setReminderRiskTab] = useState('medium_risk')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [notice, setNotice] = useState(null)

  // Settings State
  const [penaltyForm, setPenaltyForm] = useState({
    calculation_base: 'PRINCIPAL_ONLY',
    low_risk: { penalty_rate_percent: 1.0, grace_period_days: 14 },
    medium_risk: { penalty_rate_percent: 2.0, grace_period_days: 7 },
    high_risk: { penalty_rate_percent: 3.0, grace_period_days: 3 },
  })

  const [reminderForm, setReminderForm] = useState({
    automation_enabled: true,
    automation_interval_minutes: 15,
    low_risk: {
      auto_reminders_enabled: true,
      first_reminder_days: 3,
      reminder_interval_days: 7,
      max_reminders_before_escalation: 3,
      final_reminder_approval_required: true,
      pause_on_dispute: true,
    },
    medium_risk: {
      auto_reminders_enabled: true,
      first_reminder_days: 1,
      reminder_interval_days: 5,
      max_reminders_before_escalation: 3,
      final_reminder_approval_required: true,
      pause_on_dispute: true,
    },
    high_risk: {
      auto_reminders_enabled: true,
      first_reminder_days: 0,
      reminder_interval_days: 3,
      max_reminders_before_escalation: 2,
      final_reminder_approval_required: false,
      pause_on_dispute: false,
    },
  })

  const [bankForm, setBankForm] = useState({
    beneficiary_name: '',
    bank_name: '',
    account_number: '',
    confirm_account_number: '',
    ifsc_code: '',
    payment_instructions: '',
  })

  const [agentForm, setAgentForm] = useState({
    agent_enabled: true,
  })

  // Load existing persistent settings from backend
  useEffect(() => {
    async function loadSettings() {
      try {
        setLoading(true)
        const data = await getAdminSettings()
        if (data.penalty) {
          setPenaltyForm(data.penalty)
        }
        if (data.reminders) {
          setReminderForm(data.reminders)
        }
        if (data.bank) {
          setBankForm({
            ...data.bank,
            confirm_account_number: data.bank.account_number || '',
          })
        }
        if (data.agent) {
          setAgentForm(data.agent)
        }
      } catch (err) {
        setNotice({
          type: 'error',
          text: `Failed to load settings: ${err.message || 'Network error'}`,
        })
      } finally {
        setLoading(false)
      }
    }
    loadSettings()
  }, [])

  // Auto-dismiss notice feedback after 5 seconds
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [notice])

  const showToast = (type, text) => {
    setNotice({ type, text })
  }

  // 1. Save Penalty Rules
  const handleSavePenalty = async (e) => {
    e.preventDefault()
    try {
      setSaving(true)
      const res = await updatePenaltySettings(penaltyForm)
      showToast('success', res.message || 'Penalty and financial rules saved successfully.')
    } catch (err) {
      showToast('error', err.response?.data?.detail || err.message || 'Failed to update penalty rules.')
    } finally {
      setSaving(false)
    }
  }

  // 2. Save Reminders
  const handleSaveReminders = async (e) => {
    e.preventDefault()
    try {
      setSaving(true)
      const res = await updateReminderSettings(reminderForm)
      showToast('success', res.message || 'Reminder cadence and escalation settings saved.')
    } catch (err) {
      showToast('error', err.response?.data?.detail || err.message || 'Failed to update reminder settings.')
    } finally {
      setSaving(false)
    }
  }

  // 3. Save Bank Details
  const handleSaveBank = async (e) => {
    e.preventDefault()
    if (bankForm.account_number !== bankForm.confirm_account_number) {
      showToast('error', 'Account number and confirmation account number must match.')
      return
    }

    try {
      setSaving(true)
      const res = await updateBankSettings(bankForm)
      showToast('success', res.message || 'Bank and remittance details updated successfully.')
    } catch (err) {
      showToast('error', err.response?.data?.detail || err.message || 'Failed to update bank details.')
    } finally {
      setSaving(false)
    }
  }

  // 4. Save Agent Toggle
  const handleSaveAgent = async (e) => {
    e.preventDefault()
    try {
      setSaving(true)
      const res = await updateAgentSettings(agentForm)
      showToast('success', res.message || 'Agent master switch updated.')
    } catch (err) {
      showToast('error', err.response?.data?.detail || err.message || 'Failed to update agent settings.')
    } finally {
      setSaving(false)
    }
  }

  const sections = [
    { id: 'penalty', label: 'Penalty & Financial Rules', icon: ShieldAlert },
    { id: 'reminders', label: 'Payment Reminders & Escalation', icon: BellRing },
    { id: 'bank', label: 'Payment & Bank Details', icon: Landmark },
    { id: 'agent', label: 'Agent Settings', icon: Bot },
  ]

  const riskLabels = {
    low_risk: 'Low Risk',
    medium_risk: 'Medium Risk',
    high_risk: 'High Risk',
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-16 space-y-3">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-sm font-medium text-muted">Loading administrative configurations...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between pb-1">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="btn-secondary flex items-center gap-2 text-xs sm:text-sm font-semibold py-2 px-3.5 rounded-btn shadow-sm transition-all shrink-0"
            title="Back to Dashboard"
          >
            <ArrowLeft size={16} />
            <span>Dashboard</span>
          </button>
          <div className="h-9 w-px hidden sm:block shrink-0" style={{ background: 'var(--border)' }} />
          <div>
            <h1 className="text-lg sm:text-xl font-bold tracking-tight" style={{ color: 'var(--text)' }}>
              Admin Settings
            </h1>
            <p className="text-xs sm:text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Penalty rules, reminders cadence, bank details & agent controls
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5 self-start sm:self-auto">
          <span
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold ${
              agentForm.agent_enabled
                ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30'
                : 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30'
            }`}
          >
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                agentForm.agent_enabled ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
              }`}
            />
            {agentForm.agent_enabled ? 'Agent Active' : 'Agent Paused'}
          </span>
        </div>
      </div>

      {/* Floating Viewport Toast Notice (Always visible regardless of scroll position) */}
      {notice && (
        <div
          className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 p-4 text-sm font-semibold rounded-card border shadow-2xl animate-slideUp max-w-md ${
            notice.type === 'error'
              ? 'bg-red-500/15 border-red-500/40 text-red-600 dark:text-red-400 backdrop-blur-md'
              : 'bg-emerald-500/15 border-emerald-500/40 text-emerald-600 dark:text-emerald-400 backdrop-blur-md'
          }`}
          style={{ background: 'var(--card)' }}
        >
          {notice.type === 'error' ? (
            <AlertCircle size={20} className="shrink-0 text-danger" />
          ) : (
            <CheckCircle size={20} className="shrink-0 text-emerald-500" />
          )}
          <span className="flex-1">{notice.text}</span>
          <button
            onClick={() => setNotice(null)}
            className="opacity-60 hover:opacity-100 text-xs font-bold pl-2 cursor-pointer"
            title="Dismiss notice"
          >
            ✕
          </button>
        </div>
      )}

      {/* Section Navigation Tabs */}
      <div className="flex border-b gap-3 overflow-x-auto" style={{ borderColor: 'var(--border)' }}>
        {sections.map((sec) => {
          const Icon = sec.icon
          const active = activeSection === sec.id
          return (
            <button
              key={sec.id}
              onClick={() => setActiveSection(sec.id)}
              className={`flex items-center gap-2.5 px-5 py-3.5 text-sm font-semibold border-b-2 transition-all whitespace-nowrap ${
                active ? 'border-primary text-primary font-bold' : 'border-transparent hover:text-text'
              }`}
              style={{ color: active ? 'var(--primary)' : 'var(--text-secondary)' }}
            >
              <Icon size={18} />
              <span>{sec.label}</span>
            </button>
          )
        })}
      </div>

      {/* Tab Panels */}
      {activeSection === 'penalty' && (
        <PenaltySettingsTab
          penaltyForm={penaltyForm}
          setPenaltyForm={setPenaltyForm}
          penaltyRiskTab={penaltyRiskTab}
          setPenaltyRiskTab={setPenaltyRiskTab}
          riskLabels={riskLabels}
          handleSavePenalty={handleSavePenalty}
          saving={saving}
          notice={notice}
        />
      )}

      {activeSection === 'reminders' && (
        <RemindersSettingsTab
          reminderForm={reminderForm}
          setReminderForm={setReminderForm}
          reminderRiskTab={reminderRiskTab}
          setReminderRiskTab={setReminderRiskTab}
          riskLabels={riskLabels}
          handleSaveReminders={handleSaveReminders}
          saving={saving}
          notice={notice}
        />
      )}

      {activeSection === 'bank' && (
        <BankSettingsTab
          bankForm={bankForm}
          setBankForm={setBankForm}
          handleSaveBank={handleSaveBank}
          saving={saving}
          notice={notice}
        />
      )}

      {activeSection === 'agent' && (
        <AgentSettingsTab
          agentForm={agentForm}
          setAgentForm={setAgentForm}
          handleSaveAgent={handleSaveAgent}
          saving={saving}
          notice={notice}
        />
      )}
    </div>
  )
}

import { Bot, Save, Sparkles, CheckCircle, AlertCircle } from 'lucide-react'

/**
 * Agent Settings Tab Component
 *
 * Controls the master operational state of the AI Agent.
 * When paused, autonomous actions and conversational mutations are halted,
 * while manual record browsing, approvals, and audit safety checks remain active.
 */
export default function AgentSettingsTab({
  agentForm,
  setAgentForm,
  handleSaveAgent,
  saving,
  notice,
}) {
  return (
    <form onSubmit={handleSaveAgent} className="space-y-6">
      {/* Master AI Agent Cognitive Core */}
      <div className="card p-6 sm:p-7 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between border-b pb-5 gap-4" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-3.5">
            <div
              className={`h-12 w-12 rounded-xl flex items-center justify-center shrink-0 shadow-sm ${
                agentForm.agent_enabled
                  ? 'bg-emerald-500/15 text-emerald-500'
                  : 'bg-amber-500/15 text-amber-500'
              }`}
            >
              <Bot size={24} />
            </div>
            <div>
              <h2 className="text-base sm:text-lg font-bold" style={{ color: 'var(--text)' }}>
                Autonomous AI Agent Operation
              </h2>
              <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
                Master switch to activate or pause AI autonomous actions, reasoning, and conversational tool executions.
              </p>
            </div>
          </div>

          {/* Master Toggle Button */}
          <div className="flex items-center gap-3 self-start sm:self-auto">
            <span
              className="text-sm font-semibold"
              style={{ color: agentForm.agent_enabled ? 'var(--primary)' : 'var(--text-muted)' }}
            >
              {agentForm.agent_enabled ? 'Agent Active' : 'Agent Paused'}
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={agentForm.agent_enabled}
              onClick={() => setAgentForm({ ...agentForm, agent_enabled: !agentForm.agent_enabled })}
              className={`relative inline-flex h-8 w-14 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
                agentForm.agent_enabled ? 'bg-primary' : 'bg-gray-300 dark:bg-gray-600'
              }`}
              title={agentForm.agent_enabled ? 'Click to pause AI agent' : 'Click to activate AI agent'}
            >
              <span
                aria-hidden="true"
                className={`pointer-events-none inline-block h-7 w-7 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
                  agentForm.agent_enabled ? 'translate-x-6' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>

        <div
          className={`p-5 rounded-card border space-y-2.5 ${
            agentForm.agent_enabled
              ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-800 dark:text-emerald-300'
              : 'bg-amber-500/10 border-amber-500/20 text-amber-800 dark:text-amber-300'
          }`}
        >
          <p className="font-semibold text-sm sm:text-base flex items-center gap-2">
            <Sparkles size={16} />
            {agentForm.agent_enabled
              ? 'AI Agent is currently Active & Monitoring Receivables'
              : 'AI Agent is currently Paused by Administrator'}
          </p>
          <p className="text-sm leading-relaxed">
            {agentForm.agent_enabled
              ? 'The agent is actively evaluating portfolio risks, triggering autonomous background collection cycles, drafting intelligent reminders, and handling user requests in conversational chat.'
              : 'When paused, autonomous background cycles and chat tool executions are temporarily frozen. Manual invoice management, human approvals, statement reviews, and audit logs remain fully operational.'}
          </p>
        </div>

        <div
          className="p-4 rounded-card border text-sm leading-relaxed"
          style={{ background: 'var(--card-secondary)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
        >
          🔒 <strong className="font-semibold" style={{ color: 'var(--text)' }}>Audit & Safety Guarantee:</strong> Core GAAP/IFRS ledger immutability and financial integrity checks remain permanently enforced regardless of the AI agent toggle state.
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
          <Save size={16} /> {saving ? 'Saving State...' : 'Save Agent Setting'}
        </button>
      </div>
    </form>
  )
}

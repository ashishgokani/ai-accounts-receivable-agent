import { useState, useEffect, useRef } from 'react'
import {
  Banknote,
  Clock,
  Mail,
  Percent,
  Play,
  RotateCcw,
  Sparkles,
  Wallet,
  CheckCircle2,
  Calendar,
  Send,
  AlertCircle,
  ArrowRight,
  Timer,
  Activity,
} from 'lucide-react'
import {
  getDashboardMetrics,
  triggerAutonomousRun,
  getAutomationStatus,
  getAutomationPipeline,
  getAutomationHistory,
} from '../api/client'
import { formatISTTime } from '../utils/date'
import { formatINR } from '../utils/currency'

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [agentRunning, setAgentRunning] = useState(false)
  const [completionBanner, setCompletionBanner] = useState(null)

  // Automation Pipeline State
  const [autoStatus, setAutoStatus] = useState(null)
  const [pipeline, setPipeline] = useState([])
  const [history, setHistory] = useState([])
  const [activeAutoTab, setActiveAutoTab] = useState('PIPELINE') // 'PIPELINE' or 'HISTORY'

  // Tracking background runs to only show banner on actual completion, never on initial visit/refresh
  const initialRunLoadedRef = useRef(false)
  const prevIsRunningRef = useRef(false)

  // Real-time second countdown for next run
  const [countdown, setCountdown] = useState({ text: '--:--', seconds: 0 })
  const [actionError, setActionError] = useState(null)

  const isExecuting = agentRunning || Boolean(autoStatus?.is_running)

  // Auto-dismiss the collection cycle completion banner after 6 seconds
  useEffect(() => {
    if (completionBanner) {
      const timer = setTimeout(() => {
        setCompletionBanner(null)
      }, 6000)
      return () => clearTimeout(timer)
    }
  }, [completionBanner])

  // Monitor background run transitions to display banner ONLY when completed while on page
  useEffect(() => {
    if (!autoStatus) return

    if (!initialRunLoadedRef.current) {
      // First load: record initial state, DO NOT show banner on refresh or navigation
      initialRunLoadedRef.current = true
      prevIsRunningRef.current = Boolean(autoStatus.is_running)
      return
    }

    // If it was running and now finished
    if (prevIsRunningRef.current && !autoStatus.is_running && autoStatus.last_run_result) {
      setCompletionBanner(autoStatus.last_run_result)
    }

    prevIsRunningRef.current = Boolean(autoStatus.is_running)
  }, [autoStatus?.is_running, autoStatus?.last_run_at, autoStatus?.last_run_result])

  // Auto-dismiss operational errors after 6 seconds
  useEffect(() => {
    if (actionError) {
      const timer = setTimeout(() => {
        setActionError(null)
      }, 6000)
      return () => clearTimeout(timer)
    }
  }, [actionError])

  useEffect(() => {
    if (!autoStatus?.next_run_at || !autoStatus?.is_active) {
      setCountdown({ text: '--:--', seconds: 0 })
      return
    }

    let synced = false
    const calculateRemaining = () => {
      const targetTime = new Date(autoStatus.next_run_at).getTime()
      const now = Date.now()
      const diffSecs = Math.max(0, Math.floor((targetTime - now) / 1000))

      if (diffSecs <= 0) {
        setCountdown({ text: 'Executing...', seconds: 0 })
        if (!synced) {
          synced = true
          setTimeout(() => {
            loadData()
          }, 2500)
        }
        return
      }

      const m = Math.floor(diffSecs / 60)
      const s = diffSecs % 60
      const formatted = `${m}m ${s < 10 ? '0' : ''}${s}s`
      setCountdown({ text: formatted, seconds: diffSecs })
    }

    calculateRemaining()
    const interval = setInterval(calculateRemaining, 1000)
    return () => clearInterval(interval)
  }, [autoStatus?.next_run_at, autoStatus?.is_active])

  const loadData = async () => {
    try {
      const [resMetrics, resStatus, resPipeline, resHistory] = await Promise.all([
        getDashboardMetrics(),
        getAutomationStatus(),
        getAutomationPipeline(),
        getAutomationHistory(),
      ])
      setData(resMetrics)
      setAutoStatus(resStatus)
      setPipeline(resPipeline)
      setHistory(resHistory)
    } catch (err) {
      console.error('Failed to load dashboard metrics:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    // Periodic refresh every 30s
    const interval = setInterval(loadData, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleRunAgentNow = async () => {
    setAgentRunning(true)
    setCompletionBanner(null)
    setActionError(null)
    try {
      const res = await triggerAutonomousRun()
      setCompletionBanner(res)
      await loadData()
    } catch (err) {
      console.error('Failed to run autonomous agent:', err)
      setActionError(err.message || 'Failed to execute autonomous collection cycle.')
    } finally {
      setAgentRunning(false)
    }
  }

  const kpis = data?.kpis || {
    total_outstanding: 0,
    total_overdue: 0,
    total_collected: 0,
    collection_rate_percent: 0,
    avg_days_overdue: 0,
  }

  const counts = data?.counts || {
    paid: 0,
    pending: 0,
    overdue: 0,
    disputed: 0,
    promised: 0,
    escalated: 0,
    pending_approvals: 0,
  }

  const cards = [
    {
      label: 'Total Outstanding',
      value: formatINR(kpis.total_outstanding),
      trend: `${counts.overdue} overdue accounts`,
      icon: Wallet,
      bgColor: 'rgba(239, 68, 68, 0.1)',
      iconColor: '#EF4444',
    },
    {
      label: 'Total Collected',
      value: formatINR(kpis.total_collected),
      trend: `${counts.paid} settled invoices`,
      icon: Banknote,
      bgColor: 'rgba(34, 197, 94, 0.1)',
      iconColor: '#22C55E',
    },
    {
      label: 'Collection Recovery Rate',
      value: `${kpis.collection_rate_percent}%`,
      trend: 'Target: 90% On-time',
      icon: Percent,
      bgColor: 'rgba(37, 99, 235, 0.1)',
      iconColor: '#2563EB',
    },
    {
      label: 'Avg Overdue Aging',
      value: `${kpis.avg_days_overdue} days`,
      trend: `${kpis.penalties_accrued ? `+${formatINR(kpis.penalties_accrued)} penalty accrued` : 'No active penalty'}`,
      icon: Clock,
      bgColor: 'rgba(139, 92, 246, 0.1)',
      iconColor: '#8B5CF6',
    },
  ]

  // Priority color chips
  const priorityBadge = {
    Urgent: 'badge-risk-high',
    High: 'badge-risk-medium',
    Standard: 'badge-risk-low',
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[420px] space-y-3">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
          Loading real-time financial metrics and automation pipelines...
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Top Header Actions Bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between pb-1">
        {/* Real-Time Agent Operation & Next Run Countdown Strip */}
        <div className="flex flex-wrap items-center gap-2.5 text-xs">
          {/* Agent Live Status Pill */}
          <div
            className="flex items-center gap-2 px-3 py-1.5 rounded-full border shadow-sm transition-all"
            style={{
              background: 'var(--card)',
              borderColor: 'var(--border)',
            }}
          >
            {agentRunning ? (
              <>
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500" />
                </span>
                <span className="font-semibold text-amber-500 flex items-center gap-1.5">
                  <Sparkles size={13} className="animate-spin text-amber-500" />
                  Autonomous Agent Running...
                </span>
              </>
            ) : autoStatus?.is_active ? (
              <>
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
                </span>
                <span className="font-semibold text-emerald-600 dark:text-emerald-400 flex items-center gap-1.5">
                  AI Agent Running
                </span>
              </>
            ) : (
              <>
                <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
                <span className="font-semibold text-amber-500">
                  Agent Automation Paused
                </span>
              </>
            )}
          </div>

          {/* Real-Time Next Run Countdown Pill */}
          {autoStatus?.is_active && (
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full border shadow-sm font-medium ${
                isExecuting ? 'animate-pulse border-primary/50' : ''
              }`}
              style={{
                background: 'var(--bg-secondary)',
                borderColor: 'var(--border)',
                color: 'var(--text)',
              }}
            >
              {isExecuting ? (
                <>
                  <Sparkles size={13} className="text-primary animate-spin shrink-0" />
                  <span className="text-[11px] font-semibold text-primary">
                    Agent Executing Cycle...
                  </span>
                </>
              ) : (
                <>
                  <Timer size={13} className="text-primary shrink-0" />
                  <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    Next Run in:
                  </span>
                  <span className="font-mono font-bold text-primary tracking-tight">
                    {countdown.text}
                  </span>
                  {autoStatus?.next_run_at && (
                    <span className="text-[11px] font-normal" style={{ color: 'var(--text-muted)' }}>
                      ({formatISTTime(autoStatus.next_run_at)})
                    </span>
                  )}
                </>
              )}
            </div>
          )}

          {/* Last Agent Run Mini Badge */}
          {autoStatus && (
            <div
              className="hidden md:flex items-center gap-1.5 px-2.5 py-1.5 rounded-full border text-[11px] font-medium"
              style={{
                background: 'var(--bg-secondary)',
                borderColor: 'var(--border)',
                color: 'var(--text-muted)',
              }}
              title="Last autonomous collection run time"
            >
              <Activity size={12} className="text-emerald-500" />
              <span>
                Last Run:{' '}
                {autoStatus.last_run_at
                  ? formatISTTime(autoStatus.last_run_at)
                  : 'Not run yet'}
              </span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2.5 self-start sm:self-auto">
          <button
            className="btn-secondary flex items-center gap-1.5 text-xs font-semibold py-2 px-3.5"
            onClick={loadData}
            title="Refresh Metrics"
          >
            <RotateCcw size={14} />
            <span>Refresh</span>
          </button>

          <button
            className="btn-primary flex items-center gap-2 px-4 py-2 text-xs font-semibold shadow-sm"
            onClick={handleRunAgentNow}
            disabled={isExecuting}
          >
            {isExecuting ? (
              <>
                <Sparkles size={14} className="animate-spin text-amber-300" />
                <span>{agentRunning ? 'Running Collection Cycle...' : 'Autonomous Cycle Active...'}</span>
              </>
            ) : (
              <>
                <Play size={14} className="fill-current text-emerald-400" />
                <span>Run Agent Now</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Autonomous Execution Completion Banner (Only displayed upon actual completion) */}
      {completionBanner && (
        <div className="rounded-card border p-4 bg-primary/10 border-primary/30 flex items-start justify-between gap-3 text-xs animate-fadeIn">
          <div className="flex items-start gap-2.5">
            <CheckCircle2 size={18} className="text-primary mt-0.5 shrink-0" />
            <div>
              <p className="font-bold text-sm" style={{ color: 'var(--text)' }}>
                Collection Cycle Completed
              </p>
              <p className="mt-1" style={{ color: 'var(--text-secondary)' }}>
                {completionBanner?.summary}
              </p>
            </div>
          </div>
          <button
            className="text-xs font-semibold shrink-0 cursor-pointer text-primary hover:underline"
            onClick={() => setCompletionBanner(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Operational Error Banner (Auto-dismisses in 6s) */}
      {actionError && (
        <div className="rounded-card border p-4 bg-red-500/10 border-red-500/30 flex items-start justify-between gap-3 text-xs text-danger animate-fadeIn">
          <div className="flex items-start gap-2.5">
            <AlertCircle size={18} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-bold text-sm">Collection Run Error</p>
              <p className="mt-1">{actionError}</p>
            </div>
          </div>
          <button
            className="text-xs font-semibold shrink-0 cursor-pointer hover:underline"
            onClick={() => setActionError(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Primary KPI Cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((item) => {
          const Icon = item.icon
          return (
            <div key={item.label} className="kpi-card">
              <div className="flex items-center justify-between">
                <span className="kpi-label">{item.label}</span>
                <div
                  className="flex h-10 w-10 items-center justify-center rounded-btn"
                  style={{ background: item.bgColor, color: item.iconColor }}
                >
                  <Icon size={18} />
                </div>
              </div>
              <p className="kpi-value mt-2">{loading ? '...' : item.value}</p>
              <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>{item.trend}</p>
            </div>
          )
        })}
      </div>

      {/* Portfolio Status Breakdown Banner */}
      <div className="card p-4 sm:p-5">
        <p className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-muted)' }}>
          Portfolio Debt Categorization
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 text-xs text-center">
          <div className="p-3 rounded border" style={{ borderColor: 'var(--border)' }}>
            <p className="text-base font-bold text-success">{counts.paid}</p>
            <p style={{ color: 'var(--text-muted)' }}>Settled</p>
          </div>
          <div className="p-3 rounded border" style={{ borderColor: 'var(--border)' }}>
            <p className="text-base font-bold text-amber-500">{counts.pending}</p>
            <p style={{ color: 'var(--text-muted)' }}>Current Pending</p>
          </div>
          <div className="p-3 rounded border" style={{ borderColor: 'var(--border)' }}>
            <p className="text-base font-bold text-danger">{counts.overdue}</p>
            <p style={{ color: 'var(--text-muted)' }}>Overdue</p>
          </div>
          <div className="p-3 rounded border" style={{ borderColor: 'var(--border)' }}>
            <p className="text-base font-bold text-blue-500">{counts.promised}</p>
            <p style={{ color: 'var(--text-muted)' }}>Payment Promised</p>
          </div>
          <div className="p-3 rounded border" style={{ borderColor: 'var(--border)' }}>
            <p className="text-base font-bold text-purple-500">{counts.disputed}</p>
            <p style={{ color: 'var(--text-muted)' }}>Disputed</p>
          </div>
          <div className="p-3 rounded border" style={{ borderColor: 'var(--border)' }}>
            <p className="text-base font-bold text-orange-500">{counts.pending_approvals}</p>
            <p style={{ color: 'var(--text-muted)' }}>Pending Approvals</p>
          </div>
        </div>
      </div>

      {/* Bottom Split: Recent Execution Feed & Automation Pipeline */}
      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        {/* Left: Recent Activity Feed */}
        <section className="card p-5 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="page-section-title">Live Account Activity Feed</h2>
              <p className="page-section-sub">Auditable history of recent account actions and decisions</p>
            </div>
            <span className="badge badge-paid flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
              Live Feed
            </span>
          </div>

          <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
            {data?.recent_activities && data.recent_activities.length > 0 ? (
              data.recent_activities.map((act) => (
                <div key={act.id} className="py-3 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded bg-primary/10 text-primary">
                      <Sparkles size={14} />
                    </div>
                    <div>
                      <p className="font-semibold" style={{ color: 'var(--text)' }}>
                        {act.title}
                      </p>
                      <p style={{ color: 'var(--text-muted)' }}>{act.detail}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="badge badge-paid">{act.status}</span>
                    <p className="mt-1 text-[11px]" style={{ color: 'var(--text-muted)' }}>{act.time}</p>
                  </div>
                </div>
              ))
            ) : (
              <p className="py-6 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                No recent actions recorded. Click 'Run Agent Now' to start autonomous monitoring.
              </p>
            )}
          </div>
        </section>

        {/* Right: Automation Pipeline & Execution Schedule */}
        <section className="card p-5 sm:p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-2">
              <div>
                <h2 className="page-section-title">Automation Schedule & Tasks</h2>
                <p className="page-section-sub">
                  Next scheduled actions and communication history
                </p>
              </div>
              <span className={`badge flex items-center gap-1.5 text-[11px] ${
                autoStatus?.is_active ? 'badge-paid' : 'badge-pending'
              }`}>
                <span className={`h-1.5 w-1.5 rounded-full ${
                  autoStatus?.is_active ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
                }`} />
                {autoStatus?.is_active ? 'Active Cycle' : 'Automation Paused'}
              </span>
            </div>

            {/* Cycle Status Subheader */}
            {autoStatus && (
              <div
                className="mt-3 p-3 rounded text-xs border flex items-center justify-between"
                style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}
              >
                <div>
                  <p className="font-semibold" style={{ color: 'var(--text)' }}>
                    Recurring Cycle Interval: Every {autoStatus.interval_minutes} Minutes
                  </p>
                  <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    Next Scheduled Run:{' '}
                    {autoStatus.is_active && autoStatus.next_run_at
                      ? formatISTTime(autoStatus.next_run_at)
                      : autoStatus.is_active
                      ? 'Scheduled after interval'
                      : 'Paused in Admin Settings'}
                  </p>
                </div>
                <div className="text-right">
                  <span className="text-[11px] font-semibold text-primary">
                    Last Run:{' '}
                    {autoStatus.last_run_at
                      ? formatISTTime(autoStatus.last_run_at)
                      : 'Not run yet'}
                  </span>
                </div>
              </div>
            )}

            {/* Pipeline vs History Tabs */}
            <div className="flex border-b text-xs font-semibold mt-4 mb-3" style={{ borderColor: 'var(--border)' }}>
              <button
                onClick={() => setActiveAutoTab('PIPELINE')}
                className={`pb-2 px-3 border-b-2 flex items-center gap-1.5 transition-all ${
                  activeAutoTab === 'PIPELINE'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted'
                }`}
              >
                <Calendar size={13} />
                <span>Upcoming Tasks ({pipeline.length})</span>
              </button>
              <button
                onClick={() => setActiveAutoTab('HISTORY')}
                className={`pb-2 px-3 border-b-2 flex items-center gap-1.5 transition-all ${
                  activeAutoTab === 'HISTORY'
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted'
                }`}
              >
                <Mail size={13} />
                <span>Sent Reminders ({history.length})</span>
              </button>
            </div>

            {/* Tab 1: Upcoming Tasks Pipeline */}
            {activeAutoTab === 'PIPELINE' && (
              <div className="space-y-2.5 max-h-[300px] overflow-y-auto pr-1">
                {pipeline.length === 0 ? (
                  <p className="py-6 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                    All accounts up to date. No pending actions in queue.
                  </p>
                ) : (
                  pipeline.map((item) => (
                    <div
                      key={item.id}
                      className="p-3 rounded border text-xs flex items-center justify-between"
                      style={{ borderColor: 'var(--border)', background: 'var(--card-secondary)' }}
                    >
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="font-bold" style={{ color: 'var(--text)' }}>
                            {item.invoice_number} · {item.company_name}
                          </span>
                          <span className={`badge ${priorityBadge[item.priority] || 'badge-risk-low'}`}>
                            {item.priority}
                          </span>
                        </div>
                        <p style={{ color: 'var(--text-secondary)' }}>
                          {item.planned_action}
                        </p>
                        <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                          Balance: {formatINR(item.amount)} · {item.days_overdue} days overdue
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <span className="text-[11px] font-semibold text-primary">
                          {formatISTTime(item.scheduled_for)}
                        </span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}

            {/* Tab 2: Sent Reminders & Communications History */}
            {activeAutoTab === 'HISTORY' && (
              <div className="space-y-2.5 max-h-[300px] overflow-y-auto pr-1">
                {history.length === 0 ? (
                  <p className="py-6 text-center text-xs" style={{ color: 'var(--text-muted)' }}>
                    No automated emails dispatched yet.
                  </p>
                ) : (
                  history.map((hist) => (
                    <div
                      key={hist.id}
                      className="p-3 rounded border text-xs space-y-1"
                      style={{ borderColor: 'var(--border)', background: 'var(--card-secondary)' }}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-primary">{hist.company_name}</span>
                        <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                          {formatISTTime(hist.executed_at)}
                        </span>
                      </div>
                      <p className="font-semibold truncate" style={{ color: 'var(--text)' }}>
                        {hist.subject}
                      </p>
                      <p className="text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>
                        To: {hist.recipient_email} · Status: Delivered
                      </p>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

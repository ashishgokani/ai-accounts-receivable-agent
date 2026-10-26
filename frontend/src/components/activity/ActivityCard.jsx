import React, { useState } from 'react'
import {
  Sparkles,
  Clock,
  ChevronDown,
  ChevronRight,
  Code,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ShieldAlert,
  FileText,
  Mail,
  Building2,
  CreditCard,
  Layers,
  ArrowRight,
} from 'lucide-react'
import { formatISTDateTime } from '../../utils/date'
import { formatINR } from '../../utils/currency'

/**
 * Human-friendly label formatter for raw technical keys.
 */
function formatKey(key) {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

/**
 * Human-friendly value formatter for complex or raw values with containment.
 */
function renderValue(val, key = '') {
  if (val === null || val === undefined) return <span className="opacity-50">—</span>
  if (typeof val === 'boolean') {
    return val ? (
      <span className="inline-flex items-center gap-1 text-emerald-600 font-semibold">
        <CheckCircle2 size={12} /> Yes / Passed
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 text-red-500 font-semibold">
        <XCircle size={12} /> No / Failed
      </span>
    )
  }
  if (typeof val === 'number') {
    if (key.toLowerCase().includes('amount') || key.toLowerCase().includes('balance') || key.toLowerCase().includes('penalty')) {
      return <span className="font-bold text-primary">{formatINR(val)}</span>
    }
    if (key.toLowerCase().includes('rate') || key.toLowerCase().includes('percent')) {
      return <span className="font-semibold">{val}%</span>
    }
    return <span className="font-mono">{val}</span>
  }
  if (Array.isArray(val)) {
    if (val.length === 0) return <span className="opacity-50">Empty</span>
    return (
      <div className="flex flex-wrap gap-1 mt-1 max-w-full">
        {val.map((item, idx) => (
          <span key={idx} className="px-2 py-0.5 rounded text-[11px] bg-secondary border break-all max-w-full" style={{ borderColor: 'var(--border)' }}>
            {typeof item === 'object' ? JSON.stringify(item) : String(item)}
          </span>
        ))}
      </div>
    )
  }
  if (typeof val === 'object') {
    return (
      <div className="mt-1 p-2 rounded text-[11px] bg-secondary border space-y-1 max-w-full overflow-hidden" style={{ borderColor: 'var(--border)' }}>
        {Object.entries(val).map(([k, v]) => (
          <div key={k} className="flex flex-wrap gap-1 min-w-0 max-w-full">
            <span className="font-semibold opacity-75 shrink-0">{formatKey(k)}:</span>
            <span className="break-all">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
          </div>
        ))}
      </div>
    )
  }
  return <span className="break-all max-w-full">{String(val)}</span>
}

const statusBadgeConfig = {
  SUCCESS: { label: 'Completed Successfully', icon: CheckCircle2, className: 'badge-paid text-emerald-600 bg-emerald-500/10 border border-emerald-500/20' },
  PENDING_APPROVAL: { label: 'Held for Manager Approval', icon: ShieldAlert, className: 'badge-pending text-amber-600 bg-amber-500/10 border border-amber-500/20' },
  BLOCKED_BY_GUARDRAIL: { label: 'Blocked by Policy Guardrail', icon: AlertTriangle, className: 'badge-overdue text-red-600 bg-red-500/10 border border-red-500/20' },
  ERROR: { label: 'Execution Error', icon: XCircle, className: 'badge-overdue text-red-600 bg-red-500/10 border border-red-500/20' },
}

/**
 * ActivityCard Component.
 * Presents complex AI tool decisions and database operations in an intuitive,
 * human-readable business view without overflowing card bounds.
 */
export default function ActivityCard({ act, isExpanded, onToggle }) {
  const [showRawJson, setShowRawJson] = useState(false)

  const statusConfig = statusBadgeConfig[act.status] || {
    label: act.status.replace(/_/g, ' '),
    icon: Sparkles,
    className: 'badge-secondary',
  }
  const StatusIcon = statusConfig.icon

  // Extract key contextual business entities for top summary
  const input = act.input_data || {}
  const output = act.output_data || {}

  const invoiceId = input.invoice_id || output.invoice_id
  const customerName = input.customer_name || input.company_name || output.company_name
  const amount = input.amount || output.amount || output.total_amount
  const recipient = input.recipient || output.recipient_email || output.recipient
  const reason = input.reason || output.reason || output.message

  return (
    <div
      className="rounded-card border transition-all overflow-hidden max-w-full"
      style={{ borderColor: 'var(--border)', background: 'var(--card)' }}
    >
      {/* Clickable Header Bar */}
      <div
        className="p-4 flex flex-wrap items-center justify-between gap-3 cursor-pointer hover:bg-black/[0.02] dark:hover:bg-white/[0.02]"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3 min-w-0 max-w-full">
          <div className="flex h-9 w-9 items-center justify-center rounded-btn bg-primary/10 text-primary shrink-0">
            <Sparkles size={16} />
          </div>
          <div className="min-w-0 max-w-full">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-bold text-sm leading-tight truncate" style={{ color: 'var(--text)' }}>
                {act.action_type.replace(/_/g, ' ')}
              </h3>
              {act.tool_name && (
                <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-primary/10 text-primary border border-primary/20 truncate">
                  Tool: {act.tool_name.replace(/_/g, ' ')}
                </span>
              )}
            </div>

            {/* Entity chips row */}
            <div className="flex flex-wrap items-center gap-2 mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>
              {invoiceId && (
                <span className="inline-flex items-center gap-1 font-semibold text-primary">
                  <FileText size={12} /> {invoiceId}
                </span>
              )}
              {customerName && (
                <span className="inline-flex items-center gap-1 font-medium truncate max-w-[200px]" style={{ color: 'var(--text)' }}>
                  <Building2 size={12} className="shrink-0" /> {customerName}
                </span>
              )}
              {amount && (
                <span className="font-semibold text-danger">
                  {formatINR(amount)}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 ml-auto shrink-0">
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-semibold ${statusConfig.className}`}>
            <StatusIcon size={13} />
            <span>{statusConfig.label}</span>
          </span>

          <div className="flex items-center gap-1.5 text-xs text-muted hidden sm:flex">
            <Clock size={13} />
            <span>{formatISTDateTime(act.created_at)}</span>
          </div>

          <button
            className="icon-btn h-7 w-7 shrink-0"
            aria-label={isExpanded ? 'Collapse activity' : 'Expand activity'}
          >
            {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
          </button>
        </div>
      </div>

      {/* Expanded Non-Technical Detail Panel */}
      {isExpanded && (
        <div className="p-4 sm:p-5 border-t space-y-4 text-xs max-w-full overflow-hidden" style={{ borderColor: 'var(--border)', background: 'var(--bg-secondary)' }}>
          {/* Natural Language Explanation Banner */}
          {reason && (
            <div
              className="p-3 rounded border text-xs flex items-start gap-2.5 max-w-full overflow-hidden"
              style={{ background: 'var(--card)', borderColor: 'var(--border)' }}
            >
              <FileText size={15} className="text-primary mt-0.5 shrink-0" />
              <div className="min-w-0 flex-1 overflow-hidden">
                <p className="font-bold text-xs" style={{ color: 'var(--text)' }}>
                  Operational Trigger & Summary:
                </p>
                <p className="mt-0.5 leading-relaxed break-words overflow-hidden" style={{ color: 'var(--text-secondary)' }}>
                  {reason}
                </p>
              </div>
            </div>
          )}

          {/* Structured Parameters Grid (Input Data) */}
          {input && Object.keys(input).length > 0 && (
            <div className="space-y-2 max-w-full overflow-hidden">
              <h4 className="text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                <Layers size={13} />
                <span>Action Parameters & Context</span>
              </h4>
              <div
                className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 p-3.5 rounded border max-w-full overflow-hidden"
                style={{ background: 'var(--card)', borderColor: 'var(--border)' }}
              >
                {Object.entries(input).map(([key, value]) => (
                  <div key={key} className="space-y-0.5 min-w-0 overflow-hidden">
                    <p className="text-[11px] font-semibold truncate" style={{ color: 'var(--text-muted)' }}>
                      {formatKey(key)}
                    </p>
                    <div className="text-xs font-medium break-words overflow-hidden" style={{ color: 'var(--text)' }}>
                      {renderValue(value, key)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Verified Business Outcome (Output Data) */}
          {output && Object.keys(output).length > 0 && (
            <div className="space-y-2 max-w-full overflow-hidden">
              <h4 className="text-[11px] font-bold uppercase tracking-wider flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 size={13} />
                <span>Verified System Outcome</span>
              </h4>
              <div
                className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 p-3.5 rounded border bg-emerald-500/[0.04] border-emerald-500/20 max-w-full overflow-hidden"
              >
                {Object.entries(output).map(([key, value]) => (
                  <div key={key} className="space-y-0.5 min-w-0 overflow-hidden">
                    <p className="text-[11px] font-semibold opacity-75 truncate" style={{ color: 'var(--text-muted)' }}>
                      {formatKey(key)}
                    </p>
                    <div className="text-xs font-semibold break-words overflow-hidden" style={{ color: 'var(--text)' }}>
                      {renderValue(value, key)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Developer Raw JSON Collapsible Toggle */}
          <div className="pt-2 border-t flex flex-col items-start gap-2 max-w-full overflow-hidden" style={{ borderColor: 'var(--border)' }}>
            <button
              type="button"
              onClick={() => setShowRawJson(!showRawJson)}
              className="text-[11px] font-semibold flex items-center gap-1.5 py-1 px-2.5 rounded border transition-colors hover:bg-black/5 dark:hover:bg-white/5"
              style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}
            >
              <Code size={12} />
              <span>{showRawJson ? 'Hide Technical JSON' : 'View Technical JSON (Developer Mode)'}</span>
            </button>

            {showRawJson && (
              <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 max-w-full overflow-hidden">
                <div className="min-w-0 overflow-hidden">
                  <p className="text-[11px] font-bold mb-1 truncate" style={{ color: 'var(--text-muted)' }}>Raw Input Payload:</p>
                  <pre
                    className="p-3 rounded text-[11px] font-mono overflow-x-auto max-w-full whitespace-pre-wrap break-all border leading-relaxed"
                    style={{ background: 'var(--card)', borderColor: 'var(--border)', color: 'var(--text)' }}
                  >
                    {JSON.stringify(input, null, 2)}
                  </pre>
                </div>
                <div className="min-w-0 overflow-hidden">
                  <p className="text-[11px] font-bold mb-1 text-emerald-600 truncate">Raw Output Verification:</p>
                  <pre
                    className="p-3 rounded text-[11px] font-mono overflow-x-auto max-w-full whitespace-pre-wrap break-all border leading-relaxed text-emerald-600 dark:text-emerald-400"
                    style={{ background: 'var(--card)', borderColor: 'var(--border)' }}
                  >
                    {JSON.stringify(output, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

import React from 'react'
import {
  ChevronDown,
  ChevronRight,
  Lightbulb,
  Sparkles,
  CheckCircle2,
} from 'lucide-react'
import MarkdownRenderer from './MarkdownRenderer'
import { formatISTTime } from '../utils/date'

/**
 * ChatMessageItem Component.
 * Renders individual user and AI chat bubbles with live real-time
 * thought streaming, tool execution status pills, and rich Markdown tables.
 */
export default function ChatMessageItem({
  msg,
  isThoughtOpen,
  onToggleThought,
}) {
  const isAi = msg.role === 'ai'
  const isStreaming = Boolean(msg.isStreaming || msg.is_streaming)
  const streamingStatus = msg.streamingStatus || msg.streaming_status

  return (
    <div className={`flex ${isAi ? 'justify-start' : 'justify-end'}`}>
      <div className={`max-w-[90%] sm:max-w-[85%] ${isAi ? 'chat-bubble-ai' : 'chat-bubble-user'}`}>
        {/* ================= THOUGHT PROCESS DRAWER ================= */}
        {isAi && (msg.reasoning || isStreaming || (msg.actions_taken && msg.actions_taken.length > 0)) && (
          <div className="mb-3">
            <button
              type="button"
              onClick={() => onToggleThought(msg.message_id)}
              className="flex items-center gap-1.5 text-[11px] font-medium py-1 px-2 rounded hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              {isThoughtOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              <Lightbulb
                size={12}
                className={isStreaming ? 'text-amber-500 animate-pulse' : 'text-amber-500'}
              />
              <span>
                {isStreaming ? (
                  <span className="text-amber-500 font-semibold flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-ping" />
                    Thinking in real time...
                  </span>
                ) : (
                  `Thought process · Generated in ${msg.execution_seconds || 1.1}s`
                )}
              </span>
            </button>

            {/* Collapsible Content */}
            {isThoughtOpen && (
              <div
                className="mt-2 p-3 rounded text-[11px] leading-relaxed border space-y-2 animate-fadeIn"
                style={{
                  background: 'rgba(0, 0, 0, 0.03)',
                  borderColor: isStreaming ? 'rgba(245, 158, 11, 0.3)' : 'var(--border)',
                  color: 'var(--text-secondary)',
                }}
              >
                <div>
                  <p className="font-semibold text-[10px] uppercase tracking-wider text-muted flex items-center justify-between">
                    <span>Internal Analysis & Policy Verification</span>
                    {isStreaming && (
                      <span className="text-[9.5px] text-amber-500 font-mono animate-pulse">
                        LIVE STREAM
                      </span>
                    )}
                  </p>
                  <p className="whitespace-pre-line italic opacity-95 mt-1 font-mono text-[11px] leading-relaxed">
                    {msg.reasoning || (isStreaming ? 'Evaluating policy rules and debtor accounts...' : '')}
                  </p>
                </div>

                {/* Live Tool Execution Status Pill */}
                {isStreaming && streamingStatus && (
                  <div className="pt-2 border-t flex items-center gap-2 text-[11px] text-primary font-medium animate-pulse">
                    <Sparkles size={12} className="animate-spin text-primary" />
                    <span>{streamingStatus}</span>
                  </div>
                )}

                {/* Completed Actions Ledger */}
                {msg.actions_taken && msg.actions_taken.length > 0 && (
                  <div className="pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                    <p className="font-semibold text-[10px] uppercase tracking-wider text-muted mb-1 flex items-center gap-1">
                      <CheckCircle2 size={11} className="text-emerald-500" /> System Actions
                    </p>
                    <div className="space-y-0.5">
                      {msg.actions_taken.map((act, idx) => (
                        <p key={idx} className="opacity-80 font-mono text-[10.5px]">
                          • {act}
                        </p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ================= MAIN MESSAGE CONTENT ================= */}
        {isAi ? (
          <div>
            <MarkdownRenderer content={msg.content} />
            {isStreaming && (
              <span className="inline-block w-1.5 h-3.5 bg-primary ml-1 animate-pulse align-middle rounded-sm" />
            )}
          </div>
        ) : (
          <div className="whitespace-pre-line text-xs sm:text-sm leading-relaxed">
            {msg.content}
          </div>
        )}

        {/* IST Timestamp */}
        {msg.created_at && (
          <div className={`text-[9.5px] mt-1 opacity-60 font-mono ${isAi ? 'text-left' : 'text-right'}`}>
            {formatISTTime(msg.created_at)}
          </div>
        )}
      </div>
    </div>
  )
}

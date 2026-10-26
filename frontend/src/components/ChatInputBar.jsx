import React from 'react'
import { Send, AlertTriangle } from 'lucide-react'

/**
 * ChatInputBar Component.
 * Encapsulates the prompt textarea, character length validator,
 * credit quota warnings, and dispatch action controls.
 */
export default function ChatInputBar({
  draft,
  setDraft,
  onSend,
  loading,
  chatConfig,
  dailyCreditsLeft,
  sessionCreditsLeft,
  onNewChat,
  textareaRef,
}) {
  const isDailyExhausted = dailyCreditsLeft <= 0
  const isSessionExhausted = sessionCreditsLeft <= 0
  const quotaExhausted = isDailyExhausted || isSessionExhausted
  const isLimitReached = draft.length >= chatConfig.max_chars

  let lowCreditWarning = null
  if (!quotaExhausted) {
    if (sessionCreditsLeft <= 2 && sessionCreditsLeft <= dailyCreditsLeft) {
      lowCreditWarning = `Only ${sessionCreditsLeft} ${sessionCreditsLeft === 1 ? 'credit' : 'credits'} left for this chat.`
    } else if (dailyCreditsLeft <= 2 && dailyCreditsLeft < sessionCreditsLeft) {
      lowCreditWarning = `Only ${dailyCreditsLeft} ${dailyCreditsLeft === 1 ? 'credit is' : 'credits are'} left out of your daily limit (resets at midnight).`
    }
  }

  const placeholderText = isDailyExhausted
    ? 'Your daily message limit is over. It will reset at 12:00 midnight.'
    : isSessionExhausted
    ? "Message limit reached for this chat. Click '+ New Chat' to continue..."
    : 'Ask about overdue balances, instruct custom emails, or inspect customer credit ratings...'

  return (
    <div>
      {/* Daily Limit Over Banner (Priority 1) */}
      {isDailyExhausted && (
        <div className="mx-4 mt-2 px-3 py-2 rounded text-[11px] bg-red-500/10 border border-red-500/20 text-red-500 flex items-center gap-1.5">
          <AlertTriangle size={13} className="shrink-0" />
          <span>Your daily message limit is over. It will reset at 12:00 midnight.</span>
        </div>
      )}

      {/* Session Limit Over Banner (Priority 2, only if daily credits remain) */}
      {!isDailyExhausted && isSessionExhausted && (
        <div className="mx-4 mt-2 px-3 py-2 rounded text-[11px] bg-amber-500/10 border border-amber-500/20 text-amber-500 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <AlertTriangle size={13} className="shrink-0" />
            <span>Message limit reached for this chat. Please start a new chat to continue.</span>
          </div>
          <button
            type="button"
            onClick={onNewChat}
            className="px-2.5 py-1 text-[11px] font-medium rounded bg-amber-500 text-black hover:bg-amber-400 transition-colors shrink-0"
          >
            + New Chat
          </button>
        </div>
      )}

      {/* Character Warning Banner */}
      {isLimitReached && (
        <div className="mx-4 mt-2 px-3 py-1.5 rounded text-[11px] bg-red-500/10 border border-red-500/20 text-red-500 flex items-center gap-1.5">
          <AlertTriangle size={13} />
          <span>Maximum message limit of {chatConfig.max_chars} characters reached. Additional characters prevented.</span>
        </div>
      )}

      {/* Input Box Controls */}
      <div className="p-3 sm:p-4 border-t" style={{ borderColor: 'var(--border)', background: 'var(--card)' }}>
        <div className="flex items-center justify-between text-[11px] mb-2 px-1 min-h-[16px]">
          {lowCreditWarning ? (
            <div className="flex items-center gap-1.5 text-amber-500 font-medium">
              <AlertTriangle size={12} className="shrink-0" />
              <span>{lowCreditWarning}</span>
            </div>
          ) : (
            <div />
          )}
          <div className={`font-mono text-[11px] ${draft.length > chatConfig.max_chars * 0.9 ? 'text-red-500 font-bold' : 'text-muted'}`}>
            {draft.length} / {chatConfig.max_chars} chars
          </div>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSend()
          }}
          className="flex items-end gap-2"
        >
          <textarea
            ref={textareaRef}
            value={draft}
            disabled={quotaExhausted}
            onChange={(e) => {
              if (e.target.value.length <= chatConfig.max_chars) {
                setDraft(e.target.value)
              }
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                onSend()
              }
            }}
            maxLength={chatConfig.max_chars}
            placeholder={placeholderText}
            rows={2}
            className="flex-1 p-2.5 text-xs sm:text-sm rounded border resize-none focus:outline-none focus:border-primary disabled:opacity-60 disabled:cursor-not-allowed"
            style={{
              background: 'var(--bg-secondary)',
              borderColor: isLimitReached || quotaExhausted ? '#EF4444' : 'var(--border)',
              color: 'var(--text)',
            }}
          />
          <button
            type="submit"
            disabled={loading || !draft.trim() || isLimitReached || quotaExhausted}
            className="btn-primary h-10 px-4 flex items-center justify-center shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send size={15} />
          </button>
        </form>
      </div>
    </div>
  )
}

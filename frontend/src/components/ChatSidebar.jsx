import React, { useState, useEffect } from 'react'
import { Plus, MessageSquare, Trash2, Pencil, Check, X, Search, Sparkles, User } from 'lucide-react'
import { searchChatHistory } from '../api/client'

/**
 * ChatSidebar Component.
 * Scrollable list of prior AI sessions with smart auto-generated titles,
 * full-text search across all prompts and AI replies, inline renaming, deletion,
 * and new chat creation.
 */
export default function ChatSidebar({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewChat,
  onDeleteSession,
  onRenameSession,
}) {
  const [editingSessionId, setEditingSessionId] = useState(null)
  const [editingTitle, setEditingTitle] = useState('')

  // Search across all chat history (prompts & AI responses)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([])
      setSearching(false)
      return
    }

    const timer = setTimeout(async () => {
      setSearching(true)
      try {
        const res = await searchChatHistory(searchQuery)
        setSearchResults(res || [])
      } catch (err) {
        console.error('Failed to search chat history:', err)
      } finally {
        setSearching(false)
      }
    }, 250)

    return () => clearTimeout(timer)
  }, [searchQuery])

  const handleStartRename = (e, sess) => {
    e.stopPropagation()
    setEditingSessionId(sess.session_id)
    setEditingTitle(sess.title)
  }

  const handleSaveRename = async (e, sessionId) => {
    e.stopPropagation()
    const trimmed = editingTitle.trim()
    if (!trimmed) {
      setEditingSessionId(null)
      return
    }
    await onRenameSession(sessionId, trimmed)
    setEditingSessionId(null)
  }

  const handleCancelRename = (e) => {
    e.stopPropagation()
    setEditingSessionId(null)
    setEditingTitle('')
  }

  const isSearchingActive = searchQuery.trim().length > 0

  return (
    <aside
      className="border-r flex flex-col p-3 space-y-3 h-full min-h-0 overflow-hidden"
      style={{ borderColor: 'var(--border)', background: 'var(--card-secondary)' }}
    >
      {/* New Chat Button */}
      <button
        onClick={onNewChat}
        className="w-full shrink-0 flex items-center justify-center gap-2 py-2 px-3 rounded-btn border text-xs font-semibold shadow-sm transition-all hover:bg-black/5 dark:hover:bg-white/5"
        style={{
          borderColor: 'var(--border)',
          background: 'var(--card)',
          color: 'var(--text)',
        }}
      >
        <Plus size={15} className="text-primary" />
        <span>New Chat</span>
      </button>

      {/* Search Input across Chat History */}
      <div className="relative shrink-0">
        <Search size={14} className="absolute left-2.5 top-2.5 text-muted pointer-events-none" />
        <input
          type="text"
          placeholder="Search all chats & replies..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full text-xs pl-8 pr-7 py-2 rounded border bg-transparent focus:outline-none focus:border-primary transition-colors"
          style={{
            borderColor: 'var(--border)',
            color: 'var(--text)',
            background: 'var(--card)',
          }}
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute right-2 top-2 p-0.5 text-muted hover:text-text rounded"
            title="Clear search"
          >
            <X size={13} />
          </button>
        )}
      </div>

      {/* Conversations List with Scrollbar */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-1.5 pr-1 scroll-smooth">
        <div className="flex items-center justify-between px-2 pt-1 pb-0.5 shrink-0">
          <p
            className="text-[11px] font-semibold uppercase tracking-wider"
            style={{ color: 'var(--text-muted)' }}
          >
            {isSearchingActive ? `Search Matches (${searchResults.length})` : 'Recent Chats'}
          </p>
          {searching && (
            <div className="h-3 w-3 animate-spin rounded-full border border-primary border-t-transparent" />
          )}
        </div>

        {/* SEARCH RESULTS VIEW */}
        {isSearchingActive ? (
          searchResults.length === 0 && !searching ? (
            <div className="p-4 text-center text-xs space-y-1" style={{ color: 'var(--text-muted)' }}>
              <p className="font-medium">No messages found</p>
              <p className="text-[11px]">No prompts or AI replies match "{searchQuery}".</p>
            </div>
          ) : (
            searchResults.map((res) => {
              const isActive = res.session_id === activeSessionId
              return (
                <div
                  key={res.session_id}
                  onClick={() => onSelectSession(res.session_id)}
                  className={`p-2.5 rounded text-xs cursor-pointer border transition-all space-y-1.5 ${
                    isActive ? 'border-primary shadow-sm' : 'hover:bg-black/5 dark:hover:bg-white/5'
                  }`}
                  style={{
                    background: isActive ? 'var(--card)' : 'transparent',
                    borderColor: isActive ? 'var(--primary)' : 'var(--border)',
                  }}
                >
                  <div className="flex items-center gap-1.5 font-bold" style={{ color: 'var(--text)' }}>
                    <MessageSquare size={13} className="text-primary shrink-0" />
                    <span className="truncate">{res.title}</span>
                  </div>

                  {res.matches?.slice(0, 2).map((m, mIdx) => (
                    <div
                      key={m.message_id || mIdx}
                      className="text-[11px] p-1.5 rounded flex items-start gap-1.5"
                      style={{ background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}
                    >
                      {m.role === 'user' ? (
                        <User size={12} className="text-primary mt-0.5 shrink-0" />
                      ) : (
                        <Sparkles size={12} className="text-amber-500 mt-0.5 shrink-0" />
                      )}
                      <p className="line-clamp-2 leading-relaxed">
                        <span className="font-semibold" style={{ color: 'var(--text)' }}>
                          {m.role === 'user' ? 'Prompt: ' : 'AI: '}
                        </span>
                        {m.snippet}
                      </p>
                    </div>
                  ))}
                </div>
              )
            })
          )
        ) : sessions.length === 0 ? (
          <p className="text-xs p-3 text-center" style={{ color: 'var(--text-muted)' }}>
            No prior conversations found.
          </p>
        ) : (
          sessions.map((sess) => {
            const isActive = sess.session_id === activeSessionId
            const isEditing = editingSessionId === sess.session_id

            if (isEditing) {
              return (
                <div
                  key={sess.session_id}
                  className="p-1.5 rounded flex items-center gap-1 border"
                  style={{
                    background: 'var(--card)',
                    borderColor: 'var(--primary)',
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <input
                    type="text"
                    value={editingTitle}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveRename(e, sess.session_id)
                      if (e.key === 'Escape') handleCancelRename(e)
                    }}
                    autoFocus
                    className="flex-1 text-xs px-1.5 py-1 rounded bg-transparent focus:outline-none"
                    style={{ color: 'var(--text)' }}
                  />
                  <button
                    onClick={(e) => handleSaveRename(e, sess.session_id)}
                    className="p-1 text-emerald-500 hover:bg-emerald-500/10 rounded"
                    title="Save title"
                  >
                    <Check size={13} />
                  </button>
                  <button
                    onClick={handleCancelRename}
                    className="p-1 text-muted hover:bg-black/5 rounded"
                    title="Cancel"
                  >
                    <X size={13} />
                  </button>
                </div>
              )
            }

            return (
              <div
                key={sess.session_id}
                onClick={() => onSelectSession(sess.session_id)}
                className={`group flex items-center justify-between p-2.5 rounded text-xs cursor-pointer transition-all ${
                  isActive
                    ? 'font-bold shadow-sm'
                    : 'hover:bg-black/5 dark:hover:bg-white/5 opacity-80'
                }`}
                style={{
                  background: isActive ? 'var(--card)' : 'transparent',
                  color: 'var(--text)',
                  border: isActive ? '1px solid var(--border)' : '1px solid transparent',
                }}
              >
                <div className="flex items-center gap-2 truncate flex-1 mr-1">
                  <MessageSquare size={13} className={isActive ? 'text-primary' : 'text-muted'} />
                  <span className="truncate">{sess.title}</span>
                </div>

                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={(e) => handleStartRename(e, sess)}
                    className="p-1 hover:text-primary transition-colors rounded"
                    title="Rename conversation"
                  >
                    <Pencil size={12} />
                  </button>
                  <button
                    onClick={(e) => onDeleteSession(e, sess.session_id)}
                    className="p-1 hover:text-danger transition-colors rounded"
                    title="Delete conversation"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            )
          })
        )}
      </div>
    </aside>
  )
}

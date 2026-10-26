import { useState, useRef, useEffect } from 'react'
import {
  streamChatMessage,
  getChatSessions,
  createChatSession,
  getSessionMessages,
  getActiveSessionTurn,
  deleteChatSession,
  renameChatSession,
  getChatConfig,
} from '../api/client'
import ChatSidebar from '../components/ChatSidebar'
import ChatMessageItem from '../components/ChatMessageItem'
import ChatInputBar from '../components/ChatInputBar'

const WELCOME_MESSAGE_TEXT =
  'Hello! I am your Autonomous Accounts Receivable Intelligence Assistant.\n\nYou can ask me to monitor overdue accounts, check customer risk ratings, dispatch custom emails, or audit debtor records with live real-time reasoning.'

const buildWelcomeMessage = (sessionId) => ({
  message_id: `welcome-${sessionId || 'default'}`,
  session_id: sessionId,
  role: 'ai',
  content: WELCOME_MESSAGE_TEXT,
  reasoning: 'System initialized with live PostgreSQL database and corporate credit control policies.',
  execution_seconds: 0.1,
  actions_taken: [],
  tool_calls: [],
  created_at: new Date().toISOString(),
})

export default function AgentChat() {
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [expandedThoughtIds, setExpandedThoughtIds] = useState(new Set())
  const [chatConfig, setChatConfig] = useState({
    max_history_turns: 10, max_chars: 1000, daily_credits: 50, session_credits: 15, model_name: 'Amazon Nova Pro',
  })
  const [creditsLeft, setCreditsLeft] = useState(15)
  const [dailyCreditsLeft, setDailyCreditsLeft] = useState(50)
  const [sessionCreditsLeft, setSessionCreditsLeft] = useState(15)

  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)
  const activeSessionIdRef = useRef(null)
  const pollingIntervalRef = useRef(null)
  const activeTurnsRef = useRef({})

  useEffect(() => { activeSessionIdRef.current = activeSessionId }, [activeSessionId])
  useEffect(() => () => { if (pollingIntervalRef.current) clearInterval(pollingIntervalRef.current) }, [])

  // 1. Initial Load: Load config and sessions
  useEffect(() => {
    async function init() {
      try {
        setInitialLoading(true)
        const sessList = await getChatSessions()
        setSessions(sessList)

        // Restore previously viewed session from localStorage if available
        const savedSessionId = localStorage.getItem('receiviq_active_chat_session_id')
        const initialSessionId =
          savedSessionId && sessList.some((s) => s.session_id === savedSessionId)
            ? savedSessionId
            : sessList && sessList.length > 0
            ? sessList[0].session_id
            : null

        const config = await getChatConfig(initialSessionId)
        setChatConfig(config)
        setDailyCreditsLeft(config.daily_credits_left ?? config.daily_credits)
        setSessionCreditsLeft(config.session_credits_left ?? config.session_credits)
        setCreditsLeft(config.credits_left ?? Math.min(config.daily_credits_left ?? 50, config.session_credits_left ?? 15))

        if (initialSessionId) {
          selectSession(initialSessionId, config)
        } else {
          handleNewChat()
        }
      } catch (err) {
        console.error('Failed to initialize chat interface:', err)
      } finally {
        setInitialLoading(false)
      }
    }
    init()
  }, [])

  // 2. Scroll to bottom on message updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // 3. Tab Visibility Listener: Re-sync state when user returns to this browser tab
  useEffect(() => {
    const handleVisibilityChange = async () => {
      if (document.visibilityState === 'visible' && activeSessionIdRef.current) {
        const sid = activeSessionIdRef.current
        try {
          const turn = await getActiveSessionTurn(sid)
          if (turn && turn.is_active) {
            // Re-attach active turn tracking so reasoning and content stay live
            selectSession(sid)
          } else {
            const freshMsgs = await getSessionMessages(sid)
            processAndSetMessages(freshMsgs, sid)
            setLoading(false)
            const updatedList = await getChatSessions()
            setSessions(updatedList)
          }
        } catch (e) {
          console.error('Error re-syncing session on tab focus:', e)
        }
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [])

  // Helper to format messages with welcome banner
  const processAndSetMessages = (msgs, sessionId) => {
    if (!msgs || msgs.length === 0) {
      setMessages([buildWelcomeMessage(sessionId)])
      return
    }
    const welcome = msgs.find(
      (m) => m.content && m.content.includes('Autonomous Accounts Receivable Intelligence Assistant')
    )
    const nonWelcome = msgs.filter(
      (m) => !m.content || !m.content.includes('Autonomous Accounts Receivable Intelligence Assistant')
    )
    setMessages([welcome || buildWelcomeMessage(sessionId), ...nonWelcome])
  }

  // 4. Select Session & load messages + resume active turn if still running
  const selectSession = async (sessionId, existingConfig = null) => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }

    setActiveSessionId(sessionId)
    activeSessionIdRef.current = sessionId
    try {
      localStorage.setItem('receiviq_active_chat_session_id', sessionId)
    } catch (e) {}

    try {
      const msgs = await getSessionMessages(sessionId)
      processAndSetMessages(msgs, sessionId)

      const lastMsg = msgs && msgs.length > 0 ? msgs[msgs.length - 1] : null
      const isRunningOnServer = lastMsg && lastMsg.is_streaming === true
      const isRunningLocally = activeTurnsRef.current[sessionId] && !activeTurnsRef.current[sessionId].done

      if (isRunningOnServer || isRunningLocally) {
        setLoading(true)
        if (lastMsg) {
          setExpandedThoughtIds((prev) => new Set(prev).add(lastMsg.message_id))
        }

        // Start background polling to keep thoughts and status live on screen
        pollingIntervalRef.current = setInterval(async () => {
          if (activeSessionIdRef.current !== sessionId) {
            clearInterval(pollingIntervalRef.current)
            pollingIntervalRef.current = null
            return
          }
          try {
            const turn = await getActiveSessionTurn(sessionId)
            if (!turn.is_active || turn.status !== 'RUNNING') {
              if (pollingIntervalRef.current) {
                clearInterval(pollingIntervalRef.current)
                pollingIntervalRef.current = null
              }
              const completedMsgs = await getSessionMessages(sessionId)
              processAndSetMessages(completedMsgs, sessionId)
              setLoading(false)
              if (lastMsg) {
                setExpandedThoughtIds((prev) => {
                  const next = new Set(prev)
                  next.delete(lastMsg.message_id)
                  return next
                })
              }
              const updatedList = await getChatSessions()
              setSessions(updatedList)
            } else {
              setMessages((prev) =>
                prev.map((m) =>
                  m.is_streaming || m.message_id === `active-${sessionId}`
                    ? {
                        ...m,
                        reasoning: turn.reasoning || m.reasoning,
                        streamingStatus: turn.current_status,
                        content: turn.content || m.content,
                      }
                    : m
                )
              )
            }
          } catch (pErr) {
            console.error('Polling active turn error:', pErr)
          }
        }, 800)
      } else {
        setLoading(false)
      }

      // Refresh credits for selected session
      const cfg = existingConfig || (await getChatConfig(sessionId))
      if (!existingConfig) {
        setChatConfig(cfg)
        setDailyCreditsLeft(cfg.daily_credits_left ?? cfg.daily_credits)
        setSessionCreditsLeft(cfg.session_credits_left ?? cfg.session_credits)
        setCreditsLeft(cfg.credits_left ?? Math.min(cfg.daily_credits_left ?? 50, cfg.session_credits_left ?? 15))
      }
    } catch (err) {
      console.error(`Failed to load session ${sessionId}:`, err)
      setMessages([buildWelcomeMessage(sessionId)])
      setLoading(false)
    }
  }

  // 5. Create New Session
  const handleNewChat = async () => {
    try {
      const newSess = await createChatSession('New Conversation')
      setSessions((prev) => [newSess, ...prev])
      const freshSessionCredits = chatConfig.session_credits || 15
      setSessionCreditsLeft(freshSessionCredits)
      setCreditsLeft((prev) => Math.min(dailyCreditsLeft, freshSessionCredits))
      await selectSession(newSess.session_id)
    } catch (err) {
      console.error('Failed to create new chat session:', err)
    }
  }

  // 6. Delete Session
  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation()
    try {
      await deleteChatSession(sessionId)
      const remaining = sessions.filter((s) => s.session_id !== sessionId)
      setSessions(remaining)
      if (activeSessionId === sessionId) {
        try {
          localStorage.removeItem('receiviq_active_chat_session_id')
        } catch (err) {}
        if (remaining.length > 0) {
          selectSession(remaining[0].session_id)
        } else {
          handleNewChat()
        }
      }
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  }

  // 7. Rename Session
  const handleRenameSession = async (sessionId, newTitle) => {
    try {
      await renameChatSession(sessionId, newTitle)
      setSessions((prev) =>
        prev.map((s) => (s.session_id === sessionId ? { ...s, title: newTitle } : s))
      )
    } catch (err) {
      console.error('Failed to rename session:', err)
    }
  }

  // 8. Toggle Thought Accordion
  const toggleThought = (msgId) => {
    setExpandedThoughtIds((prev) => {
      const next = new Set(prev)
      if (next.has(msgId)) {
        next.delete(msgId)
      } else {
        next.add(msgId)
      }
      return next
    })
  }

  // 9. Handle Send Prompt with Background Server-Side Persistence & Live Thought Stream
  const handleSend = async (messageText) => {
    const textToSend = (messageText || draft).trim()
    const targetSessionId = activeSessionId
    if (!textToSend || loading || !targetSessionId) return

    if (creditsLeft <= 0 || sessionCreditsLeft <= 0 || dailyCreditsLeft <= 0) return
    if (textToSend.length > chatConfig.max_chars) return

    const tempUserMsg = {
      message_id: `temp-${Date.now()}`,
      session_id: targetSessionId,
      role: 'user',
      content: textToSend,
      created_at: new Date().toISOString(),
    }

    const aiMessageId = `ai-${Date.now()}`
    const initialAiMsg = {
      message_id: aiMessageId,
      session_id: targetSessionId,
      role: 'ai',
      content: '',
      reasoning: '',
      isStreaming: true,
      streamingStatus: 'Initializing agent reasoning loop...',
      execution_seconds: 0.0,
      actions_taken: [],
      created_at: new Date().toISOString(),
    }

    activeTurnsRef.current[targetSessionId] = {
      aiMessageId,
      reasoning: '',
      streamingStatus: 'Initializing agent reasoning loop...',
      content: '',
      done: false,
    }

    setMessages((prev) => [...prev, tempUserMsg, initialAiMsg])
    setExpandedThoughtIds((prev) => new Set(prev).add(aiMessageId))
    setCreditsLeft((prev) => Math.max(0, prev - 1))
    setSessionCreditsLeft((prev) => Math.max(0, prev - 1))
    setDailyCreditsLeft((prev) => Math.max(0, prev - 1))
    setDraft('')
    setLoading(true)

    try {
      await streamChatMessage(textToSend, targetSessionId, {
        onSessionInfo: (info) => {
          if (info.session_title) {
            setSessions((prev) =>
              prev.map((s) =>
                s.session_id === info.session_id ? { ...s, title: info.session_title } : s
              )
            )
          }
        },
        onThought: (chunk) => {
          if (activeTurnsRef.current[targetSessionId]) {
            activeTurnsRef.current[targetSessionId].reasoning += chunk
          }
          if (activeSessionIdRef.current === targetSessionId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.message_id === aiMessageId
                  ? { ...m, reasoning: (m.reasoning || '') + chunk }
                  : m
              )
            )
          }
        },
        onStatus: (statusMsg) => {
          if (activeTurnsRef.current[targetSessionId]) {
            activeTurnsRef.current[targetSessionId].streamingStatus = statusMsg
          }
          if (activeSessionIdRef.current === targetSessionId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.message_id === aiMessageId
                  ? { ...m, streamingStatus: statusMsg }
                  : m
              )
            )
          }
        },
        onContent: (chunk) => {
          if (activeTurnsRef.current[targetSessionId]) {
            activeTurnsRef.current[targetSessionId].content += chunk
            activeTurnsRef.current[targetSessionId].streamingStatus = null
          }
          if (activeSessionIdRef.current === targetSessionId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.message_id === aiMessageId
                  ? { ...m, content: (m.content || '') + chunk, streamingStatus: null }
                  : m
              )
            )
          }
        },
        onDone: (data) => {
          if (activeTurnsRef.current[targetSessionId]) {
            activeTurnsRef.current[targetSessionId].done = true
          }
          if (activeSessionIdRef.current === targetSessionId) {
            setMessages((prev) =>
              prev.map((m) =>
                m.message_id === aiMessageId
                  ? {
                      ...m,
                      isStreaming: false,
                      streamingStatus: null,
                      execution_seconds: data.execution_seconds || 1.1,
                      actions_taken: data.actions_taken || [],
                    }
                  : m
              )
            )
            setExpandedThoughtIds((prev) => {
              const next = new Set(prev)
              next.delete(aiMessageId)
              return next
            })
            setLoading(false)
          }
          if (data.daily_credits_left !== undefined) setDailyCreditsLeft(data.daily_credits_left)
          if (data.session_credits_left !== undefined) setSessionCreditsLeft(data.session_credits_left)
          if (data.credits_left !== undefined) setCreditsLeft(data.credits_left)
          if (data.session_title) {
            setSessions((prev) =>
              prev.map((s) => (s.session_id === data.session_id ? { ...s, title: data.session_title } : s))
            )
          }
        },
        onError: (err) => {
          console.error('Stream error:', err)
        },
      })

      const updatedList = await getChatSessions()
      setSessions(updatedList)
    } catch (err) {
      if (activeSessionIdRef.current === targetSessionId) {
        setMessages((prev) =>
          prev.map((m) =>
            m.message_id === aiMessageId
              ? {
                  ...m,
                  isStreaming: false,
                  content: `Notice: Synchronizing background response with database...`,
                  reasoning: m.reasoning || 'Background processing active.',
                }
              : m
          )
        )
      }
    } finally {
      if (activeSessionIdRef.current === targetSessionId) {
        setLoading(false)
      }
    }
  }

  if (initialLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[450px] space-y-3">
        <div className="h-9 w-9 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        <p className="text-sm font-medium" style={{ color: 'var(--text-muted)' }}>
          Connecting to Bedrock AI and loading chat history...
        </p>
      </div>
    )
  }

  return (
    <div
      className="grid grid-cols-1 md:grid-cols-[280px_1fr] h-[calc(100vh-126px)] rounded-card border overflow-hidden shadow-sm"
      style={{ borderColor: 'var(--border)', background: 'var(--card)' }}
    >
      <ChatSidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={selectSession}
        onNewChat={handleNewChat}
        onDeleteSession={handleDeleteSession}
        onRenameSession={handleRenameSession}
      />

      <div className="flex flex-col h-full overflow-hidden" style={{ background: 'var(--bg-secondary)' }}>
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
          {messages.map((msg) => (
            <ChatMessageItem
              key={msg.message_id}
              msg={msg}
              isThoughtOpen={expandedThoughtIds.has(msg.message_id)}
              onToggleThought={toggleThought}
            />
          ))}
          <div ref={messagesEndRef} />
        </div>

        <ChatInputBar
          draft={draft}
          setDraft={setDraft}
          onSend={handleSend}
          loading={loading}
          chatConfig={chatConfig}
          dailyCreditsLeft={dailyCreditsLeft}
          sessionCreditsLeft={sessionCreditsLeft}
          onNewChat={handleNewChat}
          textareaRef={textareaRef}
        />
      </div>
    </div>
  )
}

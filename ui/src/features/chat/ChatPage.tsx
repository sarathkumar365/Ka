import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, keys } from '../../lib/api'
import { streamChat } from '../../lib/stream'
import { ApprovalCard } from './ApprovalCard'
import { Composer } from './Composer'
import { followGrowth, nearBottom } from './follow'
import { emptyState } from './emptyState'
import { Entity } from './Entity'
import { entityMode } from './entityStyle'
import { Markdown } from './Markdown'
import { initialState, reduce, type ChatItem, type Phase } from './state'
import { ToolLine } from './ToolLine'
import { useTypewriter } from './useTypewriter'

/** The composer doubles as the status line while Ka works (design: Thinking, Searching). */
const RUNNING: Record<string, string> = {
  finance_search_transactions: 'Searching transactions',
  finance_sum_transactions: 'Adding up transactions',
  finance_summary: 'Looking at your spending',
  finance_list_statements: 'Listing statements',
  search_conversations: 'Searching past chats',
  get_jobs: 'Reading your jobs',
  get_profile: 'Reading your profile',
  finance_coverage: 'Checking which dates the data covers',
  propose_change: 'Preparing a change',
  propose_memory: 'Preparing a memory',
  remember: 'Preparing a memory',
  finance_import_statement: 'Preparing a statement import',
  // names before the finance_ prefix, still in older saved chats
  search_transactions: 'Searching transactions',
  sum_transactions: 'Adding up transactions',
  list_statements: 'Listing statements',
  import_statement: 'Preparing a statement import',
}

function placeholderFor(phase: Phase, hasItems: boolean, tool?: string): string {
  if (phase === 'thinking') return 'Thinking'
  if (phase === 'searching') return (tool && RUNNING[tool]) || 'Working'
  if (phase === 'waiting') return 'Answer yes or no above' // the box cannot send until then
  return hasItems ? 'Reply or ask something else' : 'Ask Ka anything'
}

function Answer({ text, animate }: { text: string; animate: boolean }) {
  return <Markdown text={useTypewriter(text, animate)} />
}

export function ChatPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { data: onboarding } = useQuery({ queryKey: keys.onboarding, queryFn: api.onboardingStatus, retry: false })
  const [state, dispatch] = useReducer(reduce, initialState)
  const [loading, setLoading] = useState(false) // history of the opened chat is on its way
  const abort = useRef<AbortController | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const thread = useRef<HTMLDivElement>(null)
  const following = useRef(true)
  const jump = useRef(true) // a freshly loaded chat opens at its end with no glide
  const lastTop = useRef(0)
  const live = useRef(false) // an answer arrived in this session, so type it out
  const loaded = useRef<string | null>(null) // conversation the screen currently shows
  const [typing, setTyping] = useState(false) // composer focused on the empty home: the entity becomes its border
  const [base, setBase] = useState(0) // items that came with the loaded history: they appear without the reveal

  useEffect(() => () => abort.current?.abort(), [])

  useEffect(() => {
    if ((id ?? null) === loaded.current) return
    abort.current?.abort()
    live.current = false
    loaded.current = id ?? null
    if (!id) {
      setLoading(false) // a chat that was still loading must not leave the new one busy
      setBase(0)
      following.current = jump.current = true
      lastTop.current = 0
      return dispatch({ type: 'load', conversationId: null, items: [] })
    }
    let cancelled = false
    setLoading(true)
    api.conversation(id).then(
      (c) => {
        if (cancelled) return
        setLoading(false)
        const items: ChatItem[] = c.items.map((i) => (i.kind === 'tool' ? { ...i, result: i.result ?? undefined } : i))
        setBase(items.length)
        following.current = jump.current = true
      lastTop.current = 0
        dispatch({ type: 'load', conversationId: id, items })
      },
      () => {
        if (cancelled) return
        setLoading(false)
        nav('/chat', { replace: true })
      },
    )
    return () => {
      cancelled = true
    }
  }, [id, nav])

  // Follow the stream only while the reader is at the end; scrolling up to read stops it.
  const toEnd = useCallback(() => {
    const el = scroller.current
    if (!el || !following.current) return
    el.scrollTo({ top: el.scrollHeight, behavior: jump.current ? 'auto' : 'smooth' })
    jump.current = false
  }, [])
  useEffect(() => toEnd(), [state.items, state.phase, toEnd])
  useEffect(() => {
    if (!scroller.current || !thread.current) return
    return followGrowth(scroller.current, thread.current, () => following.current)
  }, [])

  const send = useCallback(
    (text: string) => {
      following.current = true
      dispatch({ type: 'send', text })
      const ctl = new AbortController()
      abort.current = ctl
      streamChat(
        { conversation_id: state.conversationId, text },
        (e) => {
          if (e.type === 'answer') live.current = true
          if (e.type === 'conversation') loaded.current = e.id
          dispatch(e)
          if (e.type === 'conversation' && !state.conversationId) nav(`/chat/${e.id}`, { replace: true })
          if (e.type === 'done') qc.invalidateQueries({ queryKey: keys.conversations })
        },
        ctl.signal,
      ).catch((err) => {
        if (!ctl.signal.aborted) dispatch({ type: 'error', message: err instanceof Error ? err.message : 'Connection lost.' })
      })
    },
    [state.conversationId, nav, qc],
  )

  const decide = (approvalId: string, approve: boolean) => {
    dispatch({ type: 'decide', approvalId, approve })
    api.answerApproval(approvalId, approve).catch(() =>
      dispatch({ type: 'error', message: 'That approval is no longer open.' }),
    )
  }

  const busy = state.phase !== 'idle' || loading
  const empty = state.items.length === 0
  const lastTool = state.items.findLast((i): i is Extract<ChatItem, { kind: 'tool' }> => i.kind === 'tool')?.name
  const lastAssistant = state.items.findLastIndex((i) => i.kind === 'assistant')
  const row = (it: ChatItem, i: number) => {
    switch (it.kind) {
      case 'user':
        return (
          <div className="user">
            <div>{it.text}</div>
          </div>
        )
      case 'tool':
        return <ToolLine name={it.name} args={it.args} result={it.result} />
      case 'approval':
        return (
          <ApprovalCard
            summary={it.summary}
            diff={it.diff}
            decision={it.decision}
            onDecide={(a) => decide(it.approvalId, a)}
          />
        )
      case 'notice':
        return (
          <div className="notice" role="alert">
            {it.text}
          </div>
        )
      case 'assistant':
        return <Answer text={it.text} animate={live.current && i === lastAssistant} />
    }
  }
  return (
    <div className="chat col" data-typing={typing}>
      <Entity mode={entityMode(state.phase, !empty, typing)} />
      <div
        className="msgs"
        ref={scroller}
        // a new row opens from 0px, so scroll again once it has its full height
        onScroll={(e) => {
          const el = e.currentTarget
          // only an upward move unfollows: a smooth scroll in flight passes through mid positions
          if (el.scrollTop < lastTop.current - 2) following.current = nearBottom(el)
          else if (nearBottom(el)) following.current = true
          lastTop.current = el.scrollTop
        }}
        onAnimationEnd={(e) => {
          if ((e.target as HTMLElement).classList.contains('reveal')) toEnd()
        }}
      >
        <div ref={thread}>
          {state.items.map((it, i) => (
            // new rows open from 0fr to 1fr and fade in (design: 380ms var(--E), opacity 220ms)
            <div key={i} className={i >= base ? 'reveal' : undefined}>
              <div>{row(it, i)}</div>
            </div>
          ))}
        </div>
      </div>
      {empty && !busy && (
        <div className="empty">
          {emptyState(onboarding) === 'setup' ? (
            <>
              <div className="lead" style={{ color: 'var(--t1)' }}>
                Ka doesn't know you yet.
              </div>
              <div className="sub" style={{ maxWidth: 420 }}>
                Add your basics, a resume and what other assistants know about you. Ka reads it once and you
                approve what it keeps.
              </div>
              <button className="primary" onClick={() => nav('/onboarding')}>
                Set up Ka
              </button>
            </>
          ) : (
            <div style={{ color: 'var(--t2)' }}>Ask about your profile, your career or your money.</div>
          )}
        </div>
      )}
      {/* the placeholder is the visible status; this line reads it out to screen readers */}
      <div className="vh" role="status">
        {busy ? placeholderFor(state.phase, !empty, lastTool) : ''}
      </div>
      <Composer
        disabled={busy}
        onSend={send}
        docked={state.phase !== 'searching' && (!empty || busy)}
        placeholder={placeholderFor(state.phase, !empty, lastTool)}
        chrome={!empty || busy ? 'on' : typing ? 'off' : 'dim'}
        onFocusChange={setTyping}
      />
    </div>
  )
}

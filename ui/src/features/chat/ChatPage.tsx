import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, keys } from '../../lib/api'
import { streamChat } from '../../lib/stream'
import { ApprovalCard } from './ApprovalCard'
import { Composer } from './Composer'
import { Entity, entityMode } from './Entity'
import { Markdown } from './Markdown'
import { initialState, reduce, type ChatItem } from './state'
import { ToolLine } from './ToolLine'
import { useTypewriter } from './useTypewriter'

const PROMPTS = ['What is my current job?', 'How much did I spend last month?']

function Answer({ text, animate }: { text: string; animate: boolean }) {
  return <Markdown text={useTypewriter(text, animate)} />
}

export function ChatPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [state, dispatch] = useReducer(reduce, initialState)
  const [loading, setLoading] = useState(false) // history of the opened chat is on its way
  const abort = useRef<AbortController | null>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const live = useRef(false) // an answer arrived in this session, so type it out
  const loaded = useRef<string | null>(null) // conversation the screen currently shows

  useEffect(() => () => abort.current?.abort(), [])

  useEffect(() => {
    if ((id ?? null) === loaded.current) return
    abort.current?.abort()
    live.current = false
    loaded.current = id ?? null
    if (!id) return dispatch({ type: 'load', conversationId: null, items: [] })
    let cancelled = false
    setLoading(true)
    api.conversation(id).then(
      (c) => {
        if (cancelled) return
        setLoading(false)
        const items: ChatItem[] = c.items.map((i) => (i.kind === 'tool' ? { ...i, result: i.result ?? undefined } : i))
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

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight })
  }, [state.items, state.phase])

  const send = useCallback(
    (text: string) => {
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
  const lastAssistant = state.items.findLastIndex((i) => i.kind === 'assistant')
  return (
    <div className="chat col">
      <Entity mode={entityMode(state.phase, !empty)} />
      <div className="msgs" ref={scroller}>
        {state.items.map((it, i) => {
          switch (it.kind) {
            case 'user':
              return (
                <div key={i} className="user">
                  <div>{it.text}</div>
                </div>
              )
            case 'tool':
              return <ToolLine key={i} name={it.name} args={it.args} result={it.result} />
            case 'approval':
              return (
                <ApprovalCard
                  key={i}
                  summary={it.summary}
                  diff={it.diff}
                  decision={it.decision}
                  onDecide={(a) => decide(it.approvalId, a)}
                />
              )
            case 'notice':
              return (
                <div key={i} className="notice" role="alert">
                  {it.text}
                </div>
              )
            case 'assistant':
              return <Answer key={i} text={it.text} animate={live.current && i === lastAssistant} />
          }
        })}
      </div>
      {empty && !busy && (
        <div className="empty">
          <div style={{ color: 'var(--t2)' }}>Ask about your profile, your career or your money.</div>
          <div className="row" style={{ flexWrap: 'wrap', justifyContent: 'center', gap: 8 }}>
            {PROMPTS.map((p) => (
              <button key={p} className="chip" onClick={() => send(p)}>
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
      <Composer disabled={busy} onSend={send} docked={!empty || busy} />
    </div>
  )
}

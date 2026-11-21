"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  api,
  errorMessage,
  type ChatMessage,
  type ChatTarget,
  type ChatResponse,
} from "@/lib/api"

export type Scope = `document:${string}` | `collection:${string}` | "library"

function targetFor(scope: Scope): ChatTarget {
  if (scope.startsWith("document:")) return { doc_id: scope.slice(9) }
  if (scope.startsWith("collection:")) return { collection_id: scope.slice(11) }
  return {}
}

function toMessages(turn: ChatResponse): ChatMessage[] {
  return [
    {
      id: `${turn.id}-question`,
      role: "user",
      content: turn.question,
      created_at: turn.created_at,
    },
    {
      id: `${turn.id}-answer`,
      role: "assistant",
      content: turn.answer,
      created_at: turn.created_at,
      citations: turn.citations,
      model: turn.model,
      usage: turn.usage,
    },
  ]
}

export function useConversation(initialScope: Scope, onSaved: () => void) {
  const [scope, setScope] = useState<Scope>(initialScope)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [pendingQuestion, setPendingQuestion] = useState("")
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState("")
  const active = useRef<AbortController | null>(null)

  useEffect(() => () => active.current?.abort(), [])

  const startNew = useCallback((nextScope?: Scope) => {
    active.current?.abort()
    if (nextScope) setScope(nextScope)
    setSessionId(null)
    setMessages([])
    setPendingQuestion("")
    setLoadingHistory(false)
    setError("")
  }, [])

  async function open(id: string) {
    active.current?.abort()
    const request = new AbortController()
    active.current = request
    setLoadingHistory(true)
    setError("")
    try {
      const detail = await api.chat.getSession(id, request.signal)
      if (request.signal.aborted) return
      setSessionId(id)
      setScope(
        detail.doc_id
          ? `document:${detail.doc_id}`
          : detail.collection_id
            ? `collection:${detail.collection_id}`
            : "library"
      )
      setMessages(detail.messages.flatMap(toMessages))
    } catch (error) {
      if (!request.signal.aborted) setError(errorMessage(error))
    } finally {
      if (!request.signal.aborted) setLoadingHistory(false)
    }
  }

  async function send(text: string) {
    const question = text.trim()
    if (!question || pendingQuestion || loadingHistory) return false
    const request = new AbortController()
    active.current = request
    setPendingQuestion(question)
    setError("")
    try {
      const body = sessionId
        ? { question, session_id: sessionId }
        : { question, ...targetFor(scope) }
      const reply = await api.chat.send(body, request.signal)
      if (request.signal.aborted) return false
      setSessionId(reply.session_id ?? null)
      setMessages((previous) => [...previous, ...toMessages(reply)])
      onSaved()
      return true
    } catch (error) {
      if (!request.signal.aborted) setError(errorMessage(error))
      return false
    } finally {
      if (!request.signal.aborted) setPendingQuestion("")
    }
  }

  return {
    scope,
    sessionId,
    messages,
    pendingQuestion,
    loadingHistory,
    error,
    startNew,
    open,
    send,
  }
}

"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { errorMessage } from "@/lib/api"

export function useResource<T>(
  load: () => Promise<T>,
  shouldPoll?: (data: T) => boolean
) {
  const [data, setData] = useState<T>()
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(true)
  const version = useRef(0)

  const refresh = useCallback(async () => {
    const request = ++version.current
    try {
      const next = await load()
      if (request === version.current) {
        setData(next)
        setError("")
      }
    } catch (error) {
      if (request === version.current) setError(errorMessage(error))
    } finally {
      if (request === version.current) setLoading(false)
    }
  }, [load])

  const invalidate = useCallback(() => {
    version.current++
  }, [])
  useEffect(() => {
    const initial = window.setTimeout(() => {
      void refresh()
    }, 0)
    return () => {
      window.clearTimeout(initial)
      invalidate()
    }
  }, [refresh, invalidate])

  const polling = data !== undefined && Boolean(shouldPoll?.(data))
  useEffect(() => {
    if (!polling) return
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh()
    }, 3500)
    return () => window.clearInterval(interval)
  }, [polling, refresh])

  return { data, error, loading, refresh, setData }
}

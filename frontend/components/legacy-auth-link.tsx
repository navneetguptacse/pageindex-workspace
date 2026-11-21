"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

const routes = new Map([
  ["signup", "/complete-registration"],
  ["reset-password", "/reset-password"],
  ["verify-email", "/verify-email"],
  ["oauth-error", "/login"],
])

export function LegacyAuthLink() {
  const router = useRouter()

  useEffect(() => {
    function forward() {
      const hash = window.location.hash
      const action = new URLSearchParams(hash.slice(1)).get("auth")
      const route = action ? routes.get(action) : undefined
      if (route) router.replace(route + hash)
    }
    forward()
    window.addEventListener("hashchange", forward)
    return () => window.removeEventListener("hashchange", forward)
  }, [router])

  return null
}

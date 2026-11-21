"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { AccountMenu } from "@/components/account-menu"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { api, errorMessage } from "@/lib/api"

export function PublicAccountNavigation() {
  const router = useRouter()
  const pathname = usePathname()
  const [username, setUsername] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    let active = true
    function clearSession() {
      active = false
      setUsername(null)
    }
    void api.workspace.status().then(
      (status) => {
        if (active) setUsername(status.username)
      },
      () => {
        if (active) setUsername(null)
      }
    )
    window.addEventListener("pageindex:session-expired", clearSession)
    return () => {
      active = false
      window.removeEventListener("pageindex:session-expired", clearSession)
    }
  }, [pathname])

  async function signOut() {
    setPending(true)
    setError("")
    try {
      await api.workspace.logout()
      window.dispatchEvent(new Event("pageindex:session-expired"))
      router.replace("/login?signed-out=1")
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      {username ? (
        <AccountMenu
          username={username}
          pending={pending}
          onSignOut={signOut}
        />
      ) : (
        <>
          <Button variant="ghost" size="sm" render={<Link href="/login" />}>
            Sign in
          </Button>
          <Button size="sm" render={<Link href="/register" />}>
            Register
          </Button>
        </>
      )}
      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </>
  )
}

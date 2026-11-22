"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { AccountMenu } from "@/components/account-menu"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { api, errorMessage, type WorkspaceStatus } from "@/lib/api"

export function PublicAccountNavigation() {
  const router = useRouter()
  const pathname = usePathname()
  const [profile, setProfile] = useState<WorkspaceStatus | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  useEffect(() => {
    let active = true
    function clearSession() {
      active = false
      setProfile(null)
    }
    void api.workspace.status().then(
      (status) => {
        if (active) setProfile(status)
      },
      () => {
        if (active) setProfile(null)
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
      {profile?.username ? (
        <AccountMenu profile={profile} pending={pending} onSignOut={signOut} />
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

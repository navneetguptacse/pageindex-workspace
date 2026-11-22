"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  createContext,
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react"

import { api, errorMessage, type WorkspaceStatus } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  SidebarInset,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import { AccountMenu } from "@/components/account-menu"
import { AppSidebar } from "@/components/app-sidebar"
import { ThemeToggle } from "@/components/theme-toggle"
import { Spinner } from "@/components/ui/spinner"

export const WorkspaceStatusContext = createContext<WorkspaceStatus | null>(
  null
)

export const WorkspaceStatusUpdateContext = createContext<
  Dispatch<SetStateAction<WorkspaceStatus | null>>
>(() => {})

export function WorkspaceGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<WorkspaceStatus | null>(null)
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)
  const router = useRouter()
  const checkSession = useCallback(async () => {
    try {
      setError("")
      setStatus(await api.workspace.status())
    } catch (error) {
      setError(errorMessage(error))
    }
  }, [])

  useEffect(() => {
    function expire() {
      const next = window.location.pathname + window.location.search
      router.replace(`/login?${new URLSearchParams({ next, expired: "1" })}`)
      setStatus(null)
    }
    window.addEventListener("pageindex:session-expired", expire)
    const initial = window.setTimeout(() => {
      void checkSession()
    }, 0)
    return () => {
      window.clearTimeout(initial)
      window.removeEventListener("pageindex:session-expired", expire)
    }
  }, [checkSession, router])

  const needsSignIn = status?.auth_required && !status.username
  useEffect(() => {
    if (needsSignIn) {
      const next = window.location.pathname + window.location.search
      router.replace(`/login?${new URLSearchParams({ next })}`)
    }
  }, [needsSignIn, router])

  async function signOut() {
    setPending(true)
    try {
      await api.workspace.logout()
      router.replace("/login?signed-out=1")
      setStatus(null)
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setPending(false)
    }
  }

  if (!status || needsSignIn) {
    return (
      <main className="grid min-h-dvh place-items-center px-4">
        {error ? (
          <div className="grid max-w-sm gap-3">
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
            <Button onClick={checkSession}>Retry connection</Button>
            <Button variant="ghost" render={<Link href="/" />}>
              Home
            </Button>
          </div>
        ) : (
          <Spinner aria-label="Opening workspace" />
        )}
      </main>
    )
  }

  return (
    <SidebarProvider
      className="!min-h-dvh"
      style={{ "--sidebar-width": "14.5rem" } as React.CSSProperties}
    >
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:start-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-card focus:p-3"
      >
        Skip to content
      </a>
      <AppSidebar />
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between gap-2 border-b bg-background px-3 sm:px-5">
          <div className="flex min-w-0 items-center gap-3">
            <SidebarTrigger aria-label="Toggle navigation" />
            <span className="truncate font-medium">Document workspace</span>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <ThemeToggle />
            {!status.auth_required && (
              <Button size="sm" variant="ghost" render={<Link href="/" />}>
                Home
              </Button>
            )}
            {status.username && (
              <AccountMenu
                username={status.username}
                pending={pending}
                onSignOut={signOut}
              />
            )}
          </div>
        </header>
        <main
          id="main-content"
          className="min-w-0 flex-1 px-3 py-5 sm:px-6 lg:px-8"
        >
          {error && (
            <Alert className="mb-4" variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          <WorkspaceStatusContext.Provider value={status}>
            <WorkspaceStatusUpdateContext.Provider value={setStatus}>
              {children}
            </WorkspaceStatusUpdateContext.Provider>
          </WorkspaceStatusContext.Provider>
        </main>
      </SidebarInset>
    </SidebarProvider>
  )
}

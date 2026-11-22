"use client"

import Image from "next/image"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  useCallback,
  useEffect,
  useState,
  useSyncExternalStore,
  type FormEvent,
} from "react"

import { ProfileNameFields } from "@/components/workspace-profile"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import {
  api,
  errorMessage,
  type OAuthProvider,
  type WorkspaceStatus,
} from "@/lib/api"

export const oauthName: Record<OAuthProvider, string> = {
  google: "Google",
  github: "GitHub",
}

const oauthErrors: Record<string, string> = {
  "account-exists":
    "An account already uses this email. Sign in to it and connect the provider in account settings.",
  "already-linked": "This provider is already connected to an account.",
  "invalid-state":
    "Your sign-in link expired or was already used. Start again.",
  "session-expired":
    "Your session expired. Sign in before connecting a provider.",
  "signup-disabled": "New account registration is disabled.",
  cancelled: "Sign-in was cancelled.",
  failed:
    "We couldn’t verify your account with the provider. Try again and check that your primary email is verified.",
}

const formCopy = {
  login: ["Sign in", "Sign in to your document workspace."],
  signup: [
    "Create an account",
    "Enter your email to receive a verification link.",
  ],
  forgot: ["Reset password", "Enter the verified email on your account."],
  "finish-signup": [
    "Finish creating your account",
    "Choose a username and password for your workspace.",
  ],
  "reset-password": [
    "Choose a new password",
    "This signs you out of all active sessions.",
  ],
  "verify-email": [
    "Verify your email",
    "Confirm this email as your workspace recovery address.",
  ],
} as const

type AuthView = keyof typeof formCopy

function subscribeToHash(onChange: () => void) {
  window.addEventListener("hashchange", onChange)
  return () => window.removeEventListener("hashchange", onChange)
}

function clearHash() {
  window.history.replaceState(
    window.history.state,
    "",
    window.location.pathname + window.location.search
  )
}

function workspaceDestination() {
  const next = new URLSearchParams(window.location.search).get("next") ?? ""
  return /^\/(workspace|documents|chat|search|extract|trash|account)(\?|$)/.test(
    next
  )
    ? next
    : "/workspace"
}

function PasswordFields({ confirmation }: { confirmation: boolean }) {
  return (
    <>
      <Field>
        <FieldLabel htmlFor="auth-password">
          {confirmation ? "New password" : "Password"}
        </FieldLabel>
        <Input
          id="auth-password"
          name="password"
          type="password"
          autoComplete={confirmation ? "new-password" : "current-password"}
          required
          minLength={confirmation ? 12 : undefined}
          maxLength={256}
        />
      </Field>
      {confirmation && (
        <Field>
          <FieldLabel htmlFor="auth-confirmation">Confirm password</FieldLabel>
          <Input
            id="auth-confirmation"
            name="confirmation"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={256}
          />
        </Field>
      )}
    </>
  )
}

export function WorkspaceAuth({ view }: { view: AuthView }) {
  const router = useRouter()
  const [status, setStatus] = useState<WorkspaceStatus | null>(null)
  const [connectionError, setConnectionError] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")
  const [message, setMessage] = useState("")
  const hash = useSyncExternalStore(
    subscribeToHash,
    () => window.location.hash,
    () => ""
  )
  const params = new URLSearchParams(hash.slice(1))
  const token = params.get("token") ?? ""
  const reason = params.get("reason") ?? ""
  const oauthError =
    params.get("auth") === "oauth-error"
      ? Object.hasOwn(oauthErrors, reason)
        ? oauthErrors[reason]
        : oauthErrors.failed
      : ""
  const [title, description] = formCopy[view]
  const resetting = view === "reset-password"
  const completing = view === "finish-signup"
  const requiresToken = resetting || completing || view === "verify-email"
  const login = view === "login"
  const signup = view === "signup"
  const alreadySignedIn = Boolean(status?.username && (login || signup))
  const query = typeof window === "undefined" ? "" : window.location.search
  const flags = new URLSearchParams(query)
  const notices = new Map([
    ["signed-out", "You’ve signed out."],
    ["signed-out-everywhere", "You’ve signed out of all devices."],
    ["password-changed", "Password updated. Sign in with your new password."],
    ["expired", "Your session expired. Sign in to continue."],
  ])
  const sessionNotice =
    login && status ? [...notices].find(([flag]) => flags.has(flag))?.[1] : ""
  const checkSession = useCallback(async () => {
    setConnectionError("")
    try {
      setStatus(await api.workspace.status())
    } catch (error) {
      setConnectionError(errorMessage(error))
    }
  }, [])

  useEffect(() => {
    const job = window.setTimeout(() => {
      void checkSession()
    }, 0)
    return () => window.clearTimeout(job)
  }, [checkSession])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const email = String(data.get("email") ?? "")
    const username = String(data.get("username") ?? "")
    const password = String(data.get("password") ?? "")
    setError("")
    setMessage("")
    if ((resetting || completing) && password !== data.get("confirmation")) {
      setError("The passwords must match.")
      return
    }
    setPending(true)
    try {
      switch (view) {
        case "login":
          await api.workspace.login(username, password)
          router.replace(workspaceDestination())
          break
        case "signup":
          setMessage((await api.workspace.signup(email)).message)
          break
        case "forgot":
          setMessage((await api.workspace.forgotPassword(email)).message)
          break
        case "finish-signup":
          await api.workspace.verifySignup(
            token,
            username.trim().toLowerCase(),
            password,
            {
              first_name: String(data.get("first_name") ?? "").trim(),
              last_name: String(data.get("last_name") ?? "").trim(),
            }
          )
          clearHash()
          router.replace("/workspace")
          break
        case "reset-password":
          setMessage(
            (await api.workspace.resetPassword(token, password)).message
          )
          clearHash()
          window.dispatchEvent(new Event("pageindex:session-expired"))
          await checkSession()
          break
        case "verify-email":
          setMessage((await api.workspace.verifyEmail(token)).message)
          clearHash()
          break
      }
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setPending(false)
    }
  }

  const availabilityNotice =
    status &&
    (!status.auth_required
      ? "This instance is running in local mode. Accounts are available when workspace authentication is enabled."
      : requiresToken && !token && !message
        ? "Open the link from your account email to continue."
        : signup && !status.registration_open
          ? "New account registration is closed."
          : signup && !status.signup_enabled && !status.oauth_providers.length
            ? "Account registration is currently unavailable."
            : view === "forgot" && !status.email_enabled
              ? "Password reset by email is currently unavailable."
              : "")
  const displayedError = error || connectionError || oauthError
  const showForm =
    status?.auth_required &&
    !alreadySignedIn &&
    !availabilityNotice &&
    (!signup || status.signup_enabled) &&
    (!requiresToken || !message)

  return (
    <main className="grid flex-1 place-items-center bg-muted px-4 py-10">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <h1 className="text-xl font-semibold">{title}</h1>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="flex min-w-0 flex-col gap-4">
          {displayedError && (
            <Alert variant="destructive" role="alert">
              <AlertDescription>{displayedError}</AlertDescription>
            </Alert>
          )}
          {(message || sessionNotice || availabilityNotice) && (
            <Alert role="status">
              <AlertDescription>
                {message || sessionNotice || availabilityNotice}
              </AlertDescription>
            </Alert>
          )}
          {status ? (
            <>
              {showForm && (
                <form onSubmit={submit}>
                  <FieldGroup>
                    {completing && <ProfileNameFields />}
                    {(view === "login" || completing) && (
                      <Field>
                        <FieldLabel htmlFor="auth-username">
                          {completing ? "Username" : "Username or email"}
                        </FieldLabel>
                        <Input
                          id="auth-username"
                          name="username"
                          autoComplete="username"
                          autoCapitalize="none"
                          spellCheck={false}
                          required
                          minLength={completing ? 3 : undefined}
                          maxLength={completing ? 64 : 254}
                        />
                        {completing && (
                          <FieldDescription>
                            Your username is permanent.
                          </FieldDescription>
                        )}
                      </Field>
                    )}
                    {(view === "signup" || view === "forgot") && (
                      <Field>
                        <FieldLabel htmlFor="auth-email">
                          Email address
                        </FieldLabel>
                        <Input
                          id="auth-email"
                          name="email"
                          type="email"
                          autoComplete="email"
                          required
                          maxLength={254}
                        />
                      </Field>
                    )}
                    {(view === "login" || completing || resetting) && (
                      <PasswordFields confirmation={completing || resetting} />
                    )}
                    <Button type="submit" disabled={pending}>
                      {pending && <Spinner data-icon="inline-start" />}
                      {view === "signup" || view === "forgot"
                        ? "Send email"
                        : completing
                          ? "Create account"
                          : resetting
                            ? "Update password"
                            : title}
                    </Button>
                  </FieldGroup>
                </form>
              )}
              {(login || signup) &&
                !alreadySignedIn &&
                status.auth_required &&
                (login || status.registration_open) &&
                status.oauth_providers.length > 0 && (
                  <div className="flex flex-col gap-2 border-t pt-4">
                    {status.oauth_providers.map((provider) => (
                      <Button
                        key={provider}
                        variant="outline"
                        render={
                          <a
                            aria-label={`Continue with ${oauthName[provider]}`}
                            href={api.workspace.oauthUrl(provider)}
                          />
                        }
                        nativeButton={false}
                      >
                        <Image
                          src={`/icons/auth/${provider}.svg`}
                          alt=""
                          width={16}
                          height={16}
                          data-icon="inline-start"
                          className={
                            provider === "github"
                              ? "shrink-0 dark:invert"
                              : "shrink-0"
                          }
                        />
                        Continue with {oauthName[provider]}
                      </Button>
                    ))}
                  </div>
                )}
              {alreadySignedIn ||
              !status.auth_required ||
              (message && status.username) ? (
                <>
                  <Button
                    render={
                      <Link
                        href={
                          alreadySignedIn
                            ? workspaceDestination()
                            : "/workspace"
                        }
                      />
                    }
                  >
                    Open workspace
                  </Button>
                  {login && !status.auth_required && (
                    <Button
                      variant="link"
                      render={<Link href="/forgot-password" />}
                    >
                      Forgot password?
                    </Button>
                  )}
                </>
              ) : login ? (
                <div className="flex flex-wrap items-center justify-between gap-x-2">
                  <Button
                    variant="link"
                    className="px-0"
                    render={<Link href="/forgot-password" />}
                  >
                    Forgot password?
                  </Button>
                  <Button
                    variant="link"
                    className="px-0"
                    render={<Link href="/register" />}
                  >
                    Create an account
                  </Button>
                </div>
              ) : (
                <Button variant="ghost" render={<Link href="/login" />}>
                  Back to sign in
                </Button>
              )}
            </>
          ) : connectionError ? (
            <Button onClick={checkSession}>Retry connection</Button>
          ) : (
            <Spinner aria-label="Checking workspace session" />
          )}
        </CardContent>
      </Card>
    </main>
  )
}

"use client"

import { useContext, useRef, useState, type FormEvent } from "react"

import { WorkspaceStatusUpdateContext } from "@/components/workspace-gate"
import { UserAvatar } from "@/components/user-avatar"
import { ErrorNotice } from "@/components/workspace-ui"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { api, errorMessage, type WorkspaceStatus } from "@/lib/api"

export function ProfileNameFields({
  firstName,
  lastName,
  disabled,
}: {
  firstName?: string | null
  lastName?: string | null
  disabled?: boolean
}) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field>
        <FieldLabel htmlFor="first-name">First name</FieldLabel>
        <Input
          id="first-name"
          name="first_name"
          autoComplete="given-name"
          defaultValue={firstName ?? ""}
          required
          maxLength={80}
          disabled={disabled}
        />
      </Field>
      <Field>
        <FieldLabel htmlFor="last-name">Last name</FieldLabel>
        <Input
          id="last-name"
          name="last_name"
          autoComplete="family-name"
          defaultValue={lastName ?? ""}
          required
          maxLength={80}
          disabled={disabled}
        />
      </Field>
    </div>
  )
}

export function WorkspaceProfile({ status }: { status: WorkspaceStatus }) {
  const updateStatus = useContext(WorkspaceStatusUpdateContext)
  const [pending, setPending] = useState(false)
  const [notice, setNotice] = useState("")
  const [error, setError] = useState("")

  async function saveNames(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setPending(true)
    setError("")
    setNotice("")
    try {
      const saved = await api.workspace.updateProfile({
        first_name: String(data.get("first_name")).trim(),
        last_name: String(data.get("last_name")).trim(),
      })
      updateStatus((current) =>
        current?.username === saved.username
          ? {
              ...current,
              first_name: saved.first_name,
              last_name: saved.last_name,
            }
          : current
      )
      setNotice("Profile updated.")
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setPending(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <h2 className="font-semibold">Profile</h2>
      </CardHeader>
      <CardContent className="grid gap-4">
        <ProfilePhoto status={status} />
        <dl className="grid gap-1 text-sm">
          <dt className="text-muted-foreground">Username</dt>
          <dd className="font-medium break-all">{status.username}</dd>
        </dl>
        <form onSubmit={saveNames}>
          <FieldGroup>
            <ProfileNameFields
              firstName={status.first_name}
              lastName={status.last_name}
              disabled={pending}
            />
            {error && <ErrorNotice>{error}</ErrorNotice>}
            {notice && (
              <p role="status" className="text-sm text-success">
                {notice}
              </p>
            )}
            <Button
              type="submit"
              variant="outline"
              className="self-start"
              disabled={pending}
            >
              {pending && <Spinner data-icon="inline-start" />}
              Save name
            </Button>
          </FieldGroup>
        </form>
        <div className="grid gap-3 border-t pt-4">
          <dl className="grid gap-1 text-sm">
            <dt className="text-muted-foreground">Recovery email</dt>
            <dd className="flex flex-wrap items-center gap-2 font-medium break-all">
              {status.email ?? "No email address"}
              {status.email && (
                <Badge
                  variant={status.email_verified ? "success" : "secondary"}
                >
                  {status.email_verified ? "Verified" : "Unverified"}
                </Badge>
              )}
            </dd>
          </dl>
          {status.email_enabled && (
            <EmailChangeForm
              hasPassword={status.has_password}
              onVerified={(saved) =>
                updateStatus((current) =>
                  current?.username === saved.username
                    ? {
                        ...current,
                        email: saved.email,
                        email_verified: saved.email_verified,
                      }
                    : current
                )
              }
            />
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function ProfilePhoto({ status }: { status: WorkspaceStatus }) {
  const updateStatus = useContext(WorkspaceStatusUpdateContext)
  const input = useRef<HTMLInputElement>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  async function changePhoto(file?: File) {
    setError("")
    if (file && file.size > 2 * 1024 * 1024) {
      setError("Choose a profile picture no larger than 2 MB.")
      return
    }
    setPending(true)
    try {
      const saved = file
        ? await api.workspace.uploadAvatar(file)
        : await api.workspace.removeAvatar()
      updateStatus((current) =>
        current?.username === saved.username
          ? { ...current, avatar_url: saved.avatar_url }
          : current
      )
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="grid gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <UserAvatar profile={status} size="lg" />
        <input
          ref={input}
          type="file"
          hidden
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => {
            const file = event.currentTarget.files?.[0]
            event.currentTarget.value = ""
            if (file) void changePhoto(file)
          }}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={pending}
            onClick={() => input.current?.click()}
          >
            {status.avatar_url ? "Change photo" : "Upload photo"}
          </Button>
          {status.avatar_url && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={pending}
              onClick={() => void changePhoto()}
            >
              Remove photo
            </Button>
          )}
        </div>
      </div>
      {pending && (
        <p role="status" className="text-sm text-muted-foreground">
          Updating photo…
        </p>
      )}
      {error && <ErrorNotice>{error}</ErrorNotice>}
    </div>
  )
}

function EmailChangeForm({
  hasPassword,
  onVerified,
}: {
  hasPassword: boolean
  onVerified: (status: WorkspaceStatus) => void
}) {
  const [editing, setEditing] = useState(false)
  const [address, setAddress] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setError("")
    setNotice("")
    setPending(true)
    try {
      if (address) {
        onVerified(
          await api.workspace.confirmEmailChange(
            address,
            String(data.get("code"))
          )
        )
        setAddress("")
        setEditing(false)
        setNotice("Email updated and verified.")
      } else {
        const email = String(data.get("email")).trim()
        const response = await api.workspace.requestEmailChange(
          email,
          hasPassword ? String(data.get("password")) : undefined
        )
        setAddress(email)
        setNotice(response.message)
      }
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="grid gap-3">
      {error && <ErrorNotice>{error}</ErrorNotice>}
      {notice && (
        <p role="status" className="text-sm text-success">
          {notice}
        </p>
      )}
      {editing ? (
        <form onSubmit={submit}>
          <FieldGroup>
            {address ? (
              <Field>
                <FieldLabel htmlFor="email-change-code">
                  Verification code
                </FieldLabel>
                <Input
                  key="verification-code"
                  id="email-change-code"
                  name="code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  required
                  disabled={pending}
                />
                <FieldDescription>
                  Enter the six-digit code sent to {address}.
                </FieldDescription>
              </Field>
            ) : (
              <>
                <Field>
                  <FieldLabel htmlFor="new-email">New email address</FieldLabel>
                  <Input
                    id="new-email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    maxLength={254}
                    required
                    disabled={pending}
                  />
                </Field>
                {hasPassword && (
                  <Field>
                    <FieldLabel htmlFor="email-change-password">
                      Current password
                    </FieldLabel>
                    <Input
                      id="email-change-password"
                      name="password"
                      type="password"
                      autoComplete="current-password"
                      maxLength={256}
                      required
                      disabled={pending}
                    />
                  </Field>
                )}
              </>
            )}
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={pending}>
                {pending && <Spinner data-icon="inline-start" />}
                {address ? "Verify email" : "Send code"}
              </Button>
              <Button
                type="button"
                variant="ghost"
                aria-label={
                  address ? "Back to change email or resend code" : undefined
                }
                disabled={pending}
                onClick={() => {
                  setError("")
                  setNotice("")
                  if (address) setAddress("")
                  else setEditing(false)
                }}
              >
                {address ? "Back" : "Cancel"}
              </Button>
            </div>
          </FieldGroup>
        </form>
      ) : (
        <Button
          type="button"
          variant="outline"
          className="justify-self-start"
          onClick={() => {
            setNotice("")
            setEditing(true)
          }}
        >
          Change email
        </Button>
      )}
    </div>
  )
}

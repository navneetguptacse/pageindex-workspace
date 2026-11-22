"use client"

import { useContext, useState, type FormEvent } from "react"
import { useRouter } from "next/navigation"

import { ConfirmAction } from "@/components/confirm-action"
import { WorkspaceStatusContext } from "@/components/workspace-gate"
import { WorkspaceProfile } from "@/components/workspace-profile"
import { WorkspaceProviderSettings } from "@/components/workspace-provider-settings"
import { oauthName } from "@/components/workspace-auth"
import {
  ErrorNotice,
  PageHeader,
  WorkspacePanel,
} from "@/components/workspace-ui"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { api, errorMessage } from "@/lib/api"

function ChangePasswordForm() {
  const router = useRouter()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const password = String(data.get("newPassword"))
    setError("")
    if (password !== data.get("confirmPassword")) {
      setError("The passwords must match.")
      return
    }
    setPending(true)
    try {
      await api.workspace.changePassword(
        String(data.get("currentPassword")),
        password
      )
      router.replace("/login?password-changed=1")
    } catch (error) {
      setError(errorMessage(error))
      setPending(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <h2 className="font-semibold">Change password</h2>
        <CardDescription>
          Updating your password signs you out of all devices.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={changePassword}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="current-password">
                Current password
              </FieldLabel>
              <Input
                id="current-password"
                name="currentPassword"
                type="password"
                autoComplete="current-password"
                required
                maxLength={256}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="new-password">New password</FieldLabel>
              <Input
                id="new-password"
                name="newPassword"
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={256}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="confirm-password">
                Confirm new password
              </FieldLabel>
              <Input
                id="confirm-password"
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={256}
              />
            </Field>
            {error && <ErrorNotice>{error}</ErrorNotice>}
            <Button
              type="submit"
              variant="outline"
              className="self-start"
              disabled={pending}
            >
              {pending && <Spinner data-icon="inline-start" />}
              Update password
            </Button>
          </FieldGroup>
        </form>
      </CardContent>
    </Card>
  )
}

export function WorkspaceAccount() {
  const router = useRouter()
  const status = useContext(WorkspaceStatusContext)
  const [confirmSignOut, setConfirmSignOut] = useState(false)

  if (!status?.username) {
    return (
      <WorkspacePanel>
        <PageHeader
          title="Account settings"
          description="This workspace is running in local mode. Account settings are available when authentication is enabled."
        />
      </WorkspacePanel>
    )
  }

  return (
    <WorkspacePanel>
      <PageHeader
        title="Account settings"
        description="Manage your profile, providers, and sign-in settings."
      />
      <WorkspaceProviderSettings key={status.username} />
      <div className="grid max-w-5xl items-start gap-4 lg:grid-cols-2">
        <div className="grid min-w-0 gap-4">
          <WorkspaceProfile key={status.username} status={status} />
          {(status.oauth_providers.length > 0 ||
            status.linked_providers.length > 0) && (
            <Card>
              <CardHeader>
                <h2 className="font-semibold">Connected sign-in methods</h2>
              </CardHeader>
              <CardContent className="flex flex-wrap items-center gap-2">
                {[
                  ...new Set([
                    ...status.oauth_providers,
                    ...status.linked_providers,
                  ]),
                ].map((provider) =>
                  status.linked_providers.includes(provider) ? (
                    <span
                      key={provider}
                      className="rounded-control bg-success-surface px-2.5 py-1 text-sm text-success"
                    >
                      {oauthName[provider]} connected
                    </span>
                  ) : (
                    <Button
                      key={provider}
                      variant="outline"
                      render={
                        <a
                          aria-label={`Connect ${oauthName[provider]}`}
                          href={api.workspace.oauthUrl(provider, true)}
                        />
                      }
                      nativeButton={false}
                    >
                      Connect {oauthName[provider]}
                    </Button>
                  )
                )}
              </CardContent>
            </Card>
          )}
        </div>
        <div className="grid min-w-0 gap-4">
          {status.has_password && <ChangePasswordForm />}
          <Card>
            <CardHeader>
              <h2 className="font-semibold">Sessions</h2>
              <CardDescription>
                End every active session, including this one.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => setConfirmSignOut(true)}>
                Sign out everywhere
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
      {confirmSignOut && (
        <ConfirmAction
          title="Sign out everywhere?"
          description="You’ll need to sign in again on every device."
          action="Sign out everywhere"
          onConfirm={async () => {
            await api.workspace.logoutEverywhere()
            router.replace("/login?signed-out-everywhere=1")
          }}
          onClose={() => setConfirmSignOut(false)}
        />
      )}
    </WorkspacePanel>
  )
}

"use client"

import { useState, type FormEvent } from "react"

import { ConfirmAction } from "@/components/confirm-action"
import { ErrorNotice } from "@/components/workspace-ui"
import { Badge } from "@/components/ui/badge"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { useResource } from "@/hooks/use-resource"
import {
  api,
  errorMessage,
  type ChatProvider,
  type ProviderSettings,
  type ProviderSettingsUpdate,
} from "@/lib/api"

const providers: { value: ChatProvider; label: string }[] = [
  { value: "openai", label: "OpenAI" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini", label: "Google Gemini" },
]

type Connection = "pageindex" | "chat"
const connectionLabels = { pageindex: "PageIndex", chat: "chat" }

export function WorkspaceProviderSettings() {
  const settings = useResource(api.workspace.providers)
  const [pending, setPending] = useState<Connection>()
  const [notice, setNotice] = useState("")
  const [error, setError] = useState("")
  const [removing, setRemoving] = useState<Connection>()
  const saved = settings.data

  async function update(
    connection: Connection,
    changes: ProviderSettingsUpdate,
    message: string
  ) {
    setPending(connection)
    setError("")
    setNotice("")
    try {
      const next = await api.workspace.updateProviders(changes)
      settings.setData(next)
      setNotice(message)
    } finally {
      setPending(undefined)
    }
  }

  async function save(
    event: FormEvent<HTMLFormElement>,
    connection: Connection,
    changes: ProviderSettingsUpdate
  ) {
    const form = event.currentTarget
    try {
      await update(connection, changes, "Provider settings saved.")
      const key = form.elements.namedItem("apiKey")
      if (key instanceof HTMLInputElement) key.value = ""
    } catch (error) {
      setError(errorMessage(error))
    }
  }

  return (
    <Card id="provider-settings" className="max-w-5xl scroll-mt-4">
      <CardHeader>
        <h2 className="font-semibold">Provider settings</h2>
        <CardDescription>
          Use your own PageIndex account for PDFs and your own AI provider for
          chat.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {settings.loading && (
          <p role="status" className="flex items-center gap-2 text-sm">
            <Spinner /> Loading provider settings
          </p>
        )}
        {settings.error && (
          <div className="grid justify-items-start gap-2">
            <ErrorNotice>{settings.error}</ErrorNotice>
            <Button variant="outline" onClick={() => void settings.refresh()}>
              Retry
            </Button>
          </div>
        )}
        {saved && (
          <div className="grid gap-6 lg:grid-cols-2">
            <form
              onSubmit={(event) => {
                event.preventDefault()
                const key = String(
                  new FormData(event.currentTarget).get("apiKey")
                )
                void save(event, "pageindex", { pageindex_api_key: key })
              }}
            >
              <FieldGroup>
                <ConnectionTitle
                  title="PageIndex"
                  configured={saved.pageindex_configured}
                />
                <Field>
                  <FieldLabel htmlFor="pageindex-api-key">
                    PageIndex API key
                  </FieldLabel>
                  <Input
                    id="pageindex-api-key"
                    name="apiKey"
                    type="password"
                    autoComplete="new-password"
                    required
                    maxLength={4096}
                    disabled={Boolean(pending)}
                  />
                  <FieldDescription>
                    Use a key from your PageIndex library to upload, search, and
                    extract from PDFs.
                  </FieldDescription>
                </Field>
                <ConnectionActions
                  connection="pageindex"
                  configured={saved.pageindex_configured}
                  pending={pending}
                  onRemove={setRemoving}
                />
              </FieldGroup>
            </form>
            <ChatSettingsForm
              key={`${saved.chat_provider}:${saved.chat_model}:${saved.chat_configured}`}
              saved={saved}
              pending={pending}
              onSave={save}
              onRemove={setRemoving}
            />
          </div>
        )}
        {error && <ErrorNotice>{error}</ErrorNotice>}
        {notice && (
          <p role="status" className="text-sm text-success">
            {notice}
          </p>
        )}
      </CardContent>
      {removing && (
        <ConfirmAction
          title={`Remove ${connectionLabels[removing]} credentials?`}
          description={
            removing === "pageindex"
              ? "PageIndex features will be unavailable until you save a key."
              : "Chat will be unavailable until you save a provider key."
          }
          action="Remove credentials"
          onConfirm={() =>
            update(
              removing,
              removing === "pageindex"
                ? { pageindex_api_key: null }
                : { chat: null },
              "Credentials removed."
            )
          }
          onClose={() => setRemoving(undefined)}
        />
      )}
    </Card>
  )
}

function ChatSettingsForm({
  saved,
  pending,
  onSave,
  onRemove,
}: {
  saved: ProviderSettings
  pending?: Connection
  onSave: (
    event: FormEvent<HTMLFormElement>,
    connection: Connection,
    changes: ProviderSettingsUpdate
  ) => Promise<void>
  onRemove: (connection: Connection) => void
}) {
  const [provider, setProvider] = useState<ChatProvider | null>(
    saved.chat_provider
  )
  const [model, setModel] = useState(saved.chat_model ?? "")
  const keepKey = saved.chat_configured && provider === saved.chat_provider

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!provider) return
    const key = String(new FormData(event.currentTarget).get("apiKey")).trim()
    void onSave(event, "chat", {
      chat: { provider, model: model.trim(), ...(key && { api_key: key }) },
    })
  }

  return (
    <form onSubmit={submit}>
      <FieldGroup>
        <ConnectionTitle title="Chat" configured={saved.chat_configured} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="chat-provider">Provider</FieldLabel>
            <Select
              name="provider"
              items={providers}
              value={provider}
              disabled={Boolean(pending)}
              required
              onValueChange={(value) => {
                setProvider(value)
                setModel(
                  value === saved.chat_provider ? (saved.chat_model ?? "") : ""
                )
              }}
            >
              <SelectTrigger id="chat-provider" className="w-full">
                <SelectValue placeholder="Choose a provider" />
              </SelectTrigger>
              <SelectContent>
                {providers.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor="chat-model">Model ID</FieldLabel>
            <Input
              id="chat-model"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder="Enter the provider’s model ID"
              required
              maxLength={150}
              disabled={Boolean(pending)}
            />
          </Field>
        </div>
        <Field>
          <FieldLabel htmlFor="chat-api-key">Chat provider API key</FieldLabel>
          <Input
            id="chat-api-key"
            name="apiKey"
            type="password"
            autoComplete="new-password"
            required={!keepKey}
            maxLength={4096}
            disabled={Boolean(pending)}
          />
          {keepKey && (
            <FieldDescription>
              Leave blank to keep the saved key.
            </FieldDescription>
          )}
        </Field>
        <ConnectionActions
          connection="chat"
          configured={saved.chat_configured}
          pending={pending}
          onRemove={onRemove}
        />
      </FieldGroup>
    </form>
  )
}

function ConnectionTitle({
  title,
  configured,
}: {
  title: string
  configured: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <h3 className="text-sm font-semibold">{title}</h3>
      <Badge variant={configured ? "success" : "secondary"}>
        {configured ? "Configured" : "Setup needed"}
      </Badge>
    </div>
  )
}

function ConnectionActions({
  connection,
  configured,
  pending,
  onRemove,
}: {
  connection: Connection
  configured: boolean
  pending?: Connection
  onRemove: (connection: Connection) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button type="submit" disabled={Boolean(pending)}>
        {pending === connection && <Spinner data-icon="inline-start" />}
        {connection === "pageindex"
          ? "Save PageIndex key"
          : "Save chat settings"}
      </Button>
      {configured && (
        <Button
          type="button"
          variant="outline"
          onClick={() => onRemove(connection)}
          disabled={Boolean(pending)}
        >
          Remove key
        </Button>
      )}
    </div>
  )
}

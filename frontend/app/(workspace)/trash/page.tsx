"use client"

import { useState } from "react"
import { RotateCcwIcon, Trash2Icon } from "lucide-react"

import {
  api,
  errorMessage,
  type TrashItem,
  type TrashReference,
} from "@/lib/api"
import { formatDate } from "@/lib/format"
import { useResource } from "@/hooks/use-resource"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ConfirmAction } from "@/components/confirm-action"
import {
  ErrorNotice,
  LoadingRows,
  PageHeader,
  WorkspacePanel,
} from "@/components/workspace-ui"

const labels = { document: "PDF", chat: "Conversation", extract: "Extraction" }
const itemKey = (item: TrashReference) => `${item.type}:${item.id}`

export default function TrashPage() {
  const trash = useResource(api.trash.list)
  const [filter, setFilter] = useState<"all" | TrashItem["type"]>("all")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [action, setAction] = useState<"empty" | TrashReference[] | null>(null)
  const [error, setError] = useState("")
  const [notice, setNotice] = useState("")
  const [busy, setBusy] = useState(false)

  const items = (trash.data ?? []).filter(
    (item) => filter === "all" || filter === item.type
  )
  const chosen = items.filter((item) => selected.has(itemKey(item)))
  const count = trash.data?.length ?? 0

  function toggle(item: TrashReference, checked: boolean) {
    setSelected((previous) => {
      const next = new Set(previous)
      if (checked) next.add(itemKey(item))
      else next.delete(itemKey(item))
      return next
    })
  }

  async function restore(items: TrashReference[]) {
    setBusy(true)
    setError("")
    setNotice("")
    try {
      const { restored } = await api.trash.restore(items)
      setSelected(new Set())
      setNotice(`Restored ${restored} ${restored === 1 ? "item" : "items"}.`)
      await trash.refresh()
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <WorkspacePanel>
      <PageHeader
        title="Trash"
        description="Restore deleted items or remove them permanently."
        actions={
          count ? (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => setAction("empty")}
            >
              <Trash2Icon data-icon="inline-start" />
              Empty trash
            </Button>
          ) : undefined
        }
      />
      {(error || trash.error) && (
        <ErrorNotice>{error || trash.error}</ErrorNotice>
      )}
      {notice && (
        <p
          role="status"
          className="rounded-lg bg-success-surface px-3 py-2 text-sm text-success"
        >
          {notice}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          value={filter}
          onValueChange={(value) => {
            setFilter(value as typeof filter)
            setSelected(new Set())
          }}
        >
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="document">PDFs</TabsTrigger>
            <TabsTrigger value="chat">Chats</TabsTrigger>
            <TabsTrigger value="extract">Extractions</TabsTrigger>
          </TabsList>
        </Tabs>
        {chosen.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => restore(chosen)}
            >
              <RotateCcwIcon data-icon="inline-start" />
              Restore ({chosen.length})
            </Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => setAction(chosen)}
            >
              Delete permanently
            </Button>
          </div>
        )}
      </div>
      <Card className="py-0">
        <CardContent className="px-3 sm:px-4">
          {trash.loading ? (
            <LoadingRows label="Loading trash" />
          ) : !items.length ? (
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <Trash2Icon />
                </EmptyMedia>
                <EmptyTitle>
                  {filter === "all"
                    ? "Trash is empty"
                    : "No deleted items in this category"}
                </EmptyTitle>
                <EmptyDescription>
                  Deleted items appear here until you restore or permanently
                  remove them.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <>
              <div className="flex items-center gap-2 border-b py-2.5">
                <Checkbox
                  id="trash-select-all"
                  checked={chosen.length === items.length}
                  indeterminate={
                    chosen.length > 0 && chosen.length < items.length
                  }
                  onCheckedChange={(checked) =>
                    setSelected(new Set(checked ? items.map(itemKey) : []))
                  }
                />
                <label
                  htmlFor="trash-select-all"
                  className="text-sm font-medium"
                >
                  Select all
                </label>
              </div>
              <ul className="divide-y">
                {items.map((item) => (
                  <li
                    key={itemKey(item)}
                    className="flex min-w-0 flex-wrap items-center gap-3 py-3"
                  >
                    <Checkbox
                      aria-label={`Select ${item.title}`}
                      checked={selected.has(itemKey(item))}
                      onCheckedChange={(checked) => toggle(item, checked)}
                    />
                    <div className="min-w-0 flex-1">
                      <span className="block truncate font-medium">
                        {item.title}
                      </span>
                      <time
                        className="text-xs text-muted-foreground"
                        dateTime={item.deleted_at}
                      >
                        {formatDate(item.deleted_at)}
                      </time>
                    </div>
                    <Badge variant="secondary">{labels[item.type]}</Badge>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => restore([item])}
                      aria-label={`Restore ${item.title}`}
                      title="Restore"
                    >
                      <RotateCcwIcon />
                    </Button>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      disabled={busy}
                      onClick={() => setAction([item])}
                      aria-label={`Permanently delete ${item.title}`}
                      title="Permanently delete"
                    >
                      <Trash2Icon />
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
      {action && (
        <ConfirmAction
          title={
            action === "empty"
              ? "Empty trash?"
              : "Permanently delete selected items?"
          }
          description="Permanently deleted items cannot be restored."
          action="Delete permanently"
          onClose={() => setAction(null)}
          onConfirm={async () => {
            const deleted =
              action === "empty"
                ? (await api.trash.empty()).purged
                : (await api.trash.permanentDelete(action)).deleted
            setSelected(new Set())
            setNotice(
              `Permanently deleted ${deleted} ${deleted === 1 ? "item" : "items"}.`
            )
            await trash.refresh()
          }}
        />
      )}
    </WorkspacePanel>
  )
}

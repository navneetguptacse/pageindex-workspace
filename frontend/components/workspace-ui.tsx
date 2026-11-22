import Link from "next/link"
import type { ReactNode } from "react"
import { CircleAlertIcon } from "lucide-react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
      <div className="min-w-0">
        <h1 className="text-2xl leading-tight font-semibold tracking-tight sm:text-[1.75rem]">
          {title}
        </h1>
        {description && (
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {actions && (
        <div className="flex flex-wrap items-center gap-2">{actions}</div>
      )}
    </header>
  )
}

export function ErrorNotice({ children }: { children: ReactNode }) {
  return (
    <Alert variant="destructive" role="alert">
      <CircleAlertIcon aria-hidden="true" />
      <AlertDescription>{children}</AlertDescription>
    </Alert>
  )
}

export function ProcessingErrorText({ message }: { message: string }) {
  const [before, label, ...after] = message.split(/(provider settings)/i)
  if (!label) return message

  return (
    <>
      {before}
      <Link
        href="/account#provider-settings"
        className="rounded-sm font-semibold control-focus"
      >
        {label}
      </Link>
      {after.join("")}
    </>
  )
}

const statuses = {
  queued: { label: "Queued", variant: "secondary" },
  submitting: { label: "Starting", variant: "discovery" },
  processing: { label: "Indexing", variant: "discovery" },
  pending: { label: "Pending", variant: "discovery" },
  running: { label: "Running", variant: "discovery" },
  ready: { label: "Ready", variant: "success" },
  completed: { label: "Completed", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
  cancelled: { label: "Cancelled", variant: "warning" },
} as const

export function ResourceStatus({ status }: { status: keyof typeof statuses }) {
  return (
    <Badge variant={statuses[status].variant}>{statuses[status].label}</Badge>
  )
}

export function LoadingRows({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-3 py-3">
      {[0, 1, 2].map((row) => (
        <Skeleton key={row} className="h-9 w-full" />
      ))}
    </div>
  )
}

export function WorkspacePanel({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-7xl min-w-0 flex-col gap-6">
      {children}
    </div>
  )
}

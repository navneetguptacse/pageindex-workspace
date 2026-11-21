export function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
    new Date(value)
  )
}

export function formatBytes(bytes: number | null | undefined) {
  if (bytes == null) return "—"
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`
}

export function documentIsPending({ status }: { status: string }) {
  return ["queued", "submitting", "processing"].includes(status)
}

export function extractionIsPending({ status }: { status: string }) {
  return ["queued", "submitting", "pending", "running"].includes(status)
}

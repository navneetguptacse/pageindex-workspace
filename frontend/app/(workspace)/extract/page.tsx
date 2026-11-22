"use client"

import { Suspense, useRef, useState, type FormEvent } from "react"
import { useSearchParams } from "next/navigation"
import {
  BracesIcon,
  ClipboardIcon,
  DownloadIcon,
  Table2Icon,
  Trash2Icon,
} from "lucide-react"

import { api, errorMessage } from "@/lib/api"
import { extractionPresets } from "@/lib/extraction-presets"
import { extractionIsPending, formatDate } from "@/lib/format"
import { useResource } from "@/hooks/use-resource"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { Spinner } from "@/components/ui/spinner"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Badge } from "@/components/ui/badge"
import { CitationModal } from "@/components/citation-modal"
import { ConfirmAction } from "@/components/confirm-action"
import {
  ErrorNotice,
  LoadingRows,
  PageHeader,
  ProcessingErrorText,
  ResourceStatus,
  WorkspacePanel,
} from "@/components/workspace-ui"

const loadDocuments = () => api.documents.list()
const loadJobs = () => api.extract.listJobs()
const tierItems = [
  { value: "standard", label: "Standard" },
  { value: "pro", label: "Pro" },
]
const presetItems = [
  ...Object.entries(extractionPresets).map(([value, preset]) => ({
    value,
    label: preset.name,
  })),
  { value: "custom", label: "Custom JSON Schema" },
]

function ExtractWorkspace({ doc }: { doc: string | null }) {
  const documents = useResource(loadDocuments)
  const jobs = useResource(loadJobs, (items) => items.some(extractionIsPending))
  const [documentId, setDocumentId] = useState(doc ?? "")
  const [preset, setPreset] = useState("financial")
  const [schemaText, setSchemaText] = useState(() =>
    JSON.stringify(extractionPresets.financial.schema, null, 2)
  )
  const [tier, setTier] = useState<"standard" | "pro">("standard")
  const [pages, setPages] = useState("")
  const [cite, setCite] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [copied, setCopied] = useState(false)
  const [selectedJob, setSelectedJob] = useState<string | null>(null)
  const [removal, setRemoval] = useState<
    { kind: "clear" } | { kind: "single"; id: string } | null
  >(null)
  const [preview, setPreview] = useState<{
    docId: string
    page: number
  } | null>(null)
  const request = useRef<{ signature: string; key: string } | null>(null)

  const ready = (documents.data ?? []).filter((item) => item.status === "ready")
  const docItems = ready.map((item) => ({
    value: item.doc_id,
    label: item.filename,
  }))
  const target =
    ready.find((item) => item.doc_id === documentId)?.doc_id ??
    (doc ? "" : (ready[0]?.doc_id ?? ""))
  const current = (jobs.data ?? []).find((item) => item.id === selectedJob)
  const source = documents.data?.find(
    (item) => item.id === current?.document_id && item.status === "ready"
  )
  const result =
    current?.result == null ? null : JSON.stringify(current.result, null, 2)

  async function extract(event: FormEvent) {
    event.preventDefault()
    if (!target || busy) return
    setError("")
    let schema: Record<string, unknown>
    try {
      const value = JSON.parse(schemaText)
      if (
        !value ||
        Array.isArray(value) ||
        !["object", "array"].includes(value.type)
      )
        throw new Error()
      schema = value
    } catch {
      setError("Enter a JSON Schema with a top-level object or array type.")
      return
    }
    const body = {
      document: target,
      schema,
      tier,
      pages: pages.trim() || undefined,
      cite_sources: cite,
      schema_name: extractionPresets[preset]?.name ?? "Custom schema",
    }
    const signature = JSON.stringify(body)
    if (request.current?.signature !== signature)
      request.current = { signature, key: crypto.randomUUID() }
    setBusy(true)
    try {
      const job = await api.extract.extract(body, request.current.key)
      jobs.setData((previous) => [
        job,
        ...(previous ?? []).filter((item) => item.id !== job.id),
      ])
      setSelectedJob(job.id)
      request.current = null
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  async function copyResult() {
    if (result === null) return
    try {
      await navigator.clipboard.writeText(result)
      setCopied(true)
    } catch {
      setError("Could not copy the result. Use Download JSON instead.")
    }
  }

  function download() {
    if (result === null) return
    const url = URL.createObjectURL(
      new Blob([result], { type: "application/json" })
    )
    const link = document.createElement("a")
    link.href = url
    link.download = "pageindex-extraction.json"
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <WorkspacePanel>
      <PageHeader
        title="Extract data"
        description="Turn fields or tables from a PDF into reusable JSON."
      />
      {(error || documents.error || jobs.error) && (
        <ErrorNotice>{error || documents.error || jobs.error}</ErrorNotice>
      )}
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(20rem,1fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <CardTitle>New extraction</CardTitle>
            <CardDescription>
              Choose a PDF and describe the fields to extract.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={extract}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="extract-source">PDF</FieldLabel>
                  <Select
                    value={target || null}
                    items={docItems}
                    onValueChange={(value) => {
                      if (value) setDocumentId(value)
                    }}
                    disabled={busy || !ready.length}
                  >
                    <SelectTrigger id="extract-source">
                      <SelectValue placeholder="Choose an indexed PDF" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {docItems.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  {!ready.length && !documents.loading && (
                    <FieldDescription>
                      Upload a PDF and wait for it to finish indexing.
                    </FieldDescription>
                  )}
                </Field>
                <Field>
                  <FieldLabel htmlFor="schema-preset">Schema preset</FieldLabel>
                  <Select
                    value={preset}
                    items={presetItems}
                    onValueChange={(value) => {
                      if (!value) return
                      setPreset(value)
                      if (extractionPresets[value])
                        setSchemaText(
                          JSON.stringify(
                            extractionPresets[value].schema,
                            null,
                            2
                          )
                        )
                    }}
                    disabled={busy}
                  >
                    <SelectTrigger id="schema-preset">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {presetItems.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
                <Field>
                  <FieldLabel htmlFor="extract-schema">JSON Schema</FieldLabel>
                  <Textarea
                    id="extract-schema"
                    variant="code"
                    spellCheck={false}
                    value={schemaText}
                    onChange={(event) => {
                      setSchemaText(event.target.value)
                      setPreset("custom")
                    }}
                    disabled={busy}
                    required
                  />
                </Field>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor="extract-pages">Pages</FieldLabel>
                    <Input
                      id="extract-pages"
                      placeholder="All pages"
                      value={pages}
                      onChange={(event) => setPages(event.target.value)}
                      disabled={busy}
                    />
                    <FieldDescription>
                      For example, 3–9 as 3-9.
                    </FieldDescription>
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="extract-tier">Tier</FieldLabel>
                    <Select
                      value={tier}
                      items={tierItems}
                      disabled={busy}
                      onValueChange={(value) => {
                        if (value === "standard" || value === "pro")
                          setTier(value)
                      }}
                    >
                      <SelectTrigger id="extract-tier">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          {tierItems.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  </Field>
                </div>
                <Field orientation="horizontal">
                  <Checkbox
                    id="extract-citations"
                    checked={cite}
                    onCheckedChange={setCite}
                    disabled={busy}
                  />
                  <FieldLabel htmlFor="extract-citations">
                    Include source citations
                  </FieldLabel>
                </Field>
                <Button
                  className="self-start"
                  type="submit"
                  disabled={!target || busy}
                >
                  {busy ? (
                    <Spinner data-icon="inline-start" />
                  ) : (
                    <Table2Icon data-icon="inline-start" />
                  )}
                  {busy ? "Queuing…" : "Run extraction"}
                </Button>
              </FieldGroup>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Result</CardTitle>
            <CardDescription>
              Select an extraction to see its status and output.
            </CardDescription>
          </CardHeader>
          <CardContent className="min-w-0">
            {current ? (
              <div className="flex min-w-0 flex-col gap-4">
                <div className="flex flex-wrap items-center gap-2">
                  <ResourceStatus status={current.status} />
                  {current.usage?.credits != null && (
                    <Badge variant="secondary">
                      {current.usage.credits} credits
                    </Badge>
                  )}
                  <span className="text-sm text-muted-foreground">
                    {current.schema_name}
                  </span>
                </div>
                {current.processing_error && (
                  <ErrorNotice>
                    <ProcessingErrorText message={current.processing_error} />
                  </ErrorNotice>
                )}
                {extractionIsPending(current) && (
                  <p role="status" className="text-sm text-muted-foreground">
                    This job runs in the background. You can leave and return
                    later.
                  </p>
                )}
                {result !== null && (
                  <>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="outline" onClick={copyResult}>
                        <ClipboardIcon data-icon="inline-start" />
                        {copied ? "Copied" : "Copy JSON"}
                      </Button>
                      <Button variant="outline" onClick={download}>
                        <DownloadIcon data-icon="inline-start" />
                        Download JSON
                      </Button>
                    </div>
                    <pre className="max-h-120 overflow-auto rounded-lg border bg-muted p-4 text-xs">
                      <code>{result}</code>
                    </pre>
                    {source && current.extract_metadata?.field_metadata && (
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <h3 className="w-full font-medium">Source pages</h3>
                        {Object.entries(current.extract_metadata.field_metadata)
                          .filter(([, item]) => item.page)
                          .map(([field, item]) => (
                            <Button
                              key={field}
                              variant="outline"
                              size="sm"
                              title={field}
                              onClick={() =>
                                setPreview({
                                  docId: source.doc_id,
                                  page: item.page!,
                                })
                              }
                            >
                              Page {item.page}
                              <span className="max-w-28 truncate text-xs text-muted-foreground">
                                {field}
                              </span>
                            </Button>
                          ))}
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <Empty>
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <BracesIcon />
                  </EmptyMedia>
                  <EmptyTitle>No result selected</EmptyTitle>
                  <EmptyDescription>
                    Start an extraction or select a job below.
                  </EmptyDescription>
                </EmptyHeader>
              </Empty>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle>Extraction history</CardTitle>
            <CardDescription>
              Queued, active, and completed jobs
            </CardDescription>
          </div>
          {!!jobs.data?.length && (
            <Button
              variant="ghost"
              onClick={() => setRemoval({ kind: "clear" })}
            >
              Clear history
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {jobs.loading ? (
            <LoadingRows label="Loading extraction history" />
          ) : !jobs.data?.length ? (
            <p className="text-muted-foreground">No extraction jobs yet.</p>
          ) : (
            <ul className="divide-y">
              {jobs.data.map((job) => (
                <li
                  key={job.id}
                  className="flex min-w-0 items-center gap-2 py-2"
                >
                  <Button
                    variant={job.id === selectedJob ? "secondary" : "ghost"}
                    className="h-auto min-w-0 flex-1 justify-start py-2 text-left"
                    onClick={() => {
                      setSelectedJob(job.id)
                      setCopied(false)
                    }}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate">
                        {job.schema_name || "Extraction"}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {formatDate(job.created_at)}
                      </span>
                    </span>
                    <ResourceStatus status={job.status} />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Move ${job.schema_name || "extraction"} to trash`}
                    onClick={() => setRemoval({ kind: "single", id: job.id })}
                  >
                    <Trash2Icon />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      {removal && (
        <ConfirmAction
          title="Move extraction history to trash?"
          description="Jobs can be restored from Trash."
          action="Move to trash"
          onClose={() => setRemoval(null)}
          onConfirm={async () => {
            if (removal.kind === "clear") await api.extract.clearJobs()
            else await api.extract.deleteJob(removal.id)
            if (removal.kind === "clear" || removal.id === selectedJob)
              setSelectedJob(null)
            await jobs.refresh()
          }}
        />
      )}
      <CitationModal
        open={!!preview}
        onOpenChange={(open) => {
          if (!open) setPreview(null)
        }}
        docId={preview?.docId ?? null}
        initialPage={preview?.page}
      />
    </WorkspacePanel>
  )
}

function ExtractFromUrl() {
  const doc = useSearchParams().get("doc")
  return <ExtractWorkspace key={doc ?? "extract"} doc={doc} />
}

export default function ExtractPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading extraction" />}>
      <ExtractFromUrl />
    </Suspense>
  )
}

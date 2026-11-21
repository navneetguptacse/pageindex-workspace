"use client"

import Link from "next/link"
import { useState } from "react"
import {
  ArrowRightIcon,
  FileTextIcon,
  FolderOpenIcon,
  MessageSquareIcon,
  ScanSearchIcon,
  Table2Icon,
  UploadIcon,
  GaugeIcon,
} from "lucide-react"

import { api } from "@/lib/api"
import {
  formatDate,
  documentIsPending,
  extractionIsPending,
} from "@/lib/format"
import { useResource } from "@/hooks/use-resource"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { DocumentActions } from "@/components/document-actions"
import { DocumentChatCard } from "@/components/document-chat-card"
import { DocumentUpload } from "@/components/document-upload"
import {
  ErrorNotice,
  LoadingRows,
  PageHeader,
  ResourceStatus,
  WorkspacePanel,
} from "@/components/workspace-ui"

const workflows = [
  {
    href: "/chat",
    title: "Ask a question",
    description: "Get answers with links to the source pages.",
    icon: MessageSquareIcon,
    tone: "bg-discovery-surface text-discovery",
  },
  {
    href: "/search",
    title: "Find relevant pages",
    description: "Search across PDFs and compare page relevance.",
    icon: ScanSearchIcon,
    tone: "bg-accent text-accent-foreground",
  },
  {
    href: "/extract",
    title: "Extract data",
    description: "Turn document fields and tables into structured JSON.",
    icon: Table2Icon,
    tone: "bg-success-surface text-success",
  },
]

const loadDocuments = () => api.documents.list()
const loadJobs = () => api.extract.listJobs()

export default function DashboardPage() {
  const documents = useResource(loadDocuments, (items) =>
    items.some(documentIsPending)
  )
  const collections = useResource(api.collections.list)
  const extractions = useResource(loadJobs, (jobs) =>
    jobs.some(extractionIsPending)
  )
  const library = documents.data ?? []
  const jobs = extractions.data ?? []
  const [retryError, setRetryError] = useState("")
  const usage = useResource(api.workspace.usage)
  const error =
    retryError ||
    documents.error ||
    collections.error ||
    extractions.error ||
    usage.error

  return (
    <WorkspacePanel>
      <PageHeader
        title="Overview"
        description="Manage your PDFs and get answers grounded in the original pages."
        actions={
          <DocumentUpload
            onUpload={async (files, key) => {
              await api.documents.upload(files, undefined, key)
              await documents.refresh()
            }}
          >
            <Button>
              <UploadIcon data-icon="inline-start" />
              Upload PDFs
            </Button>
          </DocumentUpload>
        }
      />

      {error && <ErrorNotice>{error}</ErrorNotice>}

      <DocumentChatCard />

      <section
        aria-label="Library summary"
        className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"
      >
        {[
          {
            label: "Documents",
            value: documents.data?.length,
            helper: `${library.filter((item) => item.status === "ready").length} ready`,
            icon: FileTextIcon,
          },
          {
            label: "Collections",
            value: collections.data?.length,
            helper: "Document groups",
            icon: FolderOpenIcon,
          },
          {
            label: "Extractions",
            value: extractions.data?.length,
            helper: `${jobs.filter((item) => item.status === "completed").length} completed`,
            icon: Table2Icon,
          },
          {
            label: "Chat tokens today",
            value: usage.data?.chat_tokens,
            helper:
              usage.data?.chat_token_limit != null
                ? `of ${usage.data.chat_token_limit.toLocaleString()}`
                : "UTC",
            icon: GaugeIcon,
          },
        ].map(({ label, value, helper, icon: Icon }) => (
          <Card key={label}>
            <CardContent className="flex items-center gap-4 px-4 py-1">
              <div className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground">
                <Icon className="size-5" aria-hidden="true" />
              </div>
              <div>
                <div className="text-xs font-medium text-muted-foreground">
                  {label}
                </div>
                <span className="mr-2 text-xl font-semibold tabular-nums">
                  {value?.toLocaleString() ?? "—"}
                </span>
                {value != null && (
                  <span className="text-xs text-muted-foreground">
                    {helper}
                  </span>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </section>

      <section aria-labelledby="tools-title" className="flex flex-col gap-3">
        <h2 id="tools-title" className="text-base font-semibold">
          Tools
        </h2>
        <div className="grid gap-3 md:grid-cols-3">
          {workflows.map(({ href, title, description, icon: Icon, tone }) => (
            <Link
              key={href}
              href={href}
              className="group flex min-w-0 items-start gap-3 rounded-lg border bg-card p-4 transition-colors hover:border-primary/45 hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <span
                className={`grid size-9 shrink-0 place-items-center rounded-lg ${tone}`}
              >
                <Icon className="size-4" aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-semibold">{title}</span>
                <span className="mt-1 block text-sm leading-snug text-muted-foreground">
                  {description}
                </span>
              </span>
              <ArrowRightIcon
                className="mt-1 size-4 shrink-0 text-muted-foreground group-hover:text-primary"
                aria-hidden="true"
              />
            </Link>
          ))}
        </div>
      </section>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle>Recent documents</CardTitle>
            <CardDescription>Latest PDFs in your library</CardDescription>
          </div>
          <Button variant="ghost" size="sm" render={<Link href="/documents" />}>
            View library
            <ArrowRightIcon data-icon="inline-end" />
          </Button>
        </CardHeader>
        <CardContent>
          {documents.loading ? (
            <LoadingRows label="Loading documents" />
          ) : library.length === 0 ? (
            <Empty className="border">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <FileTextIcon />
                </EmptyMedia>
                <EmptyTitle>No PDFs yet</EmptyTitle>
                <EmptyDescription>
                  Upload a PDF to make it searchable.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ul className="divide-y">
              {library.slice(0, 5).map((file) => (
                <li
                  key={file.id}
                  className="flex min-w-0 items-center justify-between gap-3 py-3"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <FileTextIcon
                      className="size-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <div
                        className="truncate font-medium"
                        title={file.filename}
                      >
                        {file.filename}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {formatDate(file.uploaded_at)}
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <ResourceStatus status={file.status} />
                    <DocumentActions
                      file={file}
                      onRetryError={setRetryError}
                      onUpdated={(updated) => {
                        documents.setData((items) =>
                          items?.map((item) =>
                            item.id === updated.id ? updated : item
                          )
                        )
                        void documents.refresh()
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </WorkspacePanel>
  )
}

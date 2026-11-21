"use client"

import { Suspense, useState, type FormEvent } from "react"
import { useSearchParams } from "next/navigation"
import { FileTextIcon, ScanSearchIcon, SearchIcon } from "lucide-react"

import { api, errorMessage, type SearchResponse } from "@/lib/api"
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
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Badge } from "@/components/ui/badge"
import { Spinner } from "@/components/ui/spinner"
import { CitationModal } from "@/components/citation-modal"
import {
  ErrorNotice,
  LoadingRows,
  PageHeader,
  WorkspacePanel,
} from "@/components/workspace-ui"

const loadDocuments = () => api.documents.list()
const pageLimits = [3, 5, 10].map((value) => ({
  value: String(value),
  label: String(value),
}))

function SearchWorkspace({ doc }: { doc: string | null }) {
  const documents = useResource(loadDocuments)
  const collections = useResource(api.collections.list)
  const [scope, setScope] = useState(doc ? `document:${doc}` : "library")
  const [questions, setQuestions] = useState("")
  const [topK, setTopK] = useState("5")
  const [includeText, setIncludeText] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [results, setResults] = useState<SearchResponse | null>(null)
  const [preview, setPreview] = useState<{
    docId: string
    page: number
  } | null>(null)

  const scopes = [
    { value: "library", label: "All documents" },
    ...(documents.data ?? [])
      .filter((item) => item.status === "ready")
      .map((item) => ({
        value: `document:${item.doc_id}`,
        label: item.filename,
      })),
    ...(collections.data ?? []).map((collection) => ({
      value: `collection:${collection.id}`,
      label: `Collection: ${collection.name}`,
    })),
  ]

  async function submit(event: FormEvent) {
    event.preventDefault()
    const entries = questions
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean)
    if (entries.length > 10 || entries.length === 0) {
      setError("Enter between 1 and 10 questions, one per line.")
      return
    }
    setBusy(true)
    setError("")
    try {
      setResults(
        await api.search.search({
          questions: entries,
          document: scope.startsWith("document:") ? scope.slice(9) : undefined,
          collection: scope.startsWith("collection:")
            ? scope.slice(11)
            : undefined,
          include_text: includeText,
          top_k: Number(topK),
        })
      )
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <WorkspacePanel>
      <PageHeader
        title="Search pages"
        description="Find relevant pages across one PDF, a collection, or your library."
      />
      {(error || documents.error || collections.error) && (
        <ErrorNotice>
          {error || documents.error || collections.error}
        </ErrorNotice>
      )}
      <Card className="max-w-4xl">
        <CardHeader>
          <CardTitle>Search query</CardTitle>
          <CardDescription>
            Enter up to 10 questions, one per line.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="queries">Questions</FieldLabel>
                <Textarea
                  id="queries"
                  rows={4}
                  placeholder="What were the main findings?"
                  value={questions}
                  disabled={busy}
                  onChange={(event) => setQuestions(event.target.value)}
                  maxLength={40000}
                  required
                />
              </Field>
              <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_10rem]">
                <Field>
                  <FieldLabel htmlFor="search-sources">Sources</FieldLabel>
                  <Select
                    value={scope}
                    items={scopes}
                    disabled={busy}
                    onValueChange={(value) => {
                      if (value) setScope(value)
                    }}
                  >
                    <SelectTrigger id="search-sources">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {scopes.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                </Field>
                <Field>
                  <FieldLabel htmlFor="page-limit">Pages per PDF</FieldLabel>
                  <Select
                    value={topK}
                    items={pageLimits}
                    disabled={busy}
                    onValueChange={(value) => {
                      if (value) setTopK(value)
                    }}
                  >
                    <SelectTrigger id="page-limit">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {pageLimits.map((item) => (
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
                  id="page-text"
                  checked={includeText}
                  onCheckedChange={setIncludeText}
                  disabled={busy}
                />
                <FieldLabel htmlFor="page-text">
                  Include page excerpts
                </FieldLabel>
              </Field>
              <Button
                type="submit"
                className="self-start"
                disabled={busy || !questions.trim()}
              >
                {busy ? (
                  <Spinner data-icon="inline-start" />
                ) : (
                  <SearchIcon data-icon="inline-start" />
                )}
                {busy ? "Searching…" : "Search"}
              </Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
      {busy ? (
        <LoadingRows label="Searching pages" />
      ) : results ? (
        <section
          aria-labelledby="results-title"
          className="flex flex-col gap-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-semibold" id="results-title">
              Results
            </h2>
            {typeof results.usage?.credits === "number" && (
              <Badge variant="secondary">{results.usage.credits} credits</Badge>
            )}
          </div>
          {results.results.map((result, index) => (
            <Card key={`${index}-${result.question}`}>
              <CardHeader>
                <CardTitle className="wrap-break-word">
                  {result.question}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                {result.documents.every((item) => item.pages.length === 0) ? (
                  <FieldDescription>
                    No relevant pages were found.
                  </FieldDescription>
                ) : (
                  result.documents.map((item) => (
                    <div
                      className="min-w-0 rounded-lg border"
                      key={item.doc_id}
                    >
                      <div className="flex min-w-0 items-center gap-2 border-b bg-muted px-3 py-2">
                        <FileTextIcon
                          className="size-4 shrink-0"
                          aria-hidden="true"
                        />
                        <h3 className="truncate font-medium">
                          {documents.data?.find(
                            (file) => file.doc_id === item.doc_id
                          )?.filename ?? item.doc_id}
                        </h3>
                      </div>
                      <ul className="divide-y">
                        {item.pages.map((page, index) => (
                          <li
                            key={`${page.page}-${index}`}
                            className="flex flex-col gap-2 px-3 py-3"
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() =>
                                  setPreview({
                                    docId: item.doc_id,
                                    page: page.page,
                                  })
                                }
                              >
                                Page {page.page}
                              </Button>
                              <Badge
                                variant={
                                  page.relevance >= 0.8
                                    ? "success"
                                    : "secondary"
                                }
                              >
                                {Math.round(page.relevance * 100)}% relevance
                              </Badge>
                            </div>
                            {page.text && (
                              <p className="line-clamp-4 text-sm wrap-break-word whitespace-pre-wrap text-muted-foreground">
                                {page.text}
                              </p>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          ))}
        </section>
      ) : (
        <Empty className="border">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ScanSearchIcon />
            </EmptyMedia>
            <EmptyTitle>Relevant pages appear here</EmptyTitle>
            <EmptyDescription>
              Run a search to compare matching pages and open the originals.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
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

function SearchFromUrl() {
  const doc = useSearchParams().get("doc")
  return <SearchWorkspace key={doc ?? "library"} doc={doc} />
}

export default function SearchPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading search" />}>
      <SearchFromUrl />
    </Suspense>
  )
}

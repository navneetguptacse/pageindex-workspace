"use client"

import Link from "next/link"
import { useCallback, useMemo, useState, type FormEvent } from "react"
import {
  FileTextIcon,
  FolderPlusIcon,
  SearchIcon,
  UploadIcon,
} from "lucide-react"

import { api, errorMessage, type Document } from "@/lib/api"
import { documentIsPending, formatBytes, formatDate } from "@/lib/format"
import { useResource } from "@/hooks/use-resource"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { InputGroup, InputGroupAddon } from "@/components/ui/input-group"
import { Field, FieldLabel } from "@/components/ui/field"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { DropdownMenuItem } from "@/components/ui/dropdown-menu"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { DocumentActions } from "@/components/document-actions"
import { DocumentUpload } from "@/components/document-upload"
import { ConfirmAction } from "@/components/confirm-action"
import { CitationModal } from "@/components/citation-modal"
import {
  ErrorNotice,
  LoadingRows,
  PageHeader,
  ResourceStatus,
  WorkspacePanel,
} from "@/components/workspace-ui"

export default function DocumentsPage() {
  const [collectionId, setCollectionId] = useState("all")
  const [query, setQuery] = useState("")
  const [retryError, setRetryError] = useState("")
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState("")
  const [deleteDocument, setDeleteDocument] = useState<Document | null>(null)
  const [deleteCollection, setDeleteCollection] = useState(false)
  const [preview, setPreview] = useState<Document | null>(null)
  const documents = useResource(
    useCallback(() => api.documents.list(), []),
    (items) => items.some(documentIsPending)
  )
  const collections = useResource(api.collections.list)
  const collection = collections.data?.find((item) => item.id === collectionId)
  const collectionItems = [
    { value: "all", label: "All documents" },
    ...(collections.data ?? []).map((item) => ({
      value: item.id,
      label: item.name,
    })),
  ]
  const visible = useMemo(
    () =>
      (documents.data ?? []).filter(
        (item) =>
          (collectionId === "all" || item.collection_id === collectionId) &&
          item.filename.toLowerCase().includes(query.trim().toLowerCase())
      ),
    [documents.data, query, collectionId]
  )

  async function createCollection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = String(new FormData(event.currentTarget).get("name")).trim()
    if (!name) return
    setCreating(true)
    setCreateError("")
    try {
      const result = await api.collections.create(name)
      await collections.refresh()
      setCollectionId(result.id)
      setCreateOpen(false)
    } catch (error) {
      setCreateError(errorMessage(error))
    } finally {
      setCreating(false)
    }
  }

  return (
    <WorkspacePanel>
      <PageHeader
        title="Documents"
        description="Upload PDFs, organize collections, and open source pages."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => {
                setCreateError("")
                setCreateOpen(true)
              }}
            >
              <FolderPlusIcon data-icon="inline-start" />
              New collection
            </Button>
            <DocumentUpload
              onUpload={async (files, key) => {
                await api.documents.upload(files, collection?.id, key)
                await documents.refresh()
              }}
            >
              <Button>
                <UploadIcon data-icon="inline-start" />
                Upload PDFs
              </Button>
            </DocumentUpload>
          </>
        }
      />
      {(retryError || documents.error || collections.error) && (
        <ErrorNotice>
          {retryError || documents.error || collections.error}
        </ErrorNotice>
      )}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <InputGroup className="w-full sm:max-w-80">
          <InputGroupAddon aria-hidden="true">
            <SearchIcon />
          </InputGroupAddon>
          <Input
            appearance="grouped"
            type="search"
            aria-label="Filter documents"
            placeholder="Filter by filename"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </InputGroup>
        <Select
          items={collectionItems}
          value={collectionId}
          onValueChange={(value) => {
            if (value) setCollectionId(value)
          }}
        >
          <SelectTrigger
            className="sm:max-w-64"
            aria-label="Filter by collection"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              {collectionItems.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        {collection && (
          <Button
            variant="ghost"
            className="self-start sm:ml-auto"
            onClick={() => setDeleteCollection(true)}
          >
            Delete collection
          </Button>
        )}
      </div>
      <Card className="py-0">
        {documents.loading ? (
          <CardContent className="p-4">
            <LoadingRows label="Loading document library" />
          </CardContent>
        ) : visible.length === 0 ? (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <FileTextIcon />
              </EmptyMedia>
              <EmptyTitle>
                {query ? "No matching documents" : "No PDFs here yet"}
              </EmptyTitle>
              <EmptyDescription>
                {query
                  ? "Try another filename."
                  : "Upload a PDF to start indexing."}
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <>
            <div
              className="hidden grid-cols-[minmax(0,1fr)_7rem_8rem_6rem_2.5rem] items-center gap-3 border-b bg-muted px-4 py-2.5 text-xs font-semibold text-muted-foreground md:grid"
              aria-hidden="true"
            >
              <span>Filename</span>
              <span>Status</span>
              <span>Uploaded</span>
              <span>Size</span>
              <span />
            </div>
            <ul className="divide-y">
              {visible.map((file) => (
                <li
                  key={file.id}
                  className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 px-3 py-3 md:grid-cols-[minmax(0,1fr)_7rem_8rem_6rem_2.5rem] md:gap-3 md:px-4"
                >
                  <div className="flex min-w-0 items-start gap-2.5">
                    <FileTextIcon
                      className="mt-0.5 size-4 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <div
                        className="truncate font-medium"
                        title={file.filename}
                      >
                        {file.filename}
                      </div>
                      <div className="text-xs text-muted-foreground md:hidden">
                        {formatDate(file.uploaded_at)} ·{" "}
                        {formatBytes(file.file_size)}
                      </div>
                      {file.processing_error && (
                        <div className="text-xs text-destructive">
                          {file.processing_error}
                        </div>
                      )}
                    </div>
                  </div>
                  <ResourceStatus status={file.status} />
                  <time
                    className="hidden text-xs text-muted-foreground md:block"
                    dateTime={file.uploaded_at}
                  >
                    {formatDate(file.uploaded_at)}
                  </time>
                  <span className="hidden text-xs text-muted-foreground md:block">
                    {formatBytes(file.file_size)}
                  </span>
                  <DocumentActions
                    file={file}
                    onTrash={() => setDeleteDocument(file)}
                    onRetryError={setRetryError}
                    onUpdated={(updated) => {
                      documents.setData((items) =>
                        items?.map((item) =>
                          item.id === updated.id ? updated : item
                        )
                      )
                      void documents.refresh()
                    }}
                  >
                    {file.status === "ready" && (
                      <>
                        <DropdownMenuItem onClick={() => setPreview(file)}>
                          Open preview
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          render={
                            <Link
                              href={`/chat?doc=${encodeURIComponent(file.doc_id)}`}
                            />
                          }
                        >
                          Ask about this PDF
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          render={
                            <Link
                              href={`/search?doc=${encodeURIComponent(file.doc_id)}`}
                            />
                          }
                        >
                          Search pages
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          render={
                            <Link
                              href={`/extract?doc=${encodeURIComponent(file.doc_id)}`}
                            />
                          }
                        >
                          Extract data
                        </DropdownMenuItem>
                      </>
                    )}
                  </DocumentActions>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
      <Dialog
        open={createOpen}
        onOpenChange={(open) => {
          if (!creating) setCreateOpen(open)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New collection</DialogTitle>
            <DialogDescription>
              Group related PDFs for search and chat.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={createCollection} className="flex flex-col gap-4">
            {createError && <ErrorNotice>{createError}</ErrorNotice>}
            <Field>
              <FieldLabel htmlFor="collection-name">Collection name</FieldLabel>
              <Input
                id="collection-name"
                name="name"
                maxLength={200}
                required
              />
            </Field>
            <DialogFooter>
              <Button
                variant="ghost"
                disabled={creating}
                onClick={() => setCreateOpen(false)}
              >
                Cancel
              </Button>
              <Button disabled={creating} type="submit">
                {creating ? "Creating…" : "Create collection"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      {deleteDocument && (
        <ConfirmAction
          title="Move PDF to trash?"
          description={`${deleteDocument.filename} can be restored from Trash.`}
          action="Move to trash"
          onClose={() => setDeleteDocument(null)}
          onConfirm={async () => {
            await api.documents.delete(deleteDocument.id)
            await documents.refresh()
          }}
        />
      )}
      {deleteCollection && collection && (
        <ConfirmAction
          title="Permanently delete collection?"
          description={`Deleting ${collection.name} also deletes the PDFs and conversations in the collection.`}
          action="Delete collection"
          onClose={() => setDeleteCollection(false)}
          onConfirm={async () => {
            await api.collections.delete(collection.id)
            setCollectionId("all")
            await Promise.all([documents.refresh(), collections.refresh()])
          }}
        />
      )}
      <CitationModal
        open={!!preview}
        onOpenChange={(open) => {
          if (!open) setPreview(null)
        }}
        docId={preview?.doc_id ?? null}
      />
    </WorkspacePanel>
  )
}

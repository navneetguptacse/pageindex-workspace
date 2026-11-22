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
import { Checkbox } from "@/components/ui/checkbox"
import { Card, CardContent } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
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
import { CollectionPicker } from "@/components/collection-picker"
import { DocumentActions } from "@/components/document-actions"
import { DocumentUpload } from "@/components/document-upload"
import { ConfirmAction } from "@/components/confirm-action"
import { CitationModal } from "@/components/citation-modal"
import {
  ErrorNotice,
  LoadingRows,
  PageHeader,
  ProcessingErrorText,
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
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [bulkTrash, setBulkTrash] = useState<string[]>([])
  const [moveOpen, setMoveOpen] = useState(false)
  const [destination, setDestination] = useState<string | null>(null)
  const [moving, setMoving] = useState(false)
  const [moveError, setMoveError] = useState("")
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

  const chosen = visible.filter((file) => selected.has(file.id))
  const hasPendingSelection = chosen.some(documentIsPending)
  const canChooseDestination =
    collectionItems.length > 1 ||
    chosen.some((file) => file.collection_id != null)

  function selectCollection(id: string) {
    setCollectionId(id)
    setSelected(new Set())
  }

  function toggleDocument(id: string, checked: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      if (checked) next.add(id)
      else next.delete(id)
      return next
    })
  }

  async function moveSelected(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setMoveError("")
    setMoving(true)
    try {
      await api.documents.moveSelection(
        chosen.map(({ id }) => id),
        destination
      )
      setSelected(new Set())
      setMoveOpen(false)
      await documents.refresh()
    } catch (error) {
      setMoveError(errorMessage(error))
    } finally {
      setMoving(false)
    }
  }

  async function createCollection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = String(new FormData(event.currentTarget).get("name")).trim()
    if (!name) return
    setCreating(true)
    setCreateError("")
    try {
      const result = await api.collections.create(name)
      await collections.refresh()
      selectCollection(result.id)
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
              collections={collections.data ?? []}
              defaultCollectionId={collection?.id}
              onUpload={async (files, key, destination) => {
                await api.documents.upload(files, destination ?? undefined, key)
                selectCollection(destination ?? "all")
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
            onChange={(event) => {
              setQuery(event.target.value)
              setSelected(new Set())
            }}
          />
        </InputGroup>
        <Select
          items={collectionItems}
          value={collectionId}
          onValueChange={(value) => {
            if (value) selectCollection(value)
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
      {chosen.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span role="status" className="text-sm text-muted-foreground">
            {chosen.length} selected
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={hasPendingSelection || !canChooseDestination}
            onClick={() => {
              setMoveError("")
              setDestination(chosen[0]?.collection_id ?? null)
              setMoveOpen(true)
            }}
          >
            Move
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setBulkTrash(chosen.map(({ id }) => id))}
          >
            Trash
          </Button>
          {hasPendingSelection && (
            <span className="text-xs text-muted-foreground">
              Wait for indexing to finish before moving.
            </span>
          )}
        </div>
      )}
      <Card className="gap-0 py-0">
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
            <div className="grid grid-cols-[1rem_minmax(0,1fr)_auto_auto] items-center gap-2 border-b bg-muted px-3 py-2.5 text-xs font-semibold text-muted-foreground md:grid-cols-[1rem_minmax(0,1fr)_7rem_8rem_6rem_2.5rem] md:gap-3 md:px-4">
              <Checkbox
                id="select-visible-pdfs"
                aria-label="Select all visible PDFs"
                checked={chosen.length === visible.length}
                indeterminate={
                  chosen.length > 0 && chosen.length < visible.length
                }
                onCheckedChange={(checked) =>
                  setSelected(
                    new Set(checked ? visible.map(({ id }) => id) : [])
                  )
                }
              />
              <label
                htmlFor="select-visible-pdfs"
                className="col-span-3 md:hidden"
              >
                Select all
              </label>
              <span className="hidden md:block">Filename</span>
              <span className="hidden md:block">Status</span>
              <span className="hidden md:block">Uploaded</span>
              <span className="hidden md:block">Size</span>
              <span className="hidden md:block" />
            </div>
            <ul className="divide-y">
              {visible.map((file) => (
                <li
                  key={file.id}
                  className="grid min-w-0 grid-cols-[1rem_minmax(0,1fr)_auto_auto] items-center gap-2 px-3 py-3 md:grid-cols-[1rem_minmax(0,1fr)_7rem_8rem_6rem_2.5rem] md:gap-3 md:px-4"
                >
                  <Checkbox
                    aria-label={`Select ${file.filename}`}
                    checked={selected.has(file.id)}
                    onCheckedChange={(checked) =>
                      toggleDocument(file.id, checked)
                    }
                  />
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
                          <ProcessingErrorText
                            message={file.processing_error}
                          />
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
                    collections={collections.data ?? []}
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
                          Preview
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          render={
                            <Link
                              href={`/chat?doc=${encodeURIComponent(file.doc_id)}`}
                            />
                          }
                        >
                          Chat
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
                          Extract
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
                {creating ? "Creating…" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog
        open={moveOpen}
        onOpenChange={(open) => {
          if (!moving) setMoveOpen(open)
        }}
      >
        <DialogContent showCloseButton={!moving}>
          <DialogHeader>
            <DialogTitle>Move selected PDFs</DialogTitle>
            <DialogDescription>
              Choose a destination for {chosen.length} selected.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={moveSelected} className="grid gap-4">
            {moveError && <ErrorNotice>{moveError}</ErrorNotice>}
            <CollectionPicker
              id="bulk-move-collection"
              collections={collections.data ?? []}
              value={destination}
              onChange={setDestination}
              disabled={moving}
            />
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={moving}
                onClick={() => setMoveOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={
                  moving ||
                  !chosen.length ||
                  chosen.every(
                    (file) => (file.collection_id ?? null) === destination
                  )
                }
              >
                {moving && <Spinner data-icon="inline-start" />}
                Move
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      {bulkTrash.length > 0 && (
        <ConfirmAction
          title={`Move ${bulkTrash.length} selected to Trash?`}
          description="You can restore these PDFs from Trash."
          action="Move to trash"
          onClose={() => setBulkTrash([])}
          onConfirm={async () => {
            await api.documents.trashSelection(bulkTrash)
            setSelected(new Set())
            await documents.refresh()
          }}
        />
      )}
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
          title="Move collection to Trash?"
          description={`${collection.name} and its PDFs can be restored from Trash. Collection conversations will be permanently deleted.`}
          action="Move to Trash"
          onClose={() => setDeleteCollection(false)}
          onConfirm={async () => {
            await api.collections.delete(collection.id)
            selectCollection("all")
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

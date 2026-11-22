"use client"

import { useRef, useState, type FormEvent, type ReactNode } from "react"
import { EllipsisIcon } from "lucide-react"

import { api, errorMessage, type Collection, type Document } from "@/lib/api"
import { CollectionPicker } from "@/components/collection-picker"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { ErrorNotice } from "@/components/workspace-ui"

export function DocumentActions({
  file,
  collections,
  onUpdated,
  onRetryError,
  onTrash,
  children,
}: {
  file: Document
  collections: Collection[]
  onUpdated: (document: Document) => void
  onRetryError: (error: string) => void
  onTrash?: () => void
  children?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [moveOpen, setMoveOpen] = useState(false)
  const [destination, setDestination] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [error, setError] = useState("")
  const trigger = useRef<HTMLButtonElement>(null)
  const input = useRef<HTMLInputElement>(null)

  async function rename(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const filename = String(new FormData(event.currentTarget).get("filename"))
    setError("")
    setSaving(true)
    try {
      onUpdated(await api.documents.rename(file.id, filename))
      setOpen(false)
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  async function move(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setSaving(true)
    try {
      onUpdated(await api.documents.move(file.id, destination))
      setMoveOpen(false)
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  async function retry() {
    setRetrying(true)
    onRetryError("")
    try {
      onUpdated(await api.documents.retry(file.id))
    } catch (error) {
      onRetryError(errorMessage(error))
    } finally {
      setRetrying(false)
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          ref={trigger}
          render={
            <Button
              size="icon-sm"
              variant="ghost"
              disabled={retrying}
              aria-label={`Actions for ${file.filename}`}
            />
          }
        >
          {retrying ? <Spinner /> : <EllipsisIcon />}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuGroup>
            {children}
            {children && <DropdownMenuSeparator />}
            <DropdownMenuItem
              onClick={() => {
                setError("")
                setOpen(true)
              }}
            >
              Rename
            </DropdownMenuItem>
            {(file.status === "ready" || file.status === "failed") &&
              (collections.length > 0 || file.collection_id) && (
                <DropdownMenuItem
                  onClick={() => {
                    setError("")
                    setDestination(file.collection_id ?? null)
                    setMoveOpen(true)
                  }}
                >
                  Move to collection
                </DropdownMenuItem>
              )}
            {file.status === "failed" && (
              <DropdownMenuItem onClick={retry}>Retry</DropdownMenuItem>
            )}
            {onTrash && (
              <DropdownMenuItem variant="destructive" onClick={onTrash}>
                Move to trash
              </DropdownMenuItem>
            )}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!saving) setOpen(next)
        }}
      >
        <DialogContent
          initialFocus={input}
          finalFocus={trigger}
          showCloseButton={!saving}
        >
          <DialogHeader>
            <DialogTitle>Rename PDF</DialogTitle>
            <DialogDescription>
              Choose a new name for this document.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={rename} className="flex flex-col gap-4">
            {error && <ErrorNotice>{error}</ErrorNotice>}
            <Field>
              <FieldLabel htmlFor={`document-name-${file.id}`}>
                PDF name
              </FieldLabel>
              <Input
                key={file.filename}
                ref={input}
                id={`document-name-${file.id}`}
                name="filename"
                defaultValue={file.filename}
                required
                maxLength={200}
                disabled={saving}
              />
            </Field>
            <DialogFooter>
              <DialogClose
                render={
                  <Button type="button" variant="outline" disabled={saving} />
                }
              >
                Cancel
              </DialogClose>
              <Button type="submit" disabled={saving}>
                {saving && <Spinner data-icon="inline-start" />}
                Save name
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog
        open={moveOpen}
        onOpenChange={(next) => {
          if (!saving) setMoveOpen(next)
        }}
      >
        <DialogContent finalFocus={trigger} showCloseButton={!saving}>
          <DialogHeader>
            <DialogTitle>Move PDF</DialogTitle>
            <DialogDescription>{file.filename}</DialogDescription>
          </DialogHeader>
          <form onSubmit={move} className="flex flex-col gap-4">
            {error && <ErrorNotice>{error}</ErrorNotice>}
            <CollectionPicker
              id={`move-collection-${file.id}`}
              collections={collections}
              value={destination}
              onChange={setDestination}
              disabled={saving}
            />
            <DialogFooter>
              <DialogClose
                render={
                  <Button type="button" variant="outline" disabled={saving} />
                }
              >
                Cancel
              </DialogClose>
              <Button
                type="submit"
                disabled={
                  saving || destination === (file.collection_id ?? null)
                }
              >
                {saving && <Spinner data-icon="inline-start" />}
                Move
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}

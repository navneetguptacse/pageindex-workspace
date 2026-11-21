"use client"

import { useRef, useState, type DragEvent, type ReactElement } from "react"
import { FileTextIcon, UploadCloudIcon, XIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Spinner } from "@/components/ui/spinner"
import { ErrorNotice } from "@/components/workspace-ui"
import { errorMessage } from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"

export function DocumentUpload({
  onUpload,
  children,
}: {
  onUpload: (files: File[], idempotencyKey: string) => Promise<unknown>
  children: ReactElement
}) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState("")
  const input = useRef<HTMLInputElement>(null)
  const requestKey = useRef<string | null>(null)

  function addFiles(picked: FileList) {
    const additions = Array.from(picked)
    if (additions.some((file) => !file.name.toLowerCase().endsWith(".pdf"))) {
      setError("Choose PDF files.")
      return
    }
    if (files.length + additions.length > 10) {
      setError("Choose up to 10 PDFs per upload.")
      return
    }
    requestKey.current = null
    setFiles([...files, ...additions])
    setError("")
  }

  function drop(event: DragEvent) {
    event.preventDefault()
    setDragging(false)
    if (!uploading && event.dataTransfer.files.length)
      addFiles(event.dataTransfer.files)
  }

  async function upload() {
    if (!files.length || uploading) return
    setUploading(true)
    setError("")
    try {
      requestKey.current ??= crypto.randomUUID()
      await onUpload(files, requestKey.current)
      setOpen(false)
      setFiles([])
      requestKey.current = null
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setUploading(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (uploading) return
        setOpen(next)
        if (!next) {
          setFiles([])
          setError("")
          requestKey.current = null
        }
      }}
    >
      <DialogTrigger render={children} />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload PDFs</DialogTitle>
          <DialogDescription>
            Choose up to 10 PDFs. Indexing continues after you close this
            window.
          </DialogDescription>
        </DialogHeader>
        {error && <ErrorNotice>{error}</ErrorNotice>}
        <div
          className={cn(
            "flex flex-col items-center gap-3 rounded-lg border border-dashed bg-muted p-6 text-center",
            dragging && "border-primary bg-accent"
          )}
          onDrop={drop}
          onDragOver={(event) => {
            event.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
        >
          <UploadCloudIcon className="size-7 text-primary" aria-hidden="true" />
          <p className="text-sm font-medium">Drop PDFs here or choose files</p>
          <Button
            variant="outline"
            onClick={() => input.current?.click()}
            disabled={uploading}
          >
            Choose files
          </Button>
          <input
            ref={input}
            type="file"
            multiple
            accept=".pdf,application/pdf"
            hidden
            onChange={(event) => {
              if (event.target.files?.length) addFiles(event.target.files)
              event.target.value = ""
            }}
          />
        </div>
        {files.length > 0 && (
          <ul
            className="max-h-40 divide-y overflow-auto"
            aria-label="Selected PDFs"
          >
            {files.map((file, index) => (
              <li
                className="flex min-w-0 items-center gap-2 py-1"
                key={`${index}-${file.name}`}
              >
                <FileTextIcon
                  className="size-4 shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1 truncate" title={file.name}>
                  {file.name}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {formatBytes(file.size)}
                </span>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  disabled={uploading}
                  aria-label={`Remove ${file.name}`}
                  onClick={() => {
                    requestKey.current = null
                    setFiles(files.filter((_, item) => index !== item))
                  }}
                >
                  <XIcon />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <DialogFooter>
          <Button
            variant="ghost"
            disabled={uploading}
            onClick={() => setOpen(false)}
          >
            Cancel
          </Button>
          <Button onClick={upload} disabled={!files.length || uploading}>
            {uploading && <Spinner data-icon="inline-start" />}
            {uploading ? "Uploading…" : "Upload PDFs"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

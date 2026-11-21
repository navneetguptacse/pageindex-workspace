"use client"

import { useEffect, useState } from "react"
import Image from "next/image"
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  ExternalLinkIcon,
  MinusIcon,
  PlusIcon,
} from "lucide-react"

import { api, errorMessage, type PagePreview } from "@/lib/api"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ErrorNotice, LoadingRows } from "@/components/workspace-ui"

type ReferenceProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  docId: string | null
  initialPage?: number
}

function ReferencePage({
  docId,
  initialPage,
}: {
  docId: string
  initialPage: number
}) {
  const [page, setPage] = useState(initialPage)
  const [loaded, setLoaded] = useState<{
    page: number
    preview?: PagePreview
    error?: string
  }>()
  const [failedImage, setFailedImage] = useState<number>()
  const [zoom, setZoom] = useState(100)
  const requested = loaded?.page === page ? loaded : undefined
  const preview = requested?.preview
  const image = preview?.image_url

  useEffect(() => {
    const controller = new AbortController()
    api.documents.getPagePreview(docId, page, controller.signal).then(
      (preview) => setLoaded({ page, preview }),
      (error: unknown) => {
        if (!controller.signal.aborted)
          setLoaded({ page, error: errorMessage(error) })
      }
    )
    return () => controller.abort()
  }, [docId, page])

  return (
    <>
      <DialogHeader>
        <DialogTitle className="pr-7 break-words">
          {preview?.filename ?? "Source PDF"}
        </DialogTitle>
        <DialogDescription>
          View and verify the original page.
        </DialogDescription>
      </DialogHeader>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button
            size="icon-sm"
            variant="outline"
            aria-label="Previous page"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeftIcon />
          </Button>
          <span aria-live="polite" className="text-sm tabular-nums">
            Page {page}
            {preview ? ` of ${preview.total_pages}` : ""}
          </span>
          <Button
            size="icon-sm"
            variant="outline"
            aria-label="Next page"
            disabled={!preview || page >= preview.total_pages}
            onClick={() => setPage(page + 1)}
          >
            <ChevronRightIcon />
          </Button>
        </div>
        {image && (
          <Button
            size="sm"
            variant="outline"
            render={<a href={image} target="_blank" rel="noreferrer" />}
          >
            Open image
            <ExternalLinkIcon data-icon="inline-end" />
          </Button>
        )}
      </div>
      {!requested ? (
        <LoadingRows label="Loading PDF page" />
      ) : requested.error ? (
        <ErrorNotice>{requested.error}</ErrorNotice>
      ) : (
        <Tabs defaultValue="page" className="min-w-0">
          <TabsList>
            <TabsTrigger value="page">Page image</TabsTrigger>
            <TabsTrigger value="text">Extracted text</TabsTrigger>
          </TabsList>
          <TabsContent value="page" className="flex min-w-0 flex-col gap-2">
            {image && failedImage !== page ? (
              <>
                <div className="flex items-center gap-2" aria-label="Page zoom">
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    disabled={zoom <= 75}
                    aria-label="Zoom out"
                    onClick={() => setZoom(zoom - 25)}
                  >
                    <MinusIcon />
                  </Button>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {zoom}%
                  </span>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    disabled={zoom >= 200}
                    aria-label="Zoom in"
                    onClick={() => setZoom(zoom + 25)}
                  >
                    <PlusIcon />
                  </Button>
                </div>
                <div className="max-h-[54dvh] overflow-auto rounded-lg border bg-muted p-2">
                  <Image
                    key={image}
                    src={image}
                    unoptimized
                    width={1200}
                    height={1600}
                    alt={`Page ${page} of ${preview?.filename ?? "the PDF"}`}
                    className="h-auto max-w-none rounded-sm bg-white"
                    style={{ width: `${zoom}%` }}
                    onError={() => setFailedImage(page)}
                  />
                </div>
              </>
            ) : (
              <p className="rounded-lg border bg-muted p-4 text-muted-foreground">
                Image unavailable. The extracted text may still be available.
              </p>
            )}
          </TabsContent>
          <TabsContent value="text">
            <div className="max-h-[54dvh] overflow-auto rounded-lg border bg-muted p-4">
              <p className="wrap-break-word whitespace-pre-wrap">
                {preview?.text || "No text was extracted for this page."}
              </p>
            </div>
          </TabsContent>
        </Tabs>
      )}
    </>
  )
}

export function CitationModal({
  open,
  onOpenChange,
  docId,
  initialPage = 1,
}: ReferenceProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        {open && docId ? (
          <ReferencePage
            key={`${docId}:${initialPage}`}
            docId={docId}
            initialPage={initialPage}
          />
        ) : (
          <DialogHeader>
            <DialogTitle>Source PDF</DialogTitle>
            <DialogDescription>No PDF is selected.</DialogDescription>
          </DialogHeader>
        )}
      </DialogContent>
    </Dialog>
  )
}

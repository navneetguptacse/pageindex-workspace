"use client"

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { FileTextIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { type Citation } from "@/lib/api"

interface CitationViewerProps {
  citations: Citation[]
  onCitationClick?: (cite: { doc?: string; page: number }) => void
}

export function CitationViewer({
  citations,
  onCitationClick,
}: CitationViewerProps) {
  if (!citations || citations.length === 0) return null

  return (
    <div className="flex flex-wrap gap-1.5">
      {citations.map((citation, index) => {
        const pageNum = typeof citation.page === "number" ? citation.page : 1
        const docName = citation.doc_id || citation.document || undefined

        return (
          <Tooltip key={index}>
            <TooltipTrigger
              onClick={() => {
                if (onCitationClick) {
                  onCitationClick({
                    page: pageNum,
                    doc: docName,
                  })
                }
              }}
              render={<Button variant="citation" size="xs" />}
            >
              <FileTextIcon data-icon="inline-start" />
              Page {pageNum}
            </TooltipTrigger>
            <TooltipContent className="max-w-sm text-xs">
              <p>
                {citation.text || `Click to view reference on Page ${pageNum}`}
              </p>
            </TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}

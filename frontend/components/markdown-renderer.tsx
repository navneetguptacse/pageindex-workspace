"use client"

import Markdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { FileTextIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import type { Citation } from "@/lib/api"

type SourceReference = { doc?: string; page: number }
const citePattern =
  /<cite\b([^>]*?)\/?>(?:<\/cite>)?|<doc=([^;>]+);page=(\d+)[^>]*>|\[source\s+(\d+)\]/gi
const citationPrefix = "#pageindex-reference-"

function attribute(text: string, name: string) {
  const match = text.match(
    new RegExp(`(?:^|\\s)${name}=(?:"([^"]+)"|'([^']+)'|([^\\s/>]+))`, "i")
  )
  return match?.[1] ?? match?.[2] ?? match?.[3]
}

export function MarkdownRenderer({
  content,
  sources,
  onCitationClick,
}: {
  content: string
  sources?: Citation[] | null
  onCitationClick?: (citation: SourceReference) => void
}) {
  const references: SourceReference[] = []
  const markdown = content.replace(
    citePattern,
    (
      _match: string,
      attributes?: string,
      legacyDoc?: string,
      legacyPage?: string,
      label?: string
    ) => {
      const source = label
        ? sources?.find((item) => item.label === Number(label))
        : undefined
      const doc =
        source?.doc_id ??
        (attributes ? attribute(attributes, "doc") : legacyDoc)
      const page =
        source?.page ??
        Number.parseInt(
          (attributes ? attribute(attributes, "page") : legacyPage) ?? "",
          10
        )
      if (!Number.isSafeInteger(page) || page < 1) return ""
      references.push({ doc, page })
      return `[Page ${page}](${citationPrefix}${references.length - 1})`
    }
  )

  return (
    <div className="flex min-w-0 flex-col gap-3 leading-relaxed wrap-break-word">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          a: ({ href, children }) => {
            const source = href?.startsWith(citationPrefix)
              ? references[Number(href.slice(citationPrefix.length))]
              : undefined
            if (source && onCitationClick)
              return (
                <Button
                  variant="citation"
                  size="xs"
                  className="mx-0.5 align-baseline"
                  onClick={() => onCitationClick(source)}
                >
                  <FileTextIcon data-icon="inline-start" />
                  {children}
                </Button>
              )
            if (!href || !/^https?:\/\//i.test(href))
              return <span>{children}</span>
            return (
              <a
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-primary underline underline-offset-2"
              >
                {children}
              </a>
            )
          },
          img: ({ alt }) => <span>{alt}</span>,
          h1: ({ children }) => (
            <h3 className="text-base font-semibold">{children}</h3>
          ),
          h2: ({ children }) => (
            <h3 className="text-base font-semibold">{children}</h3>
          ),
          h3: ({ children }) => <h3 className="font-semibold">{children}</h3>,
          ul: ({ children }) => <ul className="ms-5 list-disc">{children}</ul>,
          ol: ({ children }) => (
            <ol className="ms-5 list-decimal">{children}</ol>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-s-2 ps-3 text-muted-foreground">
              {children}
            </blockquote>
          ),
          code: ({ children }) => (
            <code className="rounded bg-muted px-1 text-xs">{children}</code>
          ),
          pre: ({ children }) => (
            <pre className="overflow-auto rounded-lg border bg-muted p-3 [&>code]:bg-transparent [&>code]:p-0">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="min-w-0 overflow-x-auto rounded-lg border">
              <table className="w-full text-left text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b bg-muted p-2 font-semibold">{children}</th>
          ),
          td: ({ children }) => <td className="border-b p-2">{children}</td>,
        }}
      >
        {markdown}
      </Markdown>
    </div>
  )
}

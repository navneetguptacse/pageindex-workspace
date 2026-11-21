import Link from "next/link"
import {
  ArrowRightIcon,
  FileTextIcon,
  MessageSquareIcon,
  SparklesIcon,
} from "lucide-react"

import { buttonVariants } from "@/components/ui/button"

export function DocumentChatCard() {
  return (
    <section
      className="relative isolate overflow-hidden rounded-xl border border-discovery/15 bg-discovery-surface px-5 py-6 sm:px-8 sm:py-8"
      aria-label="Document chat"
    >
      <div className="flex max-w-xl flex-col items-start gap-3">
        <div className="grid size-9 place-items-center rounded-lg bg-card text-discovery">
          <SparklesIcon className="size-5" aria-hidden="true" />
        </div>
        <h2 className="text-xl font-semibold tracking-tight sm:text-2xl">
          Chat with your documents
        </h2>
        <p className="max-w-[40ch] text-sm leading-relaxed text-muted-foreground">
          Ask about one PDF, a collection, or your entire library. Open any
          citation to see where the answer came from.
        </p>
        <Link href="/chat" className={buttonVariants()}>
          <MessageSquareIcon data-icon="inline-start" />
          Open chat
          <ArrowRightIcon data-icon="inline-end" />
        </Link>
      </div>
      <div
        className="pointer-events-none absolute top-1/2 right-[10%] hidden -translate-y-1/2 select-none lg:block"
        aria-hidden="true"
      >
        <div className="absolute inset-0 -translate-x-9 translate-y-0 -rotate-12 rounded-xl border border-discovery/20 bg-accent shadow-sm" />
        <div className="absolute inset-0 translate-x-7 translate-y-1 rotate-12 rounded-xl border border-discovery/20 bg-success-surface shadow-sm" />
        <div className="relative flex h-33 w-34 -rotate-3 flex-col gap-2 rounded-xl border border-discovery/20 bg-card p-4 shadow-sm">
          <FileTextIcon className="mb-1 size-6 text-discovery" />
          <div className="h-2 w-20 rounded-full bg-discovery/20" />
          <div className="h-2 w-15 rounded-full bg-primary/20" />
          <div className="h-2 w-22 rounded-full bg-discovery/15" />
        </div>
      </div>
    </section>
  )
}

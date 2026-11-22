"use client"

import { Suspense, useCallback, useRef, useState, type FormEvent } from "react"
import { useSearchParams } from "next/navigation"
import {
  ArrowUpIcon,
  ClockIcon,
  MessageSquareIcon,
  PlusIcon,
  SparklesIcon,
  Trash2Icon,
} from "lucide-react"

import {
  api,
  errorMessage,
  type ChatMessage,
  type ChatSession,
} from "@/lib/api"
import { useResource } from "@/hooks/use-resource"
import { useConversation, type Scope } from "@/hooks/use-conversation"
import { formatDate } from "@/lib/format"
import { Button } from "@/components/ui/button"
import { InputGroup } from "@/components/ui/input-group"
import { Textarea } from "@/components/ui/textarea"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import {
  Message,
  MessageAvatar,
  MessageContent,
  MessageFooter,
  MessageHeader,
} from "@/components/ui/message"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { CitationModal } from "@/components/citation-modal"
import { CitationViewer } from "@/components/citation-viewer"
import { MarkdownRenderer } from "@/components/markdown-renderer"
import { ErrorNotice, LoadingRows, PageHeader } from "@/components/workspace-ui"

const prompts = [
  "Summarize the main findings.",
  "What are the most important figures?",
  "Which risks or caveats are mentioned?",
]
const loadDocuments = () => api.documents.list()
const historyPageSize = 50
type HistoryCursor = Pick<ChatSession, "id" | "updated_at">

function ChatMessageRow({
  message,
  onCitationClick,
}: {
  message: ChatMessage
  onCitationClick: (citation: { doc?: string; page: number }) => void
}) {
  const user = message.role === "user"
  const citationClick = ({ doc, page }: { doc?: string; page: number }) => {
    const citation = message.citations?.find(
      (item) => item.document === doc && item.page === page
    )
    onCitationClick({ doc: citation?.doc_id ?? doc, page })
  }
  return (
    <Message align={user ? "end" : "start"}>
      {!user && (
        <MessageAvatar className="size-8 self-start rounded-lg bg-discovery-surface text-discovery group-has-data-[slot=message-footer]/message:translate-y-0">
          <SparklesIcon className="size-4" aria-hidden="true" />
        </MessageAvatar>
      )}
      <MessageContent>
        <MessageHeader className="text-xs font-semibold">
          {user ? "You" : "PageIndex"}
        </MessageHeader>
        <Bubble
          align={user ? "end" : "start"}
          variant={user ? "muted" : "ghost"}
          className="max-w-full rounded-lg sm:max-w-[92%]"
        >
          <BubbleContent className="text-sm leading-relaxed">
            {user ? (
              <p className="whitespace-pre-wrap">{message.content}</p>
            ) : (
              <MarkdownRenderer
                content={message.content}
                sources={message.citations}
                onCitationClick={citationClick}
              />
            )}
          </BubbleContent>
        </Bubble>
        {!user &&
        message.citations?.length &&
        !/<(?:cite\b|doc=)|\[source\s+\d+\]/i.test(message.content) ? (
          <CitationViewer
            citations={message.citations}
            onCitationClick={citationClick}
          />
        ) : null}
        {!user && message.usage?.total_tokens != null && (
          <MessageFooter>
            <div className="flex items-center gap-2">
              <span>{message.usage.total_tokens.toLocaleString()} tokens</span>

              {!!message.usage.cached_tokens && (
                <>
                  <span className="h-3 w-px bg-current opacity-30" />
                  <span>
                    {message.usage.cached_tokens.toLocaleString()} cached
                  </span>
                </>
              )}
            </div>
          </MessageFooter>
        )}
      </MessageContent>
    </Message>
  )
}

function ConversationList({
  sessions,
  active,
  onOpen,
  onDelete,
  disabled,
}: {
  sessions: ChatSession[]
  active: string | null
  onOpen: (id: string) => void
  onDelete: (id: string) => void
  disabled: boolean
}) {
  if (!sessions.length)
    return (
      <p className="px-3 py-6 text-sm text-muted-foreground">
        Your saved conversations will appear here.
      </p>
    )
  return (
    <ul className="flex flex-col gap-1">
      {sessions.map((session) => (
        <li key={session.id} className="flex min-w-0 items-center gap-1">
          <Button
            variant={session.id === active ? "secondary" : "ghost"}
            disabled={disabled}
            className="h-auto min-w-0 flex-1 justify-start px-2 py-2 text-left"
            aria-current={session.id === active ? "true" : undefined}
            onClick={() => onOpen(session.id)}
          >
            <MessageSquareIcon data-icon="inline-start" />
            <span className="min-w-0">
              <span className="block truncate">{session.title}</span>
              <span className="block truncate text-xs font-normal text-muted-foreground">
                {session.document_filename || formatDate(session.updated_at)}
              </span>
            </span>
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            disabled={disabled}
            aria-label={`Move ${session.title} to trash`}
            onClick={() => onDelete(session.id)}
          >
            <Trash2Icon />
          </Button>
        </li>
      ))}
    </ul>
  )
}

function ChatWorkspace() {
  const params = useSearchParams()
  const initialDoc = params.get("doc")
  const initialCollection = params.get("collection")
  const initialScope = initialDoc
    ? (`document:${initialDoc}` as const)
    : initialCollection
      ? (`collection:${initialCollection}` as const)
      : "library"
  const documents = useResource(loadDocuments)
  const collections = useResource(api.collections.list)
  const [historyCursors, setHistoryCursors] = useState<HistoryCursor[]>([])
  const cursor = historyCursors.at(-1) ?? null
  const loadSessions = useCallback(
    async () => ({
      cursor,
      items: await api.chat.listSessions({
        limit: historyPageSize + 1,
        before_id: cursor?.id,
        before_updated_at: cursor?.updated_at,
      }),
    }),
    [cursor]
  )
  const sessions = useResource(loadSessions)
  const page =
    sessions.data?.cursor === cursor ? sessions.data.items : undefined
  const visibleSessions = page?.slice(0, historyPageSize) ?? []
  const nextCursor =
    page && page.length > historyPageSize ? visibleSessions.at(-1) : undefined
  const chat = useConversation(initialScope, () => {
    if (cursor) setHistoryCursors([])
    else void sessions.refresh()
  })
  const [draft, setDraft] = useState("")
  const [mobileHistory, setMobileHistory] = useState(false)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [deletePending, setDeletePending] = useState(false)
  const [error, setError] = useState("")
  const [citation, setCitation] = useState<{ docId: string; page: number }>()
  const composer = useRef<HTMLTextAreaElement>(null)
  const generating = Boolean(chat.pendingQuestion)
  const scopeItems = [
    { value: "library", label: "All documents" },
    ...(documents.data ?? [])
      .filter((document) => document.status === "ready")
      .map((document) => ({
        value: `document:${document.doc_id}`,
        label: document.filename,
      })),
    ...(collections.data ?? [])
      .filter((collection) => collection.pageindex_collection_id)
      .map((collection) => ({
        value: `collection:${collection.id}`,
        label: `Collection: ${collection.name}`,
      })),
  ]

  const onCitationClick = ({ doc, page }: { doc?: string; page: number }) => {
    const docId =
      doc || (chat.scope.startsWith("document:") ? chat.scope.slice(9) : "")
    if (docId) setCitation({ docId, page })
  }

  function newChat(scope?: Scope) {
    chat.startNew(scope)
    setDraft("")
    setError("")
    setMobileHistory(false)
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (await chat.send(draft)) setDraft("")
  }

  async function deleteSession() {
    if (!deleteId) return
    setDeletePending(true)
    setError("")
    try {
      await api.chat.deleteSession(deleteId)
      if (chat.sessionId === deleteId) newChat()
      setDeleteId(null)
      await sessions.refresh()
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setDeletePending(false)
    }
  }

  const history = (
    <>
      {page ? (
        <ConversationList
          sessions={visibleSessions}
          active={chat.sessionId}
          disabled={generating}
          onOpen={(id) => {
            setMobileHistory(false)
            setDraft("")
            void chat.open(id)
          }}
          onDelete={setDeleteId}
        />
      ) : sessions.error ? (
        <Button variant="ghost" onClick={() => void sessions.refresh()}>
          Retry loading conversations
        </Button>
      ) : (
        <LoadingRows label="Loading conversations" />
      )}
      {(cursor || nextCursor) && (
        <div className="mt-2 flex gap-1 border-t pt-2">
          <Button
            size="sm"
            variant="ghost"
            disabled={!cursor || generating || deletePending}
            onClick={() =>
              setHistoryCursors((previous) => previous.slice(0, -1))
            }
          >
            Newer
          </Button>
          <Button
            size="sm"
            variant="ghost"
            disabled={
              !nextCursor ||
              Boolean(sessions.error) ||
              generating ||
              deletePending
            }
            onClick={() => {
              if (nextCursor)
                setHistoryCursors((previous) => [...previous, nextCursor])
            }}
          >
            Older
          </Button>
        </div>
      )}
    </>
  )

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <PageHeader
        title="Chat"
        description="Ask questions and open the PDF pages behind each answer."
        actions={
          <>
            <Sheet open={mobileHistory} onOpenChange={setMobileHistory}>
              <SheetTrigger
                render={<Button variant="outline" className="lg:hidden" />}
              >
                <ClockIcon data-icon="inline-start" />
                History
              </SheetTrigger>
              <SheetContent side="left">
                <SheetHeader>
                  <SheetTitle>Conversations</SheetTitle>
                </SheetHeader>
                <div className="overflow-auto px-3 pb-4">{history}</div>
              </SheetContent>
            </Sheet>
            <Button
              variant="outline"
              disabled={generating}
              onClick={() => newChat()}
            >
              <PlusIcon data-icon="inline-start" />
              New chat
            </Button>
          </>
        }
      />
      {(error || sessions.error || documents.error || collections.error) && (
        <ErrorNotice>
          {error || sessions.error || documents.error || collections.error}
        </ErrorNotice>
      )}

      <div className="grid min-w-0 gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <aside className="hidden min-w-0 flex-col rounded-surface border bg-card lg:flex">
          <h2 className="border-b px-4 py-3 font-semibold">Conversations</h2>
          <div className="max-h-[65vh] overflow-auto p-2">{history}</div>
        </aside>
        <section
          aria-label="Conversation"
          className="flex h-[max(30rem,calc(100dvh-14rem))] min-w-0 flex-col rounded-surface border bg-card sm:h-[max(32rem,calc(100dvh-12rem))]"
        >
          <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2.5 sm:px-5">
            <label
              htmlFor="chat-scope"
              className="shrink-0 text-sm font-medium"
            >
              Sources
            </label>
            <Select
              items={scopeItems}
              value={chat.scope}
              onValueChange={(value) => {
                if (value) newChat(value as Scope)
              }}
              disabled={generating || chat.loadingHistory}
            >
              <SelectTrigger
                id="chat-scope"
                className="w-full max-w-72 min-w-0"
              >
                <SelectValue placeholder="Choose sources" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {scopeItems.map(({ value, label }) => (
                    <SelectItem value={value} key={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>

          <MessageScrollerProvider
            key={chat.sessionId ?? chat.scope}
            autoScroll
          >
            <MessageScroller className="flex-1">
              <MessageScrollerViewport>
                <MessageScrollerContent className="mx-auto max-w-3xl gap-5 px-3 py-5 sm:px-6">
                  {chat.loadingHistory ? (
                    <MessageScrollerItem messageId="history-loading">
                      <LoadingRows label="Loading conversation" />
                    </MessageScrollerItem>
                  ) : chat.messages.length === 0 && !generating ? (
                    <MessageScrollerItem
                      messageId="welcome"
                      className="flex flex-1 items-center"
                    >
                      <Empty className="p-3 sm:p-8">
                        <EmptyHeader>
                          <EmptyMedia variant="icon" size="lg" tone="discovery">
                            <SparklesIcon />
                          </EmptyMedia>
                          <EmptyTitle className="text-xl">
                            Ask your documents
                          </EmptyTitle>
                          <EmptyDescription className="text-sm">
                            Start with a question, or choose one to edit.
                          </EmptyDescription>
                        </EmptyHeader>
                        <div className="flex flex-wrap justify-center gap-2">
                          {prompts.map((prompt) => (
                            <Button
                              key={prompt}
                              size="sm"
                              variant="outline"
                              className="max-w-full text-balance whitespace-normal"
                              onClick={() => {
                                setDraft(prompt)
                                composer.current?.focus()
                              }}
                            >
                              {prompt}
                            </Button>
                          ))}
                        </div>
                      </Empty>
                    </MessageScrollerItem>
                  ) : (
                    <>
                      {chat.messages.map((message) => (
                        <MessageScrollerItem
                          messageId={message.id!}
                          key={message.id}
                          scrollAnchor={message.role === "user"}
                        >
                          <ChatMessageRow
                            message={message}
                            onCitationClick={onCitationClick}
                          />
                        </MessageScrollerItem>
                      ))}
                      {generating && (
                        <>
                          <MessageScrollerItem
                            messageId="question-being-answered"
                            scrollAnchor
                          >
                            <ChatMessageRow
                              message={{
                                role: "user",
                                content: chat.pendingQuestion,
                              }}
                              onCitationClick={onCitationClick}
                            />
                          </MessageScrollerItem>
                          <MessageScrollerItem messageId="generation">
                            <div
                              className="generative-border w-fit max-w-full rounded-xl px-4 py-3 text-sm font-medium"
                              role="status"
                            >
                              <span className="flex items-center gap-2">
                                <SparklesIcon
                                  className="size-4 text-discovery"
                                  aria-hidden="true"
                                />
                                Generating an answer…
                              </span>
                            </div>
                          </MessageScrollerItem>
                        </>
                      )}
                    </>
                  )}
                </MessageScrollerContent>
              </MessageScrollerViewport>
              <MessageScrollerButton />
            </MessageScroller>
          </MessageScrollerProvider>

          <form
            className="shrink-0 border-t px-3 py-3 sm:px-5"
            onSubmit={submit}
          >
            <div className="mx-auto flex w-full max-w-3xl flex-col gap-2">
              {chat.error && <ErrorNotice>{chat.error}</ErrorNotice>}
              <InputGroup variant="composer">
                <Textarea
                  ref={composer}
                  rows={2}
                  aria-label="Ask a question"
                  placeholder="Ask a question about your PDFs…"
                  value={draft}
                  maxLength={4000}
                  disabled={generating || chat.loadingHistory}
                  variant="composer"
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault()
                      event.currentTarget.form?.requestSubmit()
                    }
                  }}
                />
                <Button
                  type="submit"
                  size="icon-lg"
                  aria-label="Send question"
                  disabled={!draft.trim() || generating || chat.loadingHistory}
                >
                  <ArrowUpIcon />
                </Button>
              </InputGroup>
            </div>
          </form>
        </section>
      </div>
      <CitationModal
        open={!!citation}
        onOpenChange={(open) => {
          if (!open) setCitation(undefined)
        }}
        docId={citation?.docId ?? null}
        initialPage={citation?.page ?? 1}
      />
      <AlertDialog
        open={!!deleteId}
        onOpenChange={(open) => {
          if (!open && !deletePending) setDeleteId(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Move conversation to trash?</AlertDialogTitle>
            <AlertDialogDescription>
              You can restore it from Trash.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={deletePending}
              onClick={deleteSession}
            >
              Move to trash
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function ChatFromUrl() {
  const params = useSearchParams()
  return <ChatWorkspace key={params.toString()} />
}

export default function ChatPage() {
  return (
    <Suspense fallback={<LoadingRows label="Loading chat" />}>
      <ChatFromUrl />
    </Suspense>
  )
}

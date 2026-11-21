export interface Document {
  id: string
  doc_id: string
  filename: string
  status: "queued" | "submitting" | "processing" | "ready" | "failed"
  processing_error?: string | null
  file_size?: number | null
  collection_id?: string | null
  uploaded_at: string
  is_deleted?: boolean
  deleted_at?: string | null
  metadata_?: Record<string, unknown> | null
}

export interface ChatUsage {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  cached_tokens?: number
}

export interface ChatMessage {
  id?: string
  role: "user" | "assistant"
  content: string
  citations?: Citation[] | null
  model?: string | null
  usage?: ChatUsage | null
  created_at?: string
}

export interface Citation {
  label?: number
  page?: number
  text?: string
  relevance?: number
  document?: string
  doc_id?: string | null
  box?: string
  [key: string]: unknown
}

export interface ChatResponse {
  id: string
  session_id?: string | null
  question: string
  answer: string
  citations?: Citation[] | null
  model?: string | null
  usage?: ChatUsage | null
  created_at: string
}

export interface ChatSession {
  id: string
  title: string
  doc_id?: string | null
  document_filename?: string | null
  collection_id?: string | null
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview?: string | null
}

export interface ChatSessionDetail extends Omit<
  ChatSession,
  "message_count" | "last_message_preview"
> {
  messages: ChatHistoryItem[]
}

export interface ChatHistoryItem {
  id: string
  session_id?: string | null
  document_id?: string | null
  collection_id?: string | null
  question: string
  answer: string
  citations?: Citation[] | null
  model?: string | null
  usage?: ChatUsage | null
  created_at: string
}

export interface SearchPageResult {
  page: number
  relevance: number
  read?: string | null
  text?: string | null
}

export interface SearchDocumentResult {
  doc_id: string
  pages: SearchPageResult[]
}

export interface SearchQuestionResult {
  question: string
  documents: SearchDocumentResult[]
}

export interface SearchResponse {
  results: SearchQuestionResult[]
  usage?: Record<string, unknown> | null
}

export interface ExtractJob {
  id: string
  document_id: string | null
  pageindex_job_id: string
  status:
    | "queued"
    | "submitting"
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
  processing_error?: string | null
  schema_name?: string | null
  result?: Record<string, unknown> | unknown[] | null
  usage?: { credits?: number; pages?: number } | null
  extract_metadata?: {
    field_metadata?: Record<string, { page?: number }>
  } | null
  created_at: string
}

export interface Collection {
  id: string
  name: string
  pageindex_collection_id?: string | null
  created_at: string
}

export interface PagePreview {
  doc_id: string
  filename: string
  page: number
  total_pages: number
  text: string | null
  has_image: boolean
  image_url: string | null
}

export interface TrashItem {
  id: string
  type: "document" | "chat" | "extract"
  title: string
  details?: string | null
  deleted_at: string
}

export type OAuthProvider = "google" | "github"
export type ChatProvider = "openai" | "deepseek" | "anthropic" | "gemini"

export interface ProviderSettings {
  pageindex_configured: boolean
  chat_configured: boolean
  chat_provider: ChatProvider | null
  chat_model: string | null
}

export interface ProviderSettingsUpdate {
  pageindex_api_key?: string | null
  chat?: { provider: ChatProvider; model: string; api_key?: string } | null
}

export interface WorkspaceStatus {
  auth_required: boolean
  username: string | null
  email: string | null
  email_verified: boolean
  has_password: boolean
  email_enabled: boolean
  signup_enabled: boolean
  registration_open: boolean
  oauth_providers: OAuthProvider[]
  linked_providers: OAuthProvider[]
}

export interface WorkspaceUsage {
  chat_tokens: number
  chat_token_limit: number | null
  provider_requests: number | null
  provider_request_limit: number | null
}

export type ChatTarget = { doc_id?: string; collection_id?: string }
export type TrashReference = Pick<TrashItem, "id" | "type">

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number
  ) {
    super(message)
    this.name = "ApiError"
  }
}

export function errorMessage(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Try again."
}

function query(params: Record<string, string | number | undefined> = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value))
  }
  return search.size ? `?${search}` : ""
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api/v1${path}`, { cache: "no-store", ...options })
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiError(
      "Could not reach PageIndex. Check your connection and retry.",
      0
    )
  }

  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((item) => item.msg)
              .filter(Boolean)
              .join(". ")
          : `Request failed (${response.status})`
    if (
      response.status === 401 &&
      (!path.startsWith("/workspace/") ||
        path === "/workspace/usage" ||
        path.startsWith("/workspace/account/"))
    ) {
      window.dispatchEvent(new Event("pageindex:session-expired"))
    }
    throw new ApiError(message, response.status)
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

function post<T>(
  path: string,
  data: unknown,
  headers: Record<string, string> = {},
  signal?: AbortSignal
) {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(data),
    signal,
  })
}

function backgroundHeaders(key: string) {
  return { Prefer: "respond-async", "Idempotency-Key": key }
}

export const api = {
  workspace: {
    status: () => request<WorkspaceStatus>("/workspace/session"),
    providers: () => request<ProviderSettings>("/workspace/account/providers"),
    updateProviders: (settings: ProviderSettingsUpdate) =>
      request<ProviderSettings>("/workspace/account/providers", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      }),
    logoutEverywhere: () => post<void>("/workspace/account/logout-all", {}),
    changePassword: (current_password: string, new_password: string) =>
      post<{ message: string }>("/workspace/account/password", {
        current_password,
        new_password,
      }),
    usage: () => request<WorkspaceUsage>("/workspace/usage"),
    login: (username: string, password: string) =>
      post<WorkspaceStatus>("/workspace/login", { username, password }),
    logout: () => post<void>("/workspace/logout", {}),
    signup: (email: string) =>
      post<{ message: string }>("/workspace/signup", { email }),
    verifySignup: (token: string, username: string, password: string) =>
      post<WorkspaceStatus>("/workspace/verify-signup", {
        token,
        username,
        password,
      }),
    verifyEmail: (token: string) =>
      post<{ message: string }>("/workspace/verify-email", { token }),
    forgotPassword: (email: string) =>
      post<{ message: string }>("/workspace/forgot-password", { email }),
    resetPassword: (token: string, password: string) =>
      post<{ message: string }>("/workspace/reset-password", {
        token,
        password,
      }),
    addEmail: (email: string, password: string) =>
      post<{ message: string }>("/workspace/account/email", {
        email,
        password,
      }),
    oauthUrl: (provider: OAuthProvider, link = false) =>
      `/api/v1/workspace/oauth/${provider}${link ? "?link=true" : ""}`,
  },
  documents: {
    list: (collectionId?: string) =>
      request<Document[]>(
        `/documents${query({ collection_id: collectionId })}`
      ),
    upload: (
      input: File | File[],
      collectionId?: string,
      idempotencyKey: string = crypto.randomUUID()
    ) => {
      const body = new FormData()
      for (const file of Array.isArray(input) ? input : [input])
        body.append("files", file)
      return request<Document[]>(
        `/documents/batch${query({ collection_id: collectionId })}`,
        {
          method: "POST",
          body,
          headers: backgroundHeaders(idempotencyKey),
        }
      )
    },
    get: (id: string) =>
      request<Document>(`/documents/${encodeURIComponent(id)}`),
    retry: (id: string) =>
      post<Document>(`/documents/${encodeURIComponent(id)}/retry`, {}),
    rename: (id: string, filename: string) =>
      request<Document>(`/documents/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename }),
      }),
    delete: (id: string) =>
      request<void>(`/documents/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    getPagePreview: (docId: string, page: number, signal?: AbortSignal) =>
      request<PagePreview>(
        `/documents/page-preview${query({ doc_id: docId, page })}`,
        { signal }
      ),
    getPageImageUrl: (docId: string, page: number) =>
      `/api/v1/documents/page-image${query({ doc_id: docId, page })}`,
  },
  chat: {
    send: (
      body: ChatTarget & {
        question: string
        session_id?: string
        model?: string
        citations?: boolean
      },
      signal?: AbortSignal
    ) => post<ChatResponse>("/chat", body, {}, signal),
    listSessions: (params: ChatTarget = {}, signal?: AbortSignal) =>
      request<ChatSession[]>(`/chat/sessions${query(params)}`, { signal }),
    getSession: (id: string, signal?: AbortSignal) =>
      request<ChatSessionDetail>(`/chat/sessions/${encodeURIComponent(id)}`, {
        signal,
      }),
    createSession: (body: ChatTarget & { title?: string }) =>
      post<ChatSession>("/chat/sessions", body),
    deleteSession: (id: string) =>
      request<void>(`/chat/sessions/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    batchDelete: (sessionIds: string[]) =>
      post<{ deleted: number }>("/chat/sessions/batch-delete", {
        session_ids: sessionIds,
      }),
    history: (params: ChatTarget & { session_id?: string } = {}) =>
      request<ChatHistoryItem[]>(`/chat/history${query(params)}`),
  },
  search: {
    search: (
      body: {
        questions: string[]
        document?: string
        documents?: string[]
        collection?: string
        include_text?: boolean
        top_k?: number
        max_documents?: number
      },
      signal?: AbortSignal
    ) => post<SearchResponse>("/search", body, {}, signal),
  },
  extract: {
    extract: (
      body: {
        document: string
        schema: Record<string, unknown>
        tier?: "standard" | "pro"
        pages?: string
        cite_sources?: boolean
        schema_name?: string
      },
      idempotencyKey: string = crypto.randomUUID()
    ) => post<ExtractJob>("/extract", body, backgroundHeaders(idempotencyKey)),
    listJobs: (documentId?: string) =>
      request<ExtractJob[]>(
        `/extract/jobs${query({ document_id: documentId })}`
      ),
    getJob: (id: string) =>
      request<ExtractJob>(`/extract/jobs/${encodeURIComponent(id)}`),
    deleteJob: (id: string) =>
      request<void>(`/extract/jobs/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
    clearJobs: (documentId?: string) =>
      request<{ cleared: number }>(
        `/extract/jobs${query({ document_id: documentId })}`,
        { method: "DELETE" }
      ),
  },
  trash: {
    list: () => request<TrashItem[]>("/trash/items"),
    restore: (items: TrashReference[]) =>
      post<{ restored: number }>("/trash/restore", { items }),
    permanentDelete: (items: TrashReference[]) =>
      post<{ deleted: number }>("/trash/permanent-delete", { items }),
    empty: () =>
      request<{ purged: number }>("/trash/empty", { method: "DELETE" }),
  },
  collections: {
    list: () => request<Collection[]>("/collections"),
    create: (name: string) => post<Collection>("/collections", { name }),
    delete: (id: string) =>
      request<void>(`/collections/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
  },
}

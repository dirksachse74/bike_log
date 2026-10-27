// All JSON goes through here. Mutations carry the per-launch token from the <meta> tag and a
// client operation id, so a double click or a retry after a timeout is applied only once.

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, message: string, detail: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

function token(): string {
  const meta = document.querySelector('meta[name="bikelog-token"]')?.getAttribute('content') ?? ''
  if (meta && meta !== '%BIKELOG_TOKEN%') return meta
  return (import.meta.env.VITE_DEV_TOKEN as string | undefined) ?? ''
}

export function newOpId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

async function request<T>(method: string, path: string, body?: unknown, opts: { opId?: string; raw?: BodyInit; contentType?: string } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  if (method !== 'GET') headers['X-BikeLog-Token'] = token()
  if (opts.opId) headers['X-Client-Op-Id'] = opts.opId
  let payload: BodyInit | undefined
  if (opts.raw !== undefined) {
    payload = opts.raw
    headers['Content-Type'] = opts.contentType ?? 'application/octet-stream'
  } else if (body !== undefined) {
    payload = JSON.stringify(body)
    headers['Content-Type'] = 'application/json'
  }
  let res: Response
  try {
    res = await fetch(`./api${path}`, { method, headers, body: payload })
  } catch {
    throw new ApiError(0, 'Cannot reach Bike Log. Is the app still running?', null)
  }
  const text = await res.text()
  let data: unknown
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!res.ok) {
    const d = data as { detail?: unknown } | null
    let msg = `Request failed (${res.status})`
    if (d && typeof d.detail === 'string') msg = d.detail
    else if (d && Array.isArray(d.detail)) msg = d.detail.map((e: { loc?: unknown[]; msg?: string }) => `${(e.loc ?? []).slice(1).join('.')}: ${e.msg}`).join('; ')
    throw new ApiError(res.status, msg, data)
  }
  return data as T
}

export const api = {
  get: <T,>(path: string) => request<T>('GET', path),
  post: <T,>(path: string, body?: unknown, opId?: string) => request<T>('POST', path, body ?? {}, { opId }),
  patch: <T,>(path: string, body: unknown, opId?: string) => request<T>('PATCH', path, body, { opId }),
  put: <T,>(path: string, body: unknown) => request<T>('PUT', path, body),
  del: <T,>(path: string) => request<T>('DELETE', path),
  upload: <T,>(path: string, content: Blob, contentType = 'text/csv') => request<T>('POST', path, undefined, { raw: content, contentType }),
}

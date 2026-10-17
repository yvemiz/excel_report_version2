export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { ...init, credentials: 'same-origin' })
  const body = await response.json().catch(() => null)
  if (!response.ok || body?.success === false) {
    if (response.status === 401 && !url.startsWith('/api/auth/')) {
      window.dispatchEvent(new Event('session-expired'))
    }
    const detail = body?.detail || body?.message
    throw new ApiError(
      typeof detail === 'string' ? detail : `请求失败（HTTP ${response.status}）`,
      response.status,
    )
  }
  if (body === null) throw new Error('服务器未返回有效数据')
  return body as T
}

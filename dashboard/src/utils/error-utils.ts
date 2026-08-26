export function getErrorStatus(error: unknown): number | undefined {
  if (error instanceof Response) {
    return error.status
  }

  if (typeof error === 'object' && error !== null) {
    const maybeError = error as {
      status?: unknown
      statusCode?: unknown
      response?: { status?: unknown }
    }

    if (typeof maybeError.status === 'number') return maybeError.status
    if (typeof maybeError.statusCode === 'number') return maybeError.statusCode
    if (typeof maybeError.response?.status === 'number') return maybeError.response.status
  }

  return undefined
}

export function isUnauthorizedError(error: unknown): boolean {
  return getErrorStatus(error) === 401
}

export function isAuthenticationError(error: unknown): boolean {
  const status = getErrorStatus(error)

  return status === 401 || status === 403
}

export function formatErrorDetail(detail: unknown): string | undefined {
  if (!detail) return undefined
  if (typeof detail === 'string') return detail
  if (typeof detail === 'number' || typeof detail === 'boolean') return String(detail)

  if (Array.isArray(detail)) {
    const message = detail
      .map(item => formatErrorDetail(item))
      .filter(Boolean)
      .join('\n')

    return message || undefined
  }

  if (typeof detail === 'object') {
    const entries = Object.entries(detail as Record<string, unknown>)
    const message = entries
      .map(([key, value]) => {
        const formattedValue = formatErrorDetail(value)

        return formattedValue ? `${key}: ${formattedValue}` : key
      })
      .join('\n')

    return message || undefined
  }

  return undefined
}

export function getErrorMessage(error: unknown): string {
  if (typeof error === 'string') return error

  if (error instanceof Error && error.message) {
    return error.message
  }

  if (typeof error === 'object' && error !== null) {
    const maybeError = error as {
      data?: { detail?: unknown; message?: unknown }
      response?: { _data?: { detail?: unknown; message?: unknown }; data?: { detail?: unknown; message?: unknown } }
      message?: unknown
    }

    return (
      formatErrorDetail(maybeError.data?.detail) ||
      formatErrorDetail(maybeError.response?._data?.detail) ||
      formatErrorDetail(maybeError.response?.data?.detail) ||
      formatErrorDetail(maybeError.data?.message) ||
      formatErrorDetail(maybeError.response?._data?.message) ||
      formatErrorDetail(maybeError.response?.data?.message) ||
      (typeof maybeError.message === 'string' ? maybeError.message : 'An unexpected error occurred')
    )
  }

  return 'An unexpected error occurred'
}

export function getErrorStack(error: unknown): string | undefined {
  if (error instanceof Error && error.stack) {
    return error.stack
  }

  if (typeof error === 'object' && error !== null) {
    const maybeError = error as { stack?: unknown }

    if (typeof maybeError.stack === 'string') {
      return maybeError.stack
    }
  }

  return undefined
}

export function getSerializableError(error: unknown): string | undefined {
  if (!error || error instanceof Error || typeof error !== 'object') {
    return undefined
  }

  try {
    return JSON.stringify(error, null, 2)
  } catch {
    return undefined
  }
}

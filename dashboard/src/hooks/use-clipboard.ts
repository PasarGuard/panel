import { useState, useCallback } from 'react'

function copyWithCopyEvent(text: string): boolean {
  let written = false
  const onCopy = (event: ClipboardEvent) => {
    if (!event.clipboardData) return
    event.clipboardData.setData('text/plain', text)
    event.preventDefault()
    written = true
  }

  document.addEventListener('copy', onCopy)
  try {
    return document.execCommand('copy') && written
  } catch {
    return false
  } finally {
    document.removeEventListener('copy', onCopy)
  }
}

async function copyToClipboard(text: string): Promise<boolean> {
  // Try modern clipboard API first (required for iOS)
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch (err) {
      console.error('Clipboard API failed:', err)
      // Fall through to fallback method
    }
  }

  // Fallback for insecure contexts (plain HTTP on a LAN IP, UDS behind a proxy) where
  // navigator.clipboard is unavailable. Write the text from a copy event instead of selecting a
  // hidden textarea: inside a focus-trapping Radix menu or dialog the textarea cannot keep focus,
  // so execCommand('copy') copies an empty selection while still returning true.
  if (copyWithCopyEvent(text)) {
    return true
  }

  // Last resort: select a hidden textarea and keep multiline content intact.
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '-9999px'
  textarea.setAttribute('readonly', '')
  document.body.appendChild(textarea)
  textarea.focus()
  textarea.select()

  try {
    const successful = document.execCommand('copy')
    document.body.removeChild(textarea)
    return successful
  } catch (err) {
    document.body.removeChild(textarea)
    return false
  }
}

export function useClipboard({ timeout = 1500 } = {}) {
  const [error, setError] = useState<Error | null>(null)
  const [copied, setCopied] = useState(false)
  const [copyTimeout, setCopyTimeout] = useState<number | null>(null)

  const handleCopyResult = (value: boolean) => {
    window.clearTimeout(copyTimeout!)
    setCopyTimeout(window.setTimeout(() => setCopied(false), timeout))
    setCopied(value)
  }

  const copy = useCallback(
    async (text: string) => {
      try {
        const success = await copyToClipboard(text)
        if (success) {
          handleCopyResult(true)
          setError(null)
          return true
        } else {
          setError(new Error('useClipboard: copyToClipboard failed'))
          handleCopyResult(false)
          return false
        }
      } catch (err) {
        setError(err instanceof Error ? err : new Error('useClipboard: copyToClipboard failed'))
        handleCopyResult(false)
        return false
      }
    },
    [timeout],
  )

  const reset = () => {
    setCopied(false)
    setError(null)
    window.clearTimeout(copyTimeout!)
  }

  return { copy, reset, error, copied }
}

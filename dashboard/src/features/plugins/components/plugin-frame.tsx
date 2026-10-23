import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useTheme } from '@/app/providers/theme-provider'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { fetch } from '@/service/http'
import { getCreatePluginUiSessionUrl } from '@/service/api'
import { getAuthToken } from '@/utils/authStorage'
import { getErrorMessage } from '@/utils/error-utils'

// Theme variables forwarded to plugin pages (values are "H S% L%" triplets, use as hsl(var(--name))).
const THEME_VARIABLES = [
  '--background',
  '--foreground',
  '--muted',
  '--muted-foreground',
  '--card',
  '--card-foreground',
  '--popover',
  '--popover-foreground',
  '--border',
  '--input',
  '--primary',
  '--primary-foreground',
  '--secondary',
  '--secondary-foreground',
  '--accent',
  '--accent-foreground',
  '--destructive',
  '--destructive-foreground',
  '--ring',
  '--radius',
  '--success',
]

const readThemeVariables = () => {
  const style = getComputedStyle(document.documentElement)
  const vars: Record<string, string> = {}
  for (const name of THEME_VARIABLES) {
    const value = style.getPropertyValue(name).trim()
    if (value) vars[name] = value
  }
  return vars
}

/** URL of the plugin UI on the panel API origin (the dashboard may be served from another origin in dev). */
export const pluginUiUrl = (pluginId: string) => {
  const base = new URL(import.meta.env.VITE_BASE_API || '/', window.location.href)
  if (!base.pathname.endsWith('/')) base.pathname += '/'
  return new URL(`api/plugins/${encodeURIComponent(pluginId)}/ui/`, base)
}

interface PluginFrameProps {
  pluginId: string
  title: string
}

/**
 * Sandboxed iframe for a plugin page. The iframe cannot send the Authorization header:
 * 1. a path-scoped cookie (POST /api/plugins/<id>/ui-session) lets it load its own files;
 * 2. when the page posts {type: "pasarguard:ready"}, we answer with the token, theme and language.
 * Both directions check the window and the origin of the other side.
 */
export function PluginFrame({ pluginId, title }: PluginFrameProps) {
  const { t, i18n } = useTranslation()
  const { resolvedTheme } = useTheme()
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const src = useMemo(() => pluginUiUrl(pluginId), [pluginId])

  useEffect(() => {
    let cancelled = false
    setReady(false)
    setError(null)
    fetch(getCreatePluginUiSessionUrl(pluginId), { method: 'POST', credentials: 'include' })
      .then(() => !cancelled && setReady(true))
      .catch(err => !cancelled && setError(getErrorMessage(err)))
    return () => {
      cancelled = true
    }
  }, [pluginId])

  const postContext = useCallback(() => {
    const target = iframeRef.current?.contentWindow
    const token = getAuthToken()
    if (!target || !token) return
    target.postMessage({ type: 'pasarguard:context', token, theme: resolvedTheme, lang: i18n.language, cssVars: readThemeVariables() }, src.origin)
  }, [i18n.language, resolvedTheme, src])

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (event.source !== iframeRef.current?.contentWindow || event.origin !== src.origin) return
      if (event.data?.type === 'pasarguard:ready') postContext()
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [postContext, src])

  // Theme or language changed: resend so the plugin page can follow
  useEffect(() => {
    if (ready) postContext()
  }, [ready, postContext])

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          {t('plugins.uiError')}: {error}
        </AlertDescription>
      </Alert>
    )
  }

  if (!ready) {
    return <p className="text-muted-foreground p-4 text-sm">{t('plugins.uiLoading')}</p>
  }

  return <iframe ref={iframeRef} title={title} src={src.href} sandbox="allow-scripts allow-forms allow-same-origin" className="bg-background h-[calc(100dvh-10rem)] w-full rounded-md border" />
}

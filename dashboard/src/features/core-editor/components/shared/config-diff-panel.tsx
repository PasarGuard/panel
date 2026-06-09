import { useTheme } from '@/app/providers/theme-provider'
import { DEFAULT_MONACO_CODE_EDITOR_OPTIONS } from '@/components/common/code-editor-defaults'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { JsonValue } from '@pasarguard/xray-config-kit'
import { Maximize2, Minimize2 } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'

const MonacoDiffEditor = lazy(() => import('@/components/common/monaco-editor').then(m => ({ default: m.DiffEditor })))

const EMBEDDED_DIFF_H = 'h-[calc(50vh-1rem)] sm:h-[calc(55vh-1rem)] md:h-[calc(55vh-1rem)]' as const

function stableStringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return ''
  }
}

interface ConfigDiffPanelProps {
  before: JsonValue
  after: JsonValue
  className?: string
}

/**
 * Read-only JSON diff in a single Monaco surface (inline hunks, not side‑by‑side).
 * Fullscreen uses a `document.body` portal (same rationale as `CodeEditorPanel`).
 */
export function ConfigDiffPanel({ before, after, className }: ConfigDiffPanelProps) {
  const { t } = useTranslation()
  const { resolvedTheme } = useTheme()
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [isDiffReady, setIsDiffReady] = useState(false)
  const diffEditorRef = useRef<{ layout?: () => void } | null>(null)

  const original = useMemo(() => stableStringify(before), [before])
  const modified = useMemo(() => stableStringify(after), [after])

  const handleToggleFullscreen = useCallback(() => {
    diffEditorRef.current = null
    setIsFullscreen(v => !v)
    setIsDiffReady(false)
    setTimeout(() => {
      diffEditorRef.current?.layout?.()
      window.dispatchEvent(new Event('resize'))
    }, 50)
  }, [])

  const handleDiffMount = useCallback((diffEditor: { layout?: () => void }) => {
    diffEditorRef.current = diffEditor
    setIsDiffReady(true)
    requestAnimationFrame(() => {
      diffEditor.layout?.()
      setTimeout(() => diffEditor.layout?.(), 100)
    })
  }, [])

  useEffect(() => {
    return () => {
      diffEditorRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!isFullscreen) return
    const tId = window.setTimeout(() => diffEditorRef.current?.layout?.(), 150)
    return () => window.clearTimeout(tId)
  }, [isFullscreen])

  const theme = resolvedTheme === 'dark' ? 'vs-dark' : 'light'

  const diffOptions = useMemo(
    () =>
      ({
        ...DEFAULT_MONACO_CODE_EDITOR_OPTIONS,
        renderSideBySide: false,
        readOnly: true,
        enableSplitViewResizing: false,
        renderOverviewRuler: false,
        glyphMargin: false,
        fixedOverflowWidgets: true,
      }) as const,
    [],
  )

  const title = t('coreEditor.advanced.diffFullscreenTitle', { defaultValue: 'Diff vs last saved' })

  if (original === modified) {
    return <p className="text-muted-foreground text-sm">{t('coreEditor.advanced.noDiffChanges', { defaultValue: 'No changes.' })}</p>
  }

  const fallback = (
    <div className={cn('bg-muted/20 flex min-h-[200px] w-full items-center justify-center rounded-lg border', EMBEDDED_DIFF_H)} aria-busy>
      <span className="border-primary h-8 w-8 animate-spin rounded-full border-t-2 border-b-2" />
    </div>
  )

  const renderDiffEditor = () => (
    <Suspense fallback={fallback}>
      <MonacoDiffEditor height="100%" language="json" original={original} modified={modified} theme={theme} onMount={handleDiffMount} options={diffOptions as any} />
    </Suspense>
  )

  const fullscreenLayer =
    isFullscreen && typeof document !== 'undefined' ? (
      <div className="bg-background fixed inset-0 z-[200] flex min-h-0 flex-col" dir="ltr">
        <div className="bg-background/95 absolute inset-0 backdrop-blur-sm" onClick={handleToggleFullscreen} />
        {!isDiffReady && (
          <div className="bg-background/80 absolute inset-0 z-[70] flex items-center justify-center backdrop-blur-sm">
            <span className="border-primary h-8 w-8 animate-spin rounded-full border-t-2 border-b-2" />
          </div>
        )}
        <div className="bg-background relative z-10 flex min-h-0 w-full flex-1 flex-col sm:mx-auto sm:my-8 sm:h-[calc(100vh-4rem)] sm:max-w-[95vw] sm:flex-none sm:rounded-lg sm:border sm:shadow-xl">
          <div className="bg-background hidden shrink-0 items-center justify-between rounded-t-lg border-b px-3 py-2.5 sm:flex">
            <span className="text-sm font-medium">{title}</span>
            <Button type="button" size="icon" variant="ghost" className="h-8 w-8 shrink-0" onClick={handleToggleFullscreen} aria-label={t('exitFullscreen', { defaultValue: 'Exit fullscreen' })}>
              <Minimize2 className="h-4 w-4" />
            </Button>
          </div>
          <Button
            type="button"
            size="icon"
            variant="default"
            className="absolute top-2 right-2 z-20 h-9 w-9 rounded-full shadow-lg sm:hidden"
            onClick={handleToggleFullscreen}
            aria-label={t('exitFullscreen', { defaultValue: 'Exit fullscreen' })}
          >
            <Minimize2 className="h-4 w-4" />
          </Button>
          <div className="relative min-h-0 w-full flex-1">{renderDiffEditor()}</div>
        </div>
      </div>
    ) : null

  return (
    <>
      {!isFullscreen && (
        <div className={cn('bg-background relative flex min-h-0 flex-col overflow-hidden rounded-lg border', EMBEDDED_DIFF_H, className)} dir="ltr">
          {!isDiffReady && (
            <div className="bg-background/80 absolute inset-0 z-[70] flex items-center justify-center backdrop-blur-sm">
              <span className="border-primary h-8 w-8 animate-spin rounded-full border-t-2 border-b-2" />
            </div>
          )}
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="bg-background/90 hover:bg-background/90 absolute top-2 right-2 z-10 backdrop-blur-sm"
            onClick={handleToggleFullscreen}
            aria-label={t('fullscreen', { defaultValue: 'Fullscreen' })}
          >
            <Maximize2 className="h-4 w-4" />
          </Button>
          <div className="relative min-h-0 flex-1">{renderDiffEditor()}</div>
        </div>
      )}
      {fullscreenLayer ? createPortal(fullscreenLayer, document.body) : null}
    </>
  )
}

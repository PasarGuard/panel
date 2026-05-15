import { useTheme } from '@/app/providers/theme-provider'
import { Button } from '@/components/ui/button'
import { DEFAULT_MONACO_CODE_EDITOR_OPTIONS } from '@/components/common/code-editor-defaults'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { useIsMobile } from '@/hooks/use-mobile'
import { cn } from '@/lib/utils'
import { Maximize2, Minimize2 } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

const MonacoEditor = lazy(() => import('@/components/common/monaco-editor'))
const MobileCodeAceEditor = lazy(() => import('@/components/common/mobile-code-ace-editor'))

export type CodeEditorPanelProps = {
  value: string
  onChange: (value: string) => void
  /** Monaco language id (default `json`). Mobile Ace uses mapped mode. */
  language?: string
  readOnly?: boolean
  /** Merged into {@link DEFAULT_MONACO_CODE_EDITOR_OPTIONS} (desktop only). */
  monacoOptions?: Record<string, unknown>
  onValidate?: (markers: any[]) => void
  /** Editor instance: Monaco `IStandaloneCodeEditor` or Ace editor. */
  onMount?: (editor: any) => void
  /** Desktop Monaco only. */
  onDidBlur?: () => void
  /** Show maximize/minimize chrome (matches core-config / client-template modals). */
  enableFullscreen?: boolean
  /** Notified when fullscreen toggles (e.g. hide modal footer while expanded). */
  onFullscreenChange?: (fullscreen: boolean) => void
  /**
   * When the hosting dialog closes, fullscreen is cleared.
   * Pass the same flag as `Dialog` `open` when used inside a modal.
   */
  dialogOpen?: boolean
  /**
   * Tailwind classes for the bordered container when not fullscreen.
   * @default core-config style heights
   */
  embeddedContainerClassName?: string
  /** Extra class on outer wrapper (border host). */
  className?: string
  footer?: ReactNode
}

export function relayoutCodeEditorInstance(editor: unknown) {
  if (!editor || typeof editor !== 'object') return
  const e = editor as { layout?: () => void; resize?: () => void }
  if (typeof e.layout === 'function') e.layout()
  if (typeof e.resize === 'function') e.resize()
}

/**
 * Desktop Monaco + mobile Ace, optional fullscreen UI (same behavior as
 * `core-config-modal` / `client-template-modal`).
 */
export function CodeEditorPanel({
  value,
  onChange,
  language = 'json',
  readOnly,
  monacoOptions,
  onValidate,
  onMount,
  onDidBlur,
  enableFullscreen = false,
  onFullscreenChange,
  dialogOpen = true,
  embeddedContainerClassName = 'h-[calc(50vh-1rem)] sm:h-[calc(55vh-1rem)] md:h-[calc(55vh-1rem)]',
  className,
  footer,
}: CodeEditorPanelProps) {
  const { t } = useTranslation()
  const isMobile = useIsMobile()
  const { resolvedTheme } = useTheme()
  const [isEditorFullscreen, setIsEditorFullscreen] = useState(false)
  const [isEditorReady, setIsEditorReady] = useState(false)
  const [editorInstance, setEditorInstance] = useState<any>(null)

  const blurDisposableRef = useRef<{ dispose: () => void } | null>(null)

  useEffect(() => () => blurDisposableRef.current?.dispose(), [])

  useEffect(() => {
    if (dialogOpen === false) {
      setIsEditorFullscreen(false)
    }
  }, [dialogOpen])

  useEffect(() => {
    if (!enableFullscreen) return
    return () => setIsEditorFullscreen(false)
  }, [enableFullscreen])

  useEffect(() => {
    onFullscreenChange?.(isEditorFullscreen)
  }, [isEditorFullscreen, onFullscreenChange])

  const relayoutEditor = useCallback(
    (editor = editorInstance) => {
      relayoutCodeEditorInstance(editor)
    },
    [editorInstance],
  )

  const handleToggleFullscreen = useCallback(() => {
    setIsEditorFullscreen(prev => {
      setTimeout(() => {
        relayoutEditor()
        window.dispatchEvent(new Event('resize'))
      }, 50)
      return !prev
    })
  }, [relayoutEditor])

  const handleEditorDidMount = useCallback(
    (editor: any) => {
      setIsEditorReady(true)
      setEditorInstance(editor)

      if (!isMobile) {
        blurDisposableRef.current?.dispose()
        blurDisposableRef.current = null
        if (onDidBlur && editor?.onDidBlurEditorWidget) {
          blurDisposableRef.current = editor.onDidBlurEditorWidget(() => onDidBlur())
        }
        requestAnimationFrame(() => {
          relayoutCodeEditorInstance(editor)
          setTimeout(() => relayoutCodeEditorInstance(editor), 100)
        })
      } else {
        requestAnimationFrame(() => {
          relayoutCodeEditorInstance(editor)
          setTimeout(() => relayoutCodeEditorInstance(editor), 100)
        })
      }

      onMount?.(editor)
    },
    [isMobile, onDidBlur, onMount],
  )

  useEffect(() => {
    const handleResize = () => {
      setTimeout(() => relayoutEditor(), 100)
    }
    const handleOrientationChange = () => {
      setTimeout(() => relayoutEditor(), 300)
    }
    window.addEventListener('resize', handleResize)
    window.addEventListener('orientationchange', handleOrientationChange)
    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('orientationchange', handleOrientationChange)
    }
  }, [relayoutEditor])

  useEffect(() => {
    if (!editorInstance || !isEditorReady) return
    setTimeout(() => relayoutEditor(), 150)
  }, [editorInstance, isEditorFullscreen, isEditorReady, relayoutEditor])

  const monacoOptionsMerged = {
    ...DEFAULT_MONACO_CODE_EDITOR_OPTIONS,
    readOnly,
    ...monacoOptions,
  } as const

  const editorFallback = <div className="h-full min-h-[200px] w-full" aria-busy />

  const renderEditor = () => {
    if (isMobile) {
      return (
        <Suspense fallback={editorFallback}>
          <MobileCodeAceEditor
            value={value}
            language={language}
            theme={resolvedTheme}
            onChange={onChange}
            onLoad={handleEditorDidMount}
            readOnly={readOnly}
          />
        </Suspense>
      )
    }

    return (
      <Suspense fallback={editorFallback}>
        <MonacoEditor
          height="100%"
          defaultLanguage={language}
          language={language}
          value={value}
          theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
          onChange={v => onChange(v ?? '')}
          onValidate={onValidate}
          onMount={handleEditorDidMount}
          options={monacoOptionsMerged as any}
        />
      </Suspense>
    )
  }

  if (!enableFullscreen) {
    return (
      <div className={cn('relative flex flex-col overflow-hidden rounded-lg border bg-background', className)} dir="ltr">
        <div className="relative min-h-0 flex-1" style={{ minHeight: 0 }}>
          {renderEditor()}
        </div>
        {footer}
      </div>
    )
  }

  return (
    <>
      {!isEditorFullscreen && (
        <div
          className={cn('relative flex flex-col rounded-lg border bg-background', embeddedContainerClassName, className)}
          dir="ltr"
          style={{
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {!isEditorReady && (
            <div className="absolute inset-0 z-[70] flex items-center justify-center bg-background/80 backdrop-blur-sm">
              <span className="h-8 w-8 animate-spin rounded-full border-b-2 border-t-2 border-primary" />
            </div>
          )}
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="absolute right-2 top-2 z-10 bg-background/90 backdrop-blur-sm hover:bg-background/90"
            onClick={handleToggleFullscreen}
            aria-label={t('fullscreen', { defaultValue: 'Fullscreen' })}
          >
            <Maximize2 className="h-4 w-4" />
          </Button>
          <div className="relative min-h-0 flex-1" style={{ minHeight: 0 }}>
            {renderEditor()}
          </div>
          {footer}
        </div>
      )}

      {/* Fullscreen uses a nested Radix Dialog so it gets its own focus trap,
          which works correctly even when this component is inside another Dialog. */}
      <Dialog open={isEditorFullscreen} onOpenChange={open => { if (!open) handleToggleFullscreen() }}>
        <DialogContent
          className="flex h-[100dvh] max-h-[100dvh] w-[100dvw] max-w-[100dvw] flex-col gap-0 rounded-none border-none p-0 sm:h-[calc(100vh-4rem)] sm:max-h-[calc(100vh-4rem)] sm:max-w-[95vw] sm:rounded-lg sm:border sm:p-0 [&>button[class*='absolute']]:hidden"
          dir="ltr"
          onOpenAutoFocus={e => {
            e.preventDefault()
            // Focus the editor after the dialog opens
            setTimeout(() => {
              if (editorInstance) {
                if (typeof editorInstance.focus === 'function') editorInstance.focus()
              }
            }, 100)
          }}
          onPointerDownOutside={e => e.preventDefault()}
          onInteractOutside={e => e.preventDefault()}
        >
          <div className="hidden shrink-0 items-center justify-between border-b bg-background px-3 py-2.5 sm:flex sm:rounded-t-lg">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-8 w-8 shrink-0"
              onClick={handleToggleFullscreen}
              aria-label={t('exitFullscreen', { defaultValue: 'Exit fullscreen' })}
            >
              <Minimize2 className="h-4 w-4" />
            </Button>
          </div>
          <Button
            type="button"
            size="icon"
            variant="default"
            className="absolute right-2 top-2 z-20 h-9 w-9 rounded-full shadow-lg sm:hidden"
            onClick={handleToggleFullscreen}
            aria-label={t('exitFullscreen', { defaultValue: 'Exit fullscreen' })}
          >
            <Minimize2 className="h-4 w-4" />
          </Button>
          <div className="relative min-h-0 w-full flex-1">
            {isEditorFullscreen && renderEditor()}
          </div>
          {footer}
        </DialogContent>
      </Dialog>
    </>
  )
}

import { CodeEditorPanel } from '@/components/common/code-editor-panel'
import { cn } from '@/lib/utils'

interface JsonCodeEditorPanelProps {
  value: string
  onChange: (next: string) => void
  className?: string
  readOnly?: boolean
  /** When false, exits fullscreen (use hosting dialog `open` inside modals). */
  dialogOpen?: boolean
  /** Fires when the editor text area loses focus (e.g. to commit draft state). Desktop Monaco only. */
  onDidBlur?: () => void
  /** Desktop Monaco JSON diagnostics (same as {@link CodeEditorPanel}). */
  onValidate?: (markers: any[]) => void
}

/**
 * JSON editor with desktop Monaco / mobile Ace, fullscreen, and shared options
 * (same stack as `CodeEditorPanel` in core-config / client-template modals).
 */
export function JsonCodeEditorPanel({ value, onChange, className, readOnly, onDidBlur, dialogOpen = true, onValidate }: JsonCodeEditorPanelProps) {
  return (
    <CodeEditorPanel
      value={value}
      onChange={onChange}
      language="json"
      readOnly={readOnly}
      onDidBlur={onDidBlur}
      onValidate={onValidate}
      enableFullscreen
      dialogOpen={dialogOpen}
      className={cn(className)}
    />
  )
}

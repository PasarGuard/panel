import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { ConfigDiffPanel } from '@/features/core-editor/components/shared/config-diff-panel'
import { JsonCodeEditorPanel } from '@/features/core-editor/components/shared/json-code-editor-panel'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import { useCoreDraftMonacoSync } from '@/features/core-editor/state/use-core-draft-sync'
import { profileToPersistedConfig } from '@/features/core-editor/kit/xray-adapter'
import { draftToPersistedConfig } from '@/features/core-editor/kit/wireguard-adapter'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

interface JsonValidationState {
  isValid: boolean
  error?: string
}

export function XrayAdvancedSection() {
  const { t } = useTranslation()
  const kind = useCoreEditorStore(s => s.kind)
  const monacoJson = useCoreEditorStore(s => s.monacoJson)
  const setMonacoJson = useCoreEditorStore(s => s.setMonacoJson)
  const xrayProfile = useCoreEditorStore(s => s.xrayProfile)
  const xrayBaseline = useCoreEditorStore(s => s.xrayBaseline)
  const wgDraft = useCoreEditorStore(s => s.wgDraft)
  const wgBaseline = useCoreEditorStore(s => s.wgBaseline)
  const [showDiff, setShowDiff] = useState(false)
  const [jsonValidation, setJsonValidation] = useState<JsonValidationState>({ isValid: true })
  useCoreDraftMonacoSync()

  const validateJsonContent = useCallback((value: string, showToast = false) => {
    try {
      JSON.parse(value)
      setJsonValidation({ isValid: true })
      return true
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Invalid JSON'
      setJsonValidation({ isValid: false, error: errorMessage })
      if (showToast) {
        toast.error(errorMessage, { duration: 3000 })
      }
      return false
    }
  }, [])

  const handleEditorValidation = useCallback(
    (markers: any[]) => {
      const hasErrors = markers.length > 0
      if (hasErrors) {
        setJsonValidation({ isValid: false, error: markers[0].message })
        toast.error(markers[0].message, { duration: 3000 })
      } else {
        const value = useCoreEditorStore.getState().monacoJson
        validateJsonContent(value, true)
      }
    },
    [validateJsonContent],
  )

  const handleMonacoJsonChange = useCallback(
    (value: string) => {
      setMonacoJson(value, { dirty: true })
      validateJsonContent(value)
    },
    [setMonacoJson, validateJsonContent],
  )

  useEffect(() => {
    if (showDiff) return
    validateJsonContent(monacoJson)
  }, [monacoJson, showDiff, validateJsonContent])

  const beforeJson = useMemo(() => {
    try {
      if (kind === 'wg' && wgBaseline) return JSON.parse(JSON.stringify(draftToPersistedConfig(wgBaseline)))
      if (kind === 'xray' && xrayBaseline) return JSON.parse(JSON.stringify(profileToPersistedConfig(xrayBaseline)))
      return {}
    } catch {
      return {}
    }
  }, [kind, wgBaseline, xrayBaseline])

  const afterJson = useMemo(() => {
    try {
      if (kind === 'wg' && wgDraft) return JSON.parse(JSON.stringify(draftToPersistedConfig(wgDraft)))
      if (kind === 'xray' && xrayProfile) return JSON.parse(JSON.stringify(profileToPersistedConfig(xrayProfile)))
      return {}
    } catch {
      return {}
    }
  }, [kind, wgDraft, xrayProfile])

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-muted/15 p-4 shadow-sm">
        <div className="flex gap-3 sm:gap-4">
          <Switch
            id="show-diff"
            className="mt-0.5 shrink-0"
            checked={showDiff}
            onCheckedChange={setShowDiff}
            aria-describedby={showDiff ? undefined : 'show-diff-hint'}
          />
          <div className="min-w-0 flex-1 space-y-1.5">
            <Label htmlFor="show-diff" className="block cursor-pointer text-sm font-medium leading-snug">
              {t('coreEditor.advanced.showDiff', { defaultValue: 'Show diff vs last saved' })}
            </Label>
            {!showDiff && (
              <p id="show-diff-hint" className="text-xs leading-relaxed text-muted-foreground">
                {t('coreEditor.advanced.autoApplyHint', {
                  defaultValue: 'Valid JSON is merged into the draft automatically after you stop typing.',
                })}
              </p>
            )}
            {showDiff && (
              <p className="text-xs leading-relaxed text-muted-foreground">
                {t('coreEditor.advanced.diffModeHint', {
                  defaultValue: 'Green and red lines show additions and removals compared to the last saved version.',
                })}
              </p>
            )}
          </div>
        </div>
      </div>
      {showDiff ? (
        <ConfigDiffPanel before={beforeJson} after={afterJson} />
      ) : (
        <div className="space-y-2">
          <JsonCodeEditorPanel value={monacoJson} onChange={handleMonacoJsonChange} onValidate={handleEditorValidation} />
          {jsonValidation.error && !jsonValidation.isValid ? (
            <p role="alert" className="text-[0.8rem] font-medium text-destructive">
              {jsonValidation.error}
            </p>
          ) : null}
        </div>
      )}
    </div>
  )
}

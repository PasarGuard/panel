import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ConfigDiffPanel } from '@/features/core-editor/components/shared/config-diff-panel'
import { JsonCodeEditorPanel } from '@/features/core-editor/components/shared/json-code-editor-panel'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import { useCoreDraftMonacoSync } from '@/features/core-editor/state/use-core-draft-sync'
import { profileToPersistedConfig } from '@/features/core-editor/kit/xray-adapter'
import { draftToPersistedConfig } from '@/features/core-editor/kit/wireguard-adapter'
import useDirDetection from '@/hooks/use-dir-detection'
import type { JsonValue } from '@pasarguard/xray-config-kit'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

interface JsonValidationState {
  isValid: boolean
  error?: string
}

type AdvancedTab = 'all' | 'inbounds' | 'outbounds' | 'routing'

const FILTER_TABS: ReadonlyArray<Exclude<AdvancedTab, 'all'>> = ['inbounds', 'outbounds', 'routing']

function safeParseObject(json: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(json)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    return null
  } catch {
    return null
  }
}

/** Slice the persisted config into the JSON the user edits for a given tab. */
function projectForTab(fullConfig: Record<string, unknown> | null, tab: AdvancedTab): unknown {
  if (!fullConfig) return null
  if (tab === 'all') return fullConfig
  if (tab === 'inbounds') return Array.isArray(fullConfig.inbounds) ? fullConfig.inbounds : []
  if (tab === 'outbounds') return Array.isArray(fullConfig.outbounds) ? fullConfig.outbounds : []
  if (tab === 'routing') {
    const routing = fullConfig.routing
    if (routing && typeof routing === 'object' && !Array.isArray(routing)) {
      const rules = (routing as Record<string, unknown>).rules
      return Array.isArray(rules) ? rules : []
    }
    return []
  }
  return null
}

/** Merge the tab-scoped value back into the full config. */
function mergeTabValueIntoConfig(fullConfig: Record<string, unknown>, tab: AdvancedTab, tabValue: unknown): Record<string, unknown> {
  if (tab === 'all') {
    return tabValue && typeof tabValue === 'object' && !Array.isArray(tabValue) ? (tabValue as Record<string, unknown>) : fullConfig
  }
  if (tab === 'inbounds') return { ...fullConfig, inbounds: tabValue }
  if (tab === 'outbounds') return { ...fullConfig, outbounds: tabValue }
  if (tab === 'routing') {
    const prevRouting = fullConfig.routing && typeof fullConfig.routing === 'object' && !Array.isArray(fullConfig.routing) ? (fullConfig.routing as Record<string, unknown>) : {}
    return { ...fullConfig, routing: { ...prevRouting, rules: tabValue } }
  }
  return fullConfig
}

export function XrayAdvancedSection() {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const kind = useCoreEditorStore(s => s.kind)
  const monacoJson = useCoreEditorStore(s => s.monacoJson)
  const setMonacoJson = useCoreEditorStore(s => s.setMonacoJson)
  const xrayProfile = useCoreEditorStore(s => s.xrayProfile)
  const xrayBaseline = useCoreEditorStore(s => s.xrayBaseline)
  const wgDraft = useCoreEditorStore(s => s.wgDraft)
  const wgBaseline = useCoreEditorStore(s => s.wgBaseline)
  const [showDiff, setShowDiff] = useState(false)
  const [activeTab, setActiveTab] = useState<AdvancedTab>('all')
  const [tabDraft, setTabDraft] = useState<string>('')
  const [jsonValidation, setJsonValidation] = useState<JsonValidationState>({ isValid: true })
  useCoreDraftMonacoSync()

  // Filtered tabs only make sense for the xray config. WireGuard has no inbounds/outbounds/routing.
  const filterTabsAvailable = kind === 'xray'
  const effectiveTab: AdvancedTab = filterTabsAvailable ? activeTab : 'all'

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
        const value = effectiveTab === 'all' ? useCoreEditorStore.getState().monacoJson : tabDraft
        validateJsonContent(value, true)
      }
    },
    [effectiveTab, tabDraft, validateJsonContent],
  )

  // Keep the per-tab editor value in sync with the store whenever the active tab,
  // the kind, or the underlying full JSON changes (and the user is not in "all" mode).
  useEffect(() => {
    if (effectiveTab === 'all') return
    const full = safeParseObject(monacoJson)
    const slice = projectForTab(full, effectiveTab)
    setTabDraft(JSON.stringify(slice ?? [], null, 2))
    setJsonValidation({ isValid: true })
  }, [effectiveTab, monacoJson])

  // Reset to the All tab when switching away from xray (wg has no filterable sections).
  useEffect(() => {
    if (!filterTabsAvailable && activeTab !== 'all') {
      setActiveTab('all')
    }
  }, [filterTabsAvailable, activeTab])

  const handleAllJsonChange = useCallback(
    (value: string) => {
      setMonacoJson(value, { dirty: true })
      validateJsonContent(value)
    },
    [setMonacoJson, validateJsonContent],
  )

  const handleTabJsonChange = useCallback(
    (value: string) => {
      setTabDraft(value)
      const isValid = validateJsonContent(value)
      if (!isValid) return
      const full = safeParseObject(monacoJson)
      if (!full) return
      try {
        const parsedSlice = JSON.parse(value)
        const merged = mergeTabValueIntoConfig(full, effectiveTab, parsedSlice)
        setMonacoJson(JSON.stringify(merged, null, 2), { dirty: true })
      } catch {
        /* validation already reported the error */
      }
    },
    [effectiveTab, monacoJson, setMonacoJson, validateJsonContent],
  )

  useEffect(() => {
    if (showDiff) return
    const value = effectiveTab === 'all' ? monacoJson : tabDraft
    validateJsonContent(value)
  }, [monacoJson, tabDraft, effectiveTab, showDiff, validateJsonContent])

  const beforeJson = useMemo<JsonValue>(() => {
    try {
      let full: unknown
      if (kind === 'wg' && wgBaseline) full = draftToPersistedConfig(wgBaseline)
      else if (kind === 'xray' && xrayBaseline) full = profileToPersistedConfig(xrayBaseline)
      else return {} as JsonValue
      const cloned = JSON.parse(JSON.stringify(full)) as Record<string, unknown>
      return (projectForTab(cloned, effectiveTab) ?? {}) as JsonValue
    } catch {
      return {} as JsonValue
    }
  }, [kind, wgBaseline, xrayBaseline, effectiveTab])

  const afterJson = useMemo<JsonValue>(() => {
    try {
      let full: unknown
      if (kind === 'wg' && wgDraft) full = draftToPersistedConfig(wgDraft)
      else if (kind === 'xray' && xrayProfile) full = profileToPersistedConfig(xrayProfile)
      else return {} as JsonValue
      const cloned = JSON.parse(JSON.stringify(full)) as Record<string, unknown>
      return (projectForTab(cloned, effectiveTab) ?? {}) as JsonValue
    } catch {
      return {} as JsonValue
    }
  }, [kind, wgDraft, xrayProfile, effectiveTab])

  const editorValue = effectiveTab === 'all' ? monacoJson : tabDraft
  const editorOnChange = effectiveTab === 'all' ? handleAllJsonChange : handleTabJsonChange

  return (
    <div className="space-y-4">
      <div className="border-border bg-muted/15 rounded-lg border p-4 shadow-sm">
        <div className="flex gap-3 sm:gap-4">
          <Switch id="show-diff" className="mt-0.5 shrink-0" checked={showDiff} onCheckedChange={setShowDiff} aria-describedby={showDiff ? undefined : 'show-diff-hint'} />
          <div className="min-w-0 flex-1 space-y-1.5">
            <Label htmlFor="show-diff" className="block cursor-pointer text-sm leading-snug font-medium">
              {t('coreEditor.advanced.showDiff', { defaultValue: 'Show diff vs last saved' })}
            </Label>
            {!showDiff && (
              <p id="show-diff-hint" className="text-muted-foreground text-xs leading-relaxed">
                {t('coreEditor.advanced.autoApplyHint', {
                  defaultValue: 'Valid JSON is merged into the draft automatically after you stop typing.',
                })}
              </p>
            )}
            {showDiff && (
              <p className="text-muted-foreground text-xs leading-relaxed">
                {t('coreEditor.advanced.diffModeHint', {
                  defaultValue: 'Green and red lines show additions and removals compared to the last saved version.',
                })}
              </p>
            )}
          </div>
        </div>
      </div>

      {filterTabsAvailable && (
        <Tabs dir={dir} value={activeTab} onValueChange={value => setActiveTab(value as AdvancedTab)} className="min-w-0">
          <div className="-mx-1 overflow-x-auto px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <TabsList dir={dir} className="inline-flex h-10 w-auto">
              <TabsTrigger value="all" className="px-3">
                {t('coreEditor.advanced.tabs.all', { defaultValue: 'All' })}
              </TabsTrigger>
              {FILTER_TABS.map(tab => (
                <TabsTrigger key={tab} value={tab} className="px-3">
                  {tab === 'inbounds' && t('coreEditor.section.inbounds', { defaultValue: 'Inbounds' })}
                  {tab === 'outbounds' && t('coreEditor.section.outbounds', { defaultValue: 'Outbounds' })}
                  {tab === 'routing' && t('coreEditor.advanced.tabs.routingRules', { defaultValue: 'Routing Rules' })}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
        </Tabs>
      )}

      {showDiff ? (
        <ConfigDiffPanel before={beforeJson} after={afterJson} />
      ) : (
        <div className="space-y-2">
          <JsonCodeEditorPanel value={editorValue} onChange={editorOnChange} onValidate={handleEditorValidation} />
          {jsonValidation.error && !jsonValidation.isValid ? (
            <p role="alert" className="text-destructive text-[0.8rem] font-medium">
              {jsonValidation.error}
            </p>
          ) : null}
        </div>
      )}
    </div>
  )
}

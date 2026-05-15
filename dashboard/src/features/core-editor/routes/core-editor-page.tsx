import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import PageHeader from '@/components/layout/page-header'
import { Skeleton } from '@/components/ui/skeleton'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { CoreCommandMenu } from '@/features/core-editor/components/shared/core-command-menu'
import { CoreEditorLayout } from '@/features/core-editor/components/shell/core-editor-layout'
import { CoreSectionTabsPlaceholder } from '@/features/core-editor/components/shell/core-section-sidebar'
import { ValidationSummary, type ValidationListItem } from '@/features/core-editor/components/shared/validation-summary'
import type { SectionHeaderAddPulse } from '@/features/core-editor/hooks/use-section-header-add-pulse'
import { useXrayPersistValidationItems } from '@/features/core-editor/hooks/use-xray-persist-validation-items'
import { WireGuardCoreEditor } from '@/features/core-editor/components/wg/wireguard-core-editor'
import { XrayCoreEditor } from '@/features/core-editor/components/xray/xray-core-editor'
import { validateProfileForPersist } from '@/features/core-editor/kit/xray-adapter'
import { getWireGuardPersistConfig } from '@/features/core-editor/kit/wireguard-adapter'
import { selectCoreEditorHasActualChanges } from '@/features/core-editor/kit/core-editor-change-state'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import type { WgCoreSection, XrayCoreSection } from '@/features/core-editor/state/core-editor-store'
import type { CoreKind } from '@pasarguard/core-kit'
import { getGetCoreConfigQueryKey, useCreateCoreConfig, useGetCoreConfig, useModifyCoreConfig } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { ArrowLeft } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import useDirDetection from '@/hooks/use-dir-detection'

type LoadingCoreKind = 'xray' | 'wg'

function loadingSectionPageHeaderProps(coreKind?: LoadingCoreKind): { title: string; description?: string } {
  if (coreKind === 'wg') {
    return {
      title: 'coreEditor.section.interface',
      description: 'coreEditor.sectionDesc.wgInterface',
    }
  }
  if (coreKind === 'xray') {
    return {
      title: 'coreEditor.section.inbounds',
      description: 'coreEditor.sectionDesc.inbounds',
    }
  }
  return {
    title: 'coreEditor.loading.title',
    description: 'coreEditor.loading.description',
  }
}

/** Mirrors {@link CoreEditorLayout} shell: header → section header → tabs → list toolbar + table rows → sticky save bar. */
function CoreEditorLoadingSkeleton({ coreKind }: { coreKind?: LoadingCoreKind }) {
  const listGridCols =
    '24px 28px 52px minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) 44px' as const
  const pageHeader = loadingSectionPageHeaderProps(coreKind)
  const neutral = coreKind === undefined
  const formLike = neutral || coreKind === 'wg'

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-0" aria-busy="true">
      <CoreCommandMenu />
      <div className="px-4 pt-3 md:pt-6 pb-2 md:pb-0">
        <div className="flex min-w-0 items-start gap-2 sm:items-center sm:gap-3">
          <Skeleton className="h-10 w-10 shrink-0 rounded-md" />
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 sm:gap-3">
            <Skeleton className="h-10 min-h-10 min-w-0 flex-1 sm:max-w-md" />
            <Skeleton className="h-10 w-24 shrink-0 sm:w-52" />
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <PageHeader
          title={pageHeader.title}
          description={pageHeader.description}
          className="flex-wrap gap-x-3 gap-y-2 py-2.5 sm:gap-4 sm:py-4 md:pt-6"
        />

        {neutral ? (
          <div className="border-b px-4">
            <div className="flex min-w-0 gap-2 overflow-hidden py-2">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-9 w-24 shrink-0 rounded-md sm:w-32" />
              ))}
            </div>
          </div>
        ) : (
          <CoreSectionTabsPlaceholder kind={coreKind} />
        )}

        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-4">
          {formLike ? (
            <div className="space-y-5">
              <div className="grid grid-cols-1 gap-x-4 gap-y-5 sm:grid-cols-2">
                {Array.from({ length: 4 }, (_, i) => (
                  <div key={i} className="space-y-2">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-10 w-full rounded-md" />
                  </div>
                ))}
                <div className="space-y-2 sm:col-span-2">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-28 w-full rounded-md" />
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Skeleton className="h-10 w-full max-w-md rounded-md" />
                <div className="flex shrink-0 justify-end gap-2">
                  <Skeleton className="h-9 w-16 rounded-md" />
                  <Skeleton className="h-9 w-16 rounded-md" />
                </div>
              </div>

              <div
                className="text-muted-foreground grid min-w-0 items-center gap-3 rounded-md border bg-background/80 px-3 py-2 text-xs font-semibold uppercase tracking-wide"
                style={{ gridTemplateColumns: listGridCols }}
                aria-hidden
              >
                <Skeleton className="mx-auto h-3 w-3 justify-self-center rounded-sm" />
                <Skeleton className="mx-auto h-3 w-3.5 rounded-[3px]" />
                <Skeleton className="h-3 w-6" />
                <Skeleton className="h-3 w-8" />
                <Skeleton className="h-3 w-14" />
                <Skeleton className="h-3 w-10" />
                <Skeleton className="h-3 w-6 justify-self-end" />
              </div>

              {Array.from({ length: 4 }, (_, row) => (
                <div
                  key={row}
                  className="bg-background grid min-w-0 items-center gap-3 overflow-hidden rounded-md border px-3 py-3"
                  style={{ gridTemplateColumns: listGridCols }}
                >
                  <Skeleton className="mx-auto size-5 rounded-md" />
                  <Skeleton className="mx-auto h-3.5 w-3.5 rounded-[3px]" />
                  <Skeleton className="h-4 w-6 shrink-0" />
                  <Skeleton className="h-4 w-full max-w-40 min-w-0" />
                  <Skeleton className="h-4 w-full max-w-36 min-w-0" />
                  <Skeleton className="h-4 max-w-16 w-full min-w-0" />
                  <Skeleton className="size-8 justify-self-end rounded-md" />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="sticky bottom-0 z-20 flex flex-col gap-3 border-t bg-background/95 px-4 py-3 backdrop-blur supports-backdrop-filter:bg-background/80 sm:flex-row sm:items-center sm:justify-end">
        <div className="flex flex-wrap items-center justify-end gap-3">
          <div className="flex items-center gap-2 pr-2">
            <Skeleton className="size-4 rounded-sm" />
            <Skeleton className="h-4 w-28" />
          </div>
          <Skeleton className="h-9 w-20 rounded-md" />
          <Skeleton className="h-9 w-16 rounded-md" />
        </div>
      </div>
    </div>
  )
}

export default function CoreEditorPage() {
  const dir = useDirDetection()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { coreId: coreIdParam } = useParams<{ coreId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const isNew = coreIdParam === 'new'
  const numericId = coreIdParam && !isNew ? Number(coreIdParam) : NaN
  const validId = Number.isFinite(numericId) && numericId > 0

  const { data: coreData, isLoading, isError } = useGetCoreConfig(validId ? numericId : 0, {
    query: { enabled: validId },
  })

  const initFromCore = useCoreEditorStore(s => s.initFromCore)
  const initNew = useCoreEditorStore(s => s.initNew)
  const reset = useCoreEditorStore(s => s.reset)
  const hydrated = useCoreEditorStore(s => s.hydrated)
  const kind = useCoreEditorStore(s => s.kind)
  const coreName = useCoreEditorStore(s => s.coreName)
  const setCoreName = useCoreEditorStore(s => s.setCoreName)
  const hasActualChanges = useCoreEditorStore(selectCoreEditorHasActualChanges)
  const discardDraft = useCoreEditorStore(s => s.discardDraft)
  const markClean = useCoreEditorStore(s => s.markClean)
  const restartNodes = useCoreEditorStore(s => s.restartNodes)
  const setRestartNodes = useCoreEditorStore(s => s.setRestartNodes)
  const switchKind = useCoreEditorStore(s => s.switchKind)
  const fallbacksInboundTags = useCoreEditorStore(s => s.fallbacksInboundTags)
  const excludeInboundTags = useCoreEditorStore(s => s.excludeInboundTags)
  const xrayProfile = useCoreEditorStore(s => s.xrayProfile)
  const wgDraft = useCoreEditorStore(s => s.wgDraft)
  const xrayImportWarnings = useCoreEditorStore(s => s.xrayImportWarnings)
  const activeSection = useCoreEditorStore(s => s.activeSection)

  const [discardOpen, setDiscardOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [headerAddPulse, setHeaderAddPulse] = useState<SectionHeaderAddPulse>({ target: '', n: 0 })
  const [headerAddEpoch, setHeaderAddEpoch] = useState(0)

  /** Lets list sections ignore a stale pulse after the user switches tabs (see useSectionHeaderAddPulseEffect). */
  useLayoutEffect(() => {
    setHeaderAddEpoch(e => e + 1)
  }, [activeSection, kind])

  const createMutation = useCreateCoreConfig()
  const modifyMutation = useModifyCoreConfig()

  useEffect(() => {
    return () => {
      reset()
    }
  }, [reset])

  useEffect(() => {
    if (isNew) {
      const k = (searchParams.get('kind') as CoreKind | null) === 'wg' ? 'wg' : 'xray'
      const currentName = useCoreEditorStore.getState().coreName
      initNew(k, currentName)
    }
  }, [isNew, initNew, searchParams])

  const serverConfigJson = useMemo(
    () => (validId && coreData ? JSON.stringify(coreData.config) : null),
    [validId, coreData],
  )

  useEffect(() => {
    if (isNew || !validId || !coreData || serverConfigJson === null) return
    const state = useCoreEditorStore.getState()
    if (state.coreId !== coreData.id) {
      initFromCore(coreData)
      return
    }
    if (
      state.hydrated &&
      !selectCoreEditorHasActualChanges(state) &&
      !state.isNew &&
      state.serverHydratedConfigJson !== serverConfigJson
    ) {
      initFromCore(coreData, { preserveNavigation: true })
    }
  }, [isNew, validId, coreData, serverConfigJson, initFromCore])

  const xrayPersistValidationItems = useXrayPersistValidationItems()

  const preSaveIssues = useMemo((): ValidationListItem[] => {
    if (!hydrated) return []
    if (kind === 'wg' && wgDraft) {
      const r = getWireGuardPersistConfig(wgDraft)
      if (!r.ok && 'draftIssues' in r) {
        return (r.draftIssues ?? []).map(issue => ({ source: 'wireguard' as const, issue }))
      }
      if (!r.ok && 'kitIssues' in r) {
        return r.kitIssues.map(issue => ({ source: 'core-kit' as const, issue }))
      }
    }
    if (kind === 'xray' && xrayProfile) return xrayPersistValidationItems
    return []
  }, [hydrated, kind, wgDraft, xrayProfile, xrayPersistValidationItems])

  const handleBack = useCallback(() => {
    if (hasActualChanges) {
      setDiscardOpen(true)
      return
    }
    navigate('/nodes/cores')
  }, [hasActualChanges, navigate])

  const confirmDiscardAndLeave = useCallback(() => {
    discardDraft()
    setDiscardOpen(false)
    navigate('/nodes/cores')
  }, [discardDraft, navigate])

  const handleSave = useCallback(async () => {
    const name = coreName.trim()
    if (!name) {
      toast.error(t('coreEditor.nameRequired', { defaultValue: 'Name is required' }))
      return
    }
    if (preSaveIssues.length > 0) {
      toast.error(t('coreEditor.fixValidation', { defaultValue: 'Fix validation errors before saving' }))
      return
    }
    setSaving(true)
    try {
      if (kind === 'wg') {
        if (!wgDraft) return
        const r = getWireGuardPersistConfig(wgDraft)
        if (!r.ok) {
          toast.error(t('coreEditor.fixValidation', { defaultValue: 'Fix validation errors before saving' }))
          return
        }
        const cfg = r.config
        if (isNew) {
          const res = await createMutation.mutateAsync({
            data: {
              name,
              type: 'wg',
              config: cfg,
              exclude_inbound_tags: [],
              fallbacks_inbound_tags: [],
            },
          })
          toast.success(t('coreConfigModal.createSuccess', { name }))
          markClean()
          queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
          queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
          navigate(`/nodes/cores/${res.id}`, { replace: true })
        } else if (validId) {
          await modifyMutation.mutateAsync({
            coreId: numericId,
            data: {
              name,
              type: 'wg',
              config: cfg,
              exclude_inbound_tags: [],
              fallbacks_inbound_tags: [],
            },
            params: { restart_nodes: restartNodes },
          })
          toast.success(t('coreConfigModal.editSuccess', { name }))
          markClean()
          queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
          queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
          queryClient.invalidateQueries({ queryKey: getGetCoreConfigQueryKey(numericId) })
        }
        return
      }

      if (kind === 'xray' && xrayProfile) {
        const vr = validateProfileForPersist(xrayProfile)
        if (!vr.ok) {
          const n = vr.strictBlockers.length + vr.coreKitIssues.length
          toast.error(
            t('coreEditor.validationFailedToast', {
              count: n,
              defaultValue: `Fix ${n} validation issue(s) before saving.`,
            }),
          )
          return
        }
        const cfg = vr.config
        if (isNew) {
          const res = await createMutation.mutateAsync({
            data: {
              name,
              type: 'xray',
              config: cfg,
              exclude_inbound_tags: excludeInboundTags,
              fallbacks_inbound_tags: fallbacksInboundTags,
            },
          })
          toast.success(t('coreConfigModal.createSuccess', { name }))
          markClean()
          queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
          queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
          navigate(`/nodes/cores/${res.id}`, { replace: true })
        } else if (validId) {
          await modifyMutation.mutateAsync({
            coreId: numericId,
            data: {
              name,
              type: 'xray',
              config: cfg,
              exclude_inbound_tags: excludeInboundTags,
              fallbacks_inbound_tags: fallbacksInboundTags,
            },
            params: { restart_nodes: restartNodes },
          })
          toast.success(t('coreConfigModal.editSuccess', { name }))
          markClean()
          queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
          queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
          queryClient.invalidateQueries({ queryKey: getGetCoreConfigQueryKey(numericId) })
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }, [
    coreName,
    kind,
    wgDraft,
    xrayProfile,
    preSaveIssues.length,
    isNew,
    validId,
    numericId,
    fallbacksInboundTags,
    excludeInboundTags,
    restartNodes,
    createMutation,
    modifyMutation,
    markClean,
    navigate,
    t,
  ])

  const header = (
    <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
      <div className="flex min-w-0 flex-1 gap-2 items-center sm:gap-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className={cn('mt-0.5 h-11 w-11 shrink-0 sm:mt-0', dir === 'rtl' && 'rotate-180')}
          onClick={handleBack}
          aria-label={t('back', { defaultValue: 'Back' })}
        >
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex min-w-0 flex-row flex-wrap items-center gap-2 sm:gap-3">
            <div className="min-w-0 flex-1">
              <Input
                value={coreName}
                onChange={e => setCoreName(e.target.value)}
                className="h-10 font-medium sm:max-w-md"
                placeholder={t('coreConfigModal.namePlaceholder', { defaultValue: 'Core name' })}
              />
            </div>
            <Select
              value={kind === 'wg' ? 'wg' : 'xray'}
              onValueChange={value => {
                const nextKind = value === 'wg' ? 'wg' : 'xray'
                if (isNew) {
                  setSearchParams(
                    prev => {
                      const p = new URLSearchParams(prev)
                      if (nextKind === 'wg') p.set('kind', 'wg')
                      else p.delete('kind')
                      return p
                    },
                    { replace: true },
                  )
                  return
                }
                switchKind(nextKind)
              }}
            >
              <SelectTrigger
                className="h-10 w-24 shrink-0 px-2 sm:w-[200px] sm:px-3"
                aria-label={t('coreConfigModal.backendType', { defaultValue: 'Backend type' })}
              >
                <SelectValue placeholder={t('coreConfigModal.backendType', { defaultValue: 'Type' })} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="xray">Xray</SelectItem>
                <SelectItem value="wg">WireGuard</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {kind === 'xray' && xrayImportWarnings.length > 0 && (
            <Alert>
              <AlertTitle>{t('coreEditor.importWarnings', { defaultValue: 'Import notes' })}</AlertTitle>
              <AlertDescription>
                <ul className="list-inside list-disc text-sm">
                  {xrayImportWarnings.slice(0, 6).map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}
        </div>
      </div>
    </div>
  )

  const sectionHeaderConfig = useMemo(() => {
    if (kind === 'wg') {
      const section = activeSection as WgCoreSection
      return {
        interface: {
          title: 'coreEditor.section.interface',
          description: 'coreEditor.sectionDesc.wgInterface',
        },
        advanced: {
          title: 'coreEditor.section.advanced',
          description: 'coreEditor.sectionDesc.advanced',
        },
      }[section]
    }

    const section = activeSection as XrayCoreSection
    return {
      inbounds: {
        title: 'coreEditor.section.inbounds',
        description: 'coreEditor.sectionDesc.inbounds',
        buttonText: 'coreEditor.inbound.add',
      },
      outbounds: {
        title: 'coreEditor.section.outbounds',
        description: 'coreEditor.sectionDesc.outbounds',
        buttonText: 'coreEditor.outbound.add',
      },
      routing: {
        title: 'coreEditor.section.routing',
        description: 'coreEditor.sectionDesc.routing',
        buttonText: 'coreEditor.routing.addRule',
      },
      balancers: {
        title: 'coreEditor.section.balancers',
        description: 'coreEditor.sectionDesc.balancers',
        buttonText: 'coreEditor.balancer.add',
      },
      dns: {
        title: 'coreEditor.section.dns',
        description: 'coreEditor.sectionDesc.dns',
      },
      bindings: {
        title: 'coreEditor.section.bindings',
        description: 'coreEditor.sectionDesc.bindings',
      },
      advanced: {
        title: 'coreEditor.section.advanced',
        description: 'coreEditor.sectionDesc.advanced',
      },
    }[section]
  }, [kind, activeSection])

  if (!isNew && validId && isLoading) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <CoreEditorLoadingSkeleton />
      </div>
    )
  }

  if (!isNew && validId && (isError || !coreData)) {
    return (
      <div className="space-y-4 py-8">
        <p className="text-sm text-destructive">{t('coreEditor.loadFailed', { defaultValue: 'Could not load this core.' })}</p>
        <Button type="button" variant="outline" onClick={() => navigate('/nodes/cores')}>
          {t('coreEditor.backToList', { defaultValue: 'Back to cores' })}
        </Button>
      </div>
    )
  }

  if (!isNew && !validId) {
    return (
      <div className="space-y-4 py-8">
        <p className="text-sm text-muted-foreground">{t('coreEditor.invalidId', { defaultValue: 'Invalid core id.' })}</p>
        <Button type="button" variant="outline" onClick={() => navigate('/nodes/cores')}>
          {t('coreEditor.backToList', { defaultValue: 'Back to cores' })}
        </Button>
      </div>
    )
  }

  if (!hydrated && !isNew && validId) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <CoreEditorLoadingSkeleton coreKind={coreData?.type === 'wg' ? 'wg' : 'xray'} />
      </div>
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <CoreEditorLayout
        header={header}
        sectionHeader={
          sectionHeaderConfig ? (
            <PageHeader
              title={sectionHeaderConfig.title}
              description={sectionHeaderConfig.description}
              className="flex-wrap gap-x-3 gap-y-2 py-2.5 sm:gap-4 sm:py-4 md:pt-6"
              buttonText={sectionHeaderConfig.buttonText}
              onButtonClick={sectionHeaderConfig.buttonText ? () => setHeaderAddPulse(p => ({ target: String(activeSection), n: p.n + 1 })) : undefined}
            />
          ) : undefined
        }
        main={
          <div className="space-y-6">
            <ValidationSummary items={preSaveIssues} />
            {kind === 'wg' ? (
              <WireGuardCoreEditor />
            ) : (
              <XrayCoreEditor headerAddPulse={headerAddPulse} headerAddEpoch={headerAddEpoch} />
            )}
          </div>
        }
        dirty={hasActualChanges}
        onSave={handleSave}
        onDiscard={() => discardDraft()}
        saving={saving || createMutation.isPending || modifyMutation.isPending}
        showRestart={!isNew}
        restartNodes={restartNodes}
        onRestartChange={setRestartNodes}
      />
      <AlertDialog open={discardOpen} onOpenChange={setDiscardOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('coreEditor.discardTitle', { defaultValue: 'Discard changes?' })}</AlertDialogTitle>
            <AlertDialogDescription>{t('coreEditor.discardDesc', { defaultValue: 'You have unsaved edits. Leave without saving?' })}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDiscardAndLeave}>{t('coreEditor.leave', { defaultValue: 'Leave' })}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

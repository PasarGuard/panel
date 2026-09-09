import { CodeEditorPanel } from '@/components/common/code-editor-panel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAdmin } from '@/hooks/use-admin'
import { hasPermission } from '@/utils/rbac'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Copy, FileCode2, Plus, RefreshCw, Save, Settings2, Smartphone } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import { Link, useBlocker, useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'
import type { AdminDetails, ClientTemplateType } from '@/service/api'
import { DEFAULT_TEMPLATE_CONTENT } from '@/features/templates/forms/client-template-form'
import { NativeConfigurationEditor } from '@/features/client-settings/components/native-configuration-editor'
import { makeClientConfiguration } from '@/features/client-settings/forms/native-configuration'
import { DeliveryRuleEditor, DeliveryRules, selectClass } from '@/features/client-settings/delivery-rule-editor'
import { WorkspacePreviewPanel } from '@/features/client-settings/workspace-preview'
import { applyWorkspace, getWorkspace } from '@/features/client-settings/workspace-api'
import {
  assignedRules,
  bindRule,
  changeForApplication,
  CLIENT_APPLICATIONS,
  copyForApplication,
  configurationLabel,
  applicationDocument,
  workspaceHasChanges,
  codeSourceError,
  formatForType,
  isRevisionConflict,
  NATIVE_TYPES,
  ruleTemplateId,
  templateUsages,
  switchConfigurationDraft,
  type NativeFormat,
  type TemplateDraft,
  type WorkspaceChange,
  type WorkspaceSnapshot,
} from '@/features/client-settings/workspace-model'

const WORKSPACE_KEY = ['client-settings-workspace']
type EditorSection = 'routing' | 'dns' | 'delivery'

export default function ClientSettingsPage() {
  const { t, i18n } = useTranslation()
  const { admin: adminResponse } = useAdmin()
  // The shared hook returns the decoded HTTP body; its generated response-wrapper
  // annotation is broader than the runtime value. Keep that boundary local.
  const admin = adminResponse as unknown as AdminDetails | undefined
  const queryClient = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const canRead = hasPermission(admin, 'settings', 'read') && hasPermission(admin, 'client_templates', 'read')
  const canSaveRules = hasPermission(admin, 'settings', 'update')
  const canCreate = canSaveRules && hasPermission(admin, 'client_templates', 'create')
  const canUpdate = canSaveRules && hasPermission(admin, 'client_templates', 'update')
  const query = useQuery({ queryKey: WORKSPACE_KEY, queryFn: ({ signal }) => getWorkspace(signal), enabled: canRead, retry: false, refetchOnWindowFocus: false })
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null)
  const [change, setChange] = useState<WorkspaceChange | null>(null)
  const [section, setSection] = useState<EditorSection>('routing')
  const [view, setView] = useState<'visual' | 'code'>('visual')
  const [mode, setMode] = useState<ClientTemplateType>('happ_routing')
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [busy, setBusy] = useState(false)
  const [valid, setValid] = useState(true)
  const [nativeValidity, setNativeValidity] = useState({ routing: true, dns: true })
  const [nativeDirty, setNativeDirty] = useState({ routing: false, dns: false })
  const [editorEpoch, setEditorEpoch] = useState(0)
  const [search, setSearch] = useState('')
  const [selectedSource, setSelectedSource] = useState('')
  const modeDrafts = useRef<Partial<Record<ClientTemplateType, TemplateDraft>>>({})
  const pageRef = useRef<HTMLDivElement>(null)
  const [actionBounds, setActionBounds] = useState({ left: 0, width: 0 })
  const [, , tab = 'applications', itemId] = location.pathname.split('/')
  const app = tab === 'applications' ? CLIENT_APPLICATIONS.find(item => item.id === itemId) : undefined
  const libraryItem = tab === 'configurations' && itemId && itemId !== 'new' ? snapshot?.templates.find(item => item.id === Number(itemId)) : undefined
  const isNew = tab === 'configurations' && itemId === 'new'
  const editing = Boolean(app || libraryItem || isNew)
  const rules = change?.rules ?? snapshot?.subscription.rules ?? []
  const assignments = app ? assignedRules(snapshot?.subscription.rules ?? [], app.id) : []
  // Keep editing the same rule even when its application label changes in a draft.
  const appRule = assignments[0] ?? (app && change ? assignedRules(change.rules, app.id)[0] : undefined)
  const sourceId = ruleTemplateId(appRule ? rules[appRule.index] : undefined)
  const assignedSource = snapshot?.templates.find(item => item.id === sourceId)
  const currentSource = assignedSource ?? (app ? snapshot?.templates.find(item => item.template_type === NATIVE_TYPES[app.format] && item.is_default) : undefined)
  const template = change?.template ?? libraryItem ?? currentSource
  const canSave = canSaveRules && (!change?.template || (change.template.id ? canUpdate : canCreate))
  const payload: WorkspaceChange = change ?? { expected_revision: snapshot?.revision ?? '', rules }
  const userAgent = app?.userAgent ?? ''
  const hasNativeDirty = nativeDirty.routing || nativeDirty.dns
  const sourceError = template ? codeSourceError(template.template_type, template.content) : null
  const documentValid = valid && !hasNativeDirty && !sourceError && (view === 'code' || !template || template.template_type.includes('user_agent') || (nativeValidity.routing && nativeValidity.dns))
  const dirty = workspaceHasChanges(snapshot, change) || hasNativeDirty
  const labelForType = (type: string) => configurationLabel(type)
  const editableAssigned = assignedSource && !assignedSource.is_default && !assignedSource.is_system
  const initialMode = libraryItem?.template_type ?? currentSource?.template_type ?? (app ? NATIVE_TYPES[app.format] : 'xray_subscription')
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname)

  useLayoutEffect(() => {
    if (!dirty || !pageRef.current) return
    const element = pageRef.current
    const measure = () => {
      const { left, width } = element.getBoundingClientRect()
      setActionBounds(previous => (previous.left === left && previous.width === width ? previous : { left, width }))
    }
    measure()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    observer?.observe(element)
    window.addEventListener('resize', measure)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [dirty, t])

  useEffect(() => {
    if (blocker.state !== 'blocked') return
    if (window.confirm(t('clientSettings.discardConfirm', 'Discard unsaved changes?'))) blocker.proceed()
    else blocker.reset()
  }, [blocker, t])

  useEffect(() => {
    if (query.data && !change) setSnapshot(query.data)
  }, [query.data, change])
  useEffect(() => {
    setChange(null)
    setNativeDirty({ routing: false, dns: false })
    setNativeValidity({ routing: true, dns: true })
    setEditorEpoch(value => value + 1)
    setError('')
    setConflict(false)
    setSection('routing')
    setView('visual')
    setValid(true)
    setSelectedSource('')
    modeDrafts.current = {}
  }, [location.pathname])
  useEffect(() => {
    setMode(initialMode)
  }, [initialMode])
  useEffect(() => {
    if (!dirty) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  function go(path: string) {
    navigate(path)
  }
  function assignSource() {
    const source = snapshot?.templates.find(item => item.id === Number(selectedSource))
    if (!source || !snapshot || !app) return
    const next = changeForApplication({ ...snapshot, subscription: { ...snapshot.subscription, rules } }, app, source, appRule?.index)
    setChange({ expected_revision: next.expected_revision, rules: next.rules })
  }
  function newContent(type: ClientTemplateType) {
    if (type === 'user_agent' || type === 'grpc_user_agent') return DEFAULT_TEMPLATE_CONTENT[type]
    return makeClientConfiguration(formatForType(type))
  }
  function switchView(next: 'visual' | 'code') {
    if (hasNativeDirty) {
      toast.error(t('clientSettings.applyBeforeSwitch', 'Apply or cancel the field changes before switching editors.'))
      return
    }
    setView(next)
    setValid(true)
  }
  function createDraft(type = mode) {
    if (!snapshot) return
    const source = currentSource?.template_type === type ? currentSource : snapshot.templates.find(item => item.template_type === type && item.is_default)
    const draft = modeDrafts.current[type] ?? (source && app ? copyForApplication(source, app.name) : { name: app?.name ?? '', template_type: type, content: newContent(type), is_default: false })
    setChange(
      app ? changeForApplication({ ...snapshot, subscription: { ...snapshot.subscription, rules } }, app, draft, appRule?.index) : { expected_revision: snapshot.revision, template: draft, rules },
    )
    setValid(true)
  }
  function switchMode(type: ClientTemplateType) {
    if (hasNativeDirty) {
      toast.error(t('clientSettings.applyBeforeSwitch', 'Apply or cancel the field changes before switching editors.'))
      return
    }
    setMode(type)
    setValid(true)
    if (!snapshot) return
    if (!change?.template) {
      if (type !== template?.template_type) {
        if (app && currentSource) modeDrafts.current[currentSource.template_type] = applicationDocument(currentSource, app.name)
        createDraft(type)
      }
      return
    }
    const draft = switchConfigurationDraft(change.template, type, modeDrafts.current, newContent)
    if (app) {
      const index = change.bind_rule_indices?.[0]
      if (index !== undefined) {
        const target = type === 'happ_routing' ? 'links' : formatForType(type) === 'clash' ? 'clash_meta' : formatForType(type) === 'sing_box' ? 'sing_box' : 'xray'
        setChange({ ...change, template: draft, rules: change.rules.map((rule, i) => (i === index ? bindRule({ ...rule, target }, type, draft.id) : rule)) })
      }
    } else setChange({ ...change, template: draft })
  }
  function editTemplate(updates: Partial<Pick<TemplateDraft, 'name' | 'content' | 'is_default'>>) {
    if (!snapshot || !template) return
    if (Object.entries(updates).every(([key, value]) => template[key as 'name' | 'content' | 'is_default'] === value)) return
    const draft = change?.template ?? (app && currentSource ? applicationDocument(currentSource, app.name) : libraryItem)
    if (!draft) return
    const next = { id: draft.id, name: draft.name, template_type: draft.template_type, content: draft.content, is_default: draft.is_default, ...updates }
    const base = change ?? (app ? changeForApplication(snapshot, app, next, appRule?.index) : { expected_revision: snapshot.revision, rules: snapshot.subscription.rules })
    setChange({ ...base, template: next, ...(app ? { bind_rule_indices: base.bind_rule_indices ?? [appRule?.index ?? 0] } : {}) })
  }
  function editContent(content: string) {
    if (view === 'code') setValid(true)
    editTemplate({ content })
  }
  async function save() {
    if (!change || !dirty || !canSave || !documentValid) return
    setBusy(true)
    setError('')
    setConflict(false)
    try {
      const result = await applyWorkspace(change)
      setSnapshot(result)
      setChange(null)
      modeDrafts.current = {}
      queryClient.setQueryData(WORKSPACE_KEY, result)
      await queryClient.invalidateQueries({
        predicate: query =>
          !query.queryKey.includes('client-settings-workspace') && query.queryKey.some(key => typeof key === 'string' && (key.includes('/api/client_template') || key.includes('/api/settings'))),
      })
      if (result.sync_warning === 'worker_notification_failed') toast.warning(t('clientSettings.savedSyncWarning', 'Saved; other processes could not be notified. Local settings are updated.'))
      else toast.success(t('clientSettings.saved', 'Client settings saved'))
      if (isNew) navigate('/client-settings/configurations')
    } catch (error) {
      const isConflict = isRevisionConflict(error)
      setConflict(isConflict)
      const detail = (error as { data?: { detail?: unknown } })?.data?.detail
      setError(
        isConflict
          ? t('clientSettings.conflict', 'Another administrator changed these settings. Your draft is preserved. Copy it before reloading, then apply your changes to the latest version.')
          : typeof detail === 'string'
            ? detail
            : t('clientSettings.saveFailed', 'Could not save client settings. Your draft is preserved.'),
      )
    } finally {
      setBusy(false)
    }
  }
  function cancel() {
    setEditorEpoch(value => value + 1)
    setNativeDirty({ routing: false, dns: false })
    setNativeValidity({ routing: true, dns: true })
    setChange(null)
    modeDrafts.current = {}
    setError('')
    setConflict(false)
    setValid(true)
    setMode(libraryItem?.template_type ?? currentSource?.template_type ?? (app ? NATIVE_TYPES[app.format] : 'xray_subscription'))
  }

  if (!canRead) return <p className="p-6">{t('clientSettings.readPermission', 'Settings and client template read permissions are required.')}</p>
  if (query.isLoading || (!snapshot && !query.isError)) return <div className="text-muted-foreground p-6">{t('clientSettings.loading', 'Loading client settings…')}</div>
  if (!snapshot)
    return (
      <div className="space-y-3 p-6">
        <p role="alert" className="text-destructive">
          {t('clientSettings.loadFailed', 'Could not load client settings.')}
        </p>
        <Button variant="outline" onClick={() => query.refetch()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          {t('clientSettings.retry', 'Retry')}
        </Button>
      </div>
    )

  const usages = template?.id ? templateUsages(snapshot.subscription.rules, template.id) : []
  const nativeFormat = formatForType(template?.template_type ?? mode)
  const userAgentTemplate = template?.template_type === 'user_agent' || template?.template_type === 'grpc_user_agent'
  const editorEnabled = Boolean(template) && (change?.template ? (change.template.id ? canUpdate : canCreate) : libraryItem ? canUpdate : editableAssigned ? canUpdate : canCreate)
  const name = app?.name ?? libraryItem?.name ?? t('clientSettings.newConfiguration', 'New configuration')

  return (
    <div ref={pageRef} className={`w-full min-w-0 ${dirty ? 'pb-28' : ''}`}>
      {!editing && (
        <header className="space-y-2 px-4 py-5 sm:px-6">
          {tab !== 'applications' && (
            <Link className="text-muted-foreground inline-flex items-center gap-2 text-sm hover:underline" to="/client-settings/applications">
              <ArrowLeft className="h-4 w-4" />
              {t('clientSettings.applications', 'Applications')}
            </Link>
          )}
          <div className="flex items-center gap-3">
            <Settings2 className="text-primary h-6 w-6" />
            <h1 className="text-2xl font-semibold">
              {tab === 'configurations'
                ? t('clientSettings.savedConfigurations', 'Saved configurations')
                : tab === 'rules'
                  ? t('clientSettings.applicationMatchingOrder', 'Application matching order')
                  : t('clientSettings.applications', 'Applications')}
            </h1>
          </div>
          {tab === 'applications' && <p className="text-muted-foreground text-sm">{t('clientSettings.description', 'Configure applications, reuse documents and control subscription delivery.')}</p>}
        </header>
      )}
      <main className="space-y-5 p-4 sm:p-6">
        {error && (
          <div role="alert" className="border-destructive/40 bg-destructive/5 space-y-3 rounded-xl border p-4">
            <p className="text-destructive text-sm">{error}</p>
            {conflict && (
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={async () => {
                    await navigator.clipboard.writeText(JSON.stringify(change, null, 2))
                    toast.success(t('clientSettings.draftCopied', 'Draft copied'))
                  }}
                >
                  <Copy className="mr-2 h-4 w-4" />
                  {t('clientSettings.copyDraft', 'Copy draft')}
                </Button>
                <Button
                  variant="outline"
                  onClick={async () => {
                    if (window.confirm(t('clientSettings.discardConfirm', 'Discard unsaved changes?'))) {
                      cancel()
                      await query.refetch()
                    }
                  }}
                >
                  {t('clientSettings.reload', 'Reload latest settings')}
                </Button>
              </div>
            )}
          </div>
        )}
        {tab === 'applications' && !app && (
          <>
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {CLIENT_APPLICATIONS.map(application => {
                const owned = assignedRules(snapshot.subscription.rules, application.id)
                const selected = snapshot.templates.find(item => item.id === ruleTemplateId(owned[0]?.rule))
                return (
                  <article key={application.id} className="bg-card flex flex-col gap-4 rounded-xl border p-5">
                    <div className="flex items-center justify-between">
                      <Smartphone className="text-primary h-6 w-6" />
                    </div>
                    <h2 className="text-lg font-semibold">{application.name}</h2>
                    <p className="text-muted-foreground min-h-10 text-sm break-words">
                      {selected?.name ??
                        (owned.length
                          ? t('clientSettings.usesDefault', 'Uses the default for its response format')
                          : t('clientSettings.noAssignment', 'No explicit assignment. Check the effective response in preview.'))}
                    </p>
                    <Button variant="outline" className="mt-auto justify-between" onClick={() => go(`/client-settings/applications/${application.id}`)}>
                      {t('clientSettings.openApplication', 'Open settings')}
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </article>
                )
              })}
            </div>
            <div className="text-muted-foreground flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <Link className="hover:underline" to="/client-settings/configurations">
                {t('clientSettings.savedConfigurations', 'Saved configurations')}
              </Link>
              <Link className="hover:underline" to="/client-settings/rules">
                {t('clientSettings.applicationMatchingOrder', 'Application matching order')}
              </Link>
            </div>
          </>
        )}
        {tab === 'configurations' && !editing && (
          <>
            <div className="flex flex-wrap gap-3">
              <Input
                className="max-w-md"
                aria-label={t('clientSettings.search', 'Search configurations')}
                placeholder={t('clientSettings.search', 'Search configurations')}
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
              {canCreate && (
                <Button onClick={() => go('/client-settings/configurations/new')}>
                  <Plus className="mr-2 h-4 w-4" />
                  {t('clientSettings.newConfiguration', 'New configuration')}
                </Button>
              )}
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {snapshot.templates
                .filter(item => `${item.name} ${labelForType(item.template_type)}`.toLowerCase().includes(search.toLowerCase()))
                .map(item => {
                  const references = templateUsages(snapshot.subscription.rules, item.id)
                  return (
                    <button
                      key={item.id}
                      className="bg-card hover:bg-accent/30 flex min-w-0 items-start gap-3 rounded-xl border p-4 text-start"
                      onClick={() => go(`/client-settings/configurations/${item.id}`)}
                    >
                      <FileCode2 className="text-muted-foreground mt-1 h-5 w-5 shrink-0" />
                      <div className="min-w-0 flex-1">
                        <h2 className="font-medium break-words">{item.name}</h2>
                        <p className="text-muted-foreground mt-1 text-xs">
                          {labelForType(item.template_type)} · #{item.id}
                          {item.is_default ? ` · ${t('clientSettings.default', 'Default')}` : ''}
                        </p>
                        <p className="text-muted-foreground mt-2 text-xs">{t('clientSettings.usageCount', { defaultValue: 'Used by {{count}} delivery rules', count: references.length })}</p>
                      </div>
                      <ArrowRight className="h-4 w-4 shrink-0" />
                    </button>
                  )
                })}
            </div>
          </>
        )}
        {tab === 'rules' && (
          <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
            <DeliveryRules rules={rules} templates={snapshot.templates} readOnly={!canSaveRules || busy} onChange={rules => setChange({ expected_revision: snapshot.revision, rules })} />
            <WorkspacePreviewPanel
              key="rules"
              change={payload}
              userAgent=""
              draft={dirty}
              canPreview={hasPermission(admin, 'users', 'read')}
              canReadSimple={hasPermission(admin, 'users', 'read_simple')}
              ready={!hasNativeDirty && !sourceError}
            />
          </div>
        )}
        {editing && (
          <>
            <div className="flex flex-wrap items-center gap-3">
              <Button variant="ghost" size="icon" aria-label={t('clientSettings.back', 'Back')} onClick={() => go(`/client-settings/${tab}`)}>
                <ArrowLeft className="h-5 w-5" />
              </Button>
              <div>
                <div className="flex flex-wrap items-baseline gap-3">
                  <h1 className="text-xl font-semibold">{name}</h1>
                  {app && template && <span className="text-muted-foreground text-sm">{template?.name}</span>}
                </div>
                {app && template && (assignments.length > 0 || change?.template) && (
                  <p className="text-muted-foreground mt-1 text-sm">
                    {template.template_type === 'happ_routing'
                      ? t('clientSettings.happResult', 'Server list + Happ routing')
                      : t('clientSettings.nativeResult', {
                          defaultValue: '{{format}} configuration: routing and DNS',
                          format: configurationLabel(template.template_type),
                        })}
                  </p>
                )}
                {app && !assignments.length && !change?.template && (
                  <p className="text-muted-foreground mt-1 text-sm">{t('clientSettings.noAssignment', 'No explicit assignment. Check the effective response in preview.')}</p>
                )}
              </div>
            </div>
            <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div className="min-w-0 space-y-4">
                {template && !userAgentTemplate && (
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-3">
                    <div className="flex flex-wrap gap-1">
                      {(['routing', 'dns', ...(app ? ['delivery'] : [])] as EditorSection[]).map(value => (
                        <Button
                          key={value}
                          aria-pressed={section === value}
                          variant={section === value ? 'secondary' : 'ghost'}
                          size="sm"
                          onClick={() => {
                            setSection(value)
                          }}
                        >
                          {t(`clientSettings.${value}`, value === 'routing' ? 'Routing' : value === 'dns' ? 'DNS' : 'Subscription delivery')}
                        </Button>
                      ))}
                    </div>
                    {section !== 'delivery' && (
                      <div className="flex rounded-lg border p-1">
                        <Button size="sm" aria-pressed={view === 'visual'} variant={view === 'visual' ? 'secondary' : 'ghost'} onClick={() => switchView('visual')}>
                          {t('clientSettings.visual', 'Visual')}
                        </Button>
                        <Button size="sm" aria-pressed={view === 'code'} variant={view === 'code' ? 'secondary' : 'ghost'} onClick={() => switchView('code')}>
                          {t('clientSettings.code', 'Code')}
                        </Button>
                      </div>
                    )}
                  </div>
                )}
                {app && !template && canCreate && <Button onClick={() => createDraft()}>{t('clientSettings.configure', 'Configure')}</Button>}
                {app && currentSource && !editableAssigned && !change?.template && (
                  <p className="text-muted-foreground text-sm">{t('clientSettings.defaultCopyOnSave', 'Your changes will be saved as a separate configuration for this application.')}</p>
                )}
                {app && !template && canSaveRules && (
                  <div className="space-y-2 rounded-xl border p-4">
                    <label className="block space-y-1 text-sm">
                      {t('clientSettings.selectExisting', 'Use an existing configuration')}
                      <select className={selectClass} value={selectedSource} onChange={e => setSelectedSource(e.target.value)}>
                        <option value="">{t('clientSettings.selectDocument', 'Select a document')}</option>
                        {snapshot.templates
                          .filter(item => item.template_type === NATIVE_TYPES[app.format] || (app.id === 'happ' && item.template_type === 'xray_subscription'))
                          .map(item => (
                            <option key={item.id} value={item.id}>
                              {item.name} · {labelForType(item.template_type)}
                            </option>
                          ))}
                      </select>
                    </label>
                    <Button variant="outline" disabled={!selectedSource} onClick={assignSource}>
                      {t('clientSettings.assign', 'Assign to application')}
                    </Button>
                    {change && !change.template && (
                      <p className="text-muted-foreground text-xs">{t('clientSettings.assignmentPending', 'Assignment is ready. Preview the response and save to apply.')}</p>
                    )}
                  </div>
                )}
                {app && assignments.length > 1 && (
                  <p className="text-muted-foreground rounded-xl border p-3 text-sm">
                    {t('clientSettings.multipleRules', 'This application has multiple rules. Configure edits the first assignment; review all variants in Delivery rules.')}
                  </p>
                )}
                {app && !assignments.length && (!template || section === 'delivery') && (
                  <p className="text-muted-foreground text-sm">
                    {t('clientSettings.newRuleHelp', 'Saving a configuration adds a dedicated rule before existing rules. Review the expression and response in Subscription delivery.')}
                  </p>
                )}
                {(isNew || app?.id === 'happ') && (!template || !app || section === 'delivery') && (
                  <div className="bg-card space-y-3 rounded-xl border p-4">
                    <label className="block space-y-1 text-sm">
                      {t('clientSettings.mode', 'Configuration mode')}
                      <select className={selectClass} value={change?.template?.template_type ?? mode} onChange={e => switchMode(e.target.value as ClientTemplateType)} disabled={busy}>
                        {isNew ? (
                          Object.entries(NATIVE_TYPES).map(([, type]) => (
                            <option key={type} value={type}>
                              {labelForType(type)}
                            </option>
                          ))
                        ) : (
                          <option value={NATIVE_TYPES[app!.format]}>{app?.name}</option>
                        )}
                        {app?.id === 'happ' && <option value="xray_subscription">{t('clientSettings.happFullXray', 'Full Xray configuration (alternative)')}</option>}
                        {isNew && (
                          <>
                            <option value="user_agent">HTTP User-Agent</option>
                            <option value="grpc_user_agent">gRPC User-Agent</option>
                          </>
                        )}
                      </select>
                    </label>
                    <p className="text-muted-foreground text-xs">{t('clientSettings.modeHelpSimple', 'Choose the configuration the application will receive.')}</p>
                    {isNew && !change?.template && canCreate && (
                      <Button variant="outline" onClick={() => createDraft()}>
                        {t('clientSettings.createDocument', 'Create document')}
                      </Button>
                    )}
                  </div>
                )}
                {template && (
                  <>
                    {(app || usages.length > 0) && (
                      <details className="rounded-lg border px-3 py-2 text-sm">
                        <summary className="text-muted-foreground cursor-pointer">{t('clientSettings.configurationOptions', 'Configuration options')}</summary>
                        <div className="mt-3 space-y-2">
                          <Link className="inline-block hover:underline" to="/client-settings/configurations">
                            {t('clientSettings.savedConfigurations', 'Saved configurations')}
                          </Link>
                          {usages.length > 0 && <p className="text-muted-foreground">{t('clientSettings.usedBy', 'Used by delivery rules')}:</p>}
                          {usages.map(({ rule, index }) => (
                            <p className="text-muted-foreground text-xs break-all" key={index}>
                              #{index + 1} · {rule.ui_application ?? t('clientSettings.unassigned', 'Not assigned')} · {rule.pattern}
                            </p>
                          ))}
                          {(libraryItem || (app && usages.length > 1)) && <p className="text-amber-600">{t('clientSettings.sharedEdit', 'Saving this document changes every rule that uses it.')}</p>}
                          {app && canCreate && (
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={busy || hasNativeDirty || Boolean(change?.template && !change.template.id)}
                              onClick={() => {
                                if (!template) return
                                const draft = copyForApplication(template, app.name)
                                setChange(changeForApplication({ ...snapshot, subscription: { ...snapshot.subscription, rules } }, app, draft, appRule?.index))
                              }}
                            >
                              <Copy className="mr-2 h-4 w-4" />
                              {t('clientSettings.copySeparate', 'Make a separate copy')}
                            </Button>
                          )}
                        </div>
                      </details>
                    )}
                    {libraryItem?.is_default && (
                      <p className="rounded-xl border border-amber-500/40 p-3 text-sm text-amber-600">
                        {t('clientSettings.defaultEdit', 'This is a global default. Changes affect subscriptions that use this default document.')}
                      </p>
                    )}
                    <div className="min-w-0 space-y-4">
                      <fieldset disabled={!editorEnabled || busy} hidden={Boolean(app && section !== 'delivery')}>
                        <label className="block space-y-1 text-sm">
                          {t('clientSettings.documentName', 'Document name')}
                          <Input maxLength={64} value={template.name} onChange={e => editTemplate({ name: e.target.value })} />
                        </label>
                        {!app && template.template_type !== 'happ_routing' && (
                          <label className="mt-3 flex items-center gap-2 text-sm">
                            <input type="checkbox" checked={template.is_default} onChange={e => editTemplate({ is_default: e.target.checked })} />
                            {t('clientSettings.useAsDefault', 'Use as the default for this format')}
                          </label>
                        )}
                      </fieldset>
                      {app && section === 'delivery' && (
                        <Link className="text-muted-foreground inline-block text-sm hover:underline" to="/client-settings/rules">
                          {t('clientSettings.applicationMatchingOrder', 'Application matching order')}
                        </Link>
                      )}
                      <fieldset disabled={busy || (section === 'delivery' && app ? !canSaveRules : !editorEnabled)} className="min-w-0">
                        {section === 'delivery' && app ? (
                          <DeliveryRuleEditor
                            applicationContext
                            lockedSource={Boolean(change?.template)}
                            templates={snapshot.templates}
                            rule={change?.rules[change.bind_rule_indices?.[0] ?? appRule?.index ?? 0] ?? appRule?.rule ?? { pattern: app.pattern, target: app.target }}
                            onChange={rule => {
                              const index = change?.bind_rule_indices?.[0] ?? appRule?.index ?? 0
                              const nextRules = [...rules]
                              if (appRule) nextRules[index] = rule
                              else nextRules.unshift({ ...rule, ui_application: app.id })
                              setChange({ ...(change ?? { expected_revision: snapshot.revision }), rules: nextRules, ...(change?.template ? { bind_rule_indices: [index] } : {}) })
                            }}
                          />
                        ) : view === 'code' || userAgentTemplate ? (
                          <CodeEditorPanel
                            value={template.content}
                            onChange={editContent}
                            language={nativeFormat === 'clash' ? 'yaml' : 'json'}
                            readOnly={!editorEnabled}
                            embeddedContainerClassName="h-[520px]"
                          />
                        ) : null}
                        {!userAgentTemplate &&
                          (['routing', 'dns'] as const).map(nativeSection => (
                            <div key={`${editorEpoch}-${template.template_type}-${nativeSection}`} hidden={view !== 'visual' || section !== nativeSection}>
                              <NativeConfigurationEditor
                                format={nativeFormat as NativeFormat}
                                content={template.content}
                                onChange={editContent}
                                section={nativeSection}
                                onValidityChange={value => setNativeValidity(previous => (previous[nativeSection] === value ? previous : { ...previous, [nativeSection]: value }))}
                                onDirtyChange={value => setNativeDirty(previous => (previous[nativeSection] === value ? previous : { ...previous, [nativeSection]: value }))}
                                onOpenCode={() => switchView('code')}
                              />
                            </div>
                          ))}
                        {sourceError && (
                          <p role="alert" className="text-destructive mt-3 text-sm">
                            {t('clientSettings.codeErrorLocation', { defaultValue: 'Invalid code at line {{line}}, column {{column}}: {{message}}', ...sourceError })}
                          </p>
                        )}
                      </fieldset>
                    </div>
                  </>
                )}
              </div>
              <WorkspacePreviewPanel
                key={app?.id ?? itemId}
                change={payload}
                userAgent={userAgent}
                draft={dirty}
                canPreview={hasPermission(admin, 'users', 'read')}
                canReadSimple={hasPermission(admin, 'users', 'read_simple')}
                ready={!hasNativeDirty && !sourceError}
              />
            </div>
          </>
        )}
      </main>
      {dirty &&
        createPortal(
          <div
            dir={i18n.dir()}
            style={actionBounds}
            className="bg-background/95 fixed bottom-0 z-20 flex flex-wrap items-center justify-between gap-3 border-t px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur sm:px-6"
          >
            <p className="text-muted-foreground text-sm">{t('clientSettings.unsaved', 'Unsaved changes')}</p>
            <div className="flex gap-2">
              <Button variant="outline" disabled={busy} onClick={cancel}>
                {t('clientSettings.cancel', 'Cancel')}
              </Button>
              <Button disabled={busy || !change || !canSave || !documentValid || Boolean(change?.template && !change.template.name.trim())} onClick={save}>
                <Save className="mr-2 h-4 w-4" />
                {busy ? t('clientSettings.saving', 'Saving…') : t('clientSettings.save', 'Save')}
              </Button>
            </div>
          </div>,
          document.body,
        )}
    </div>
  )
}

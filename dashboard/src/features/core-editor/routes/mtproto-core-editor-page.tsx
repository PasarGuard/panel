import { CodeEditorPanel } from '@/components/common/code-editor-panel'
import PageHeader from '@/components/layout/page-header'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { CoreEditorLayout } from '@/features/core-editor/components/shell/core-editor-layout'
import { carriedCoreName } from '@/features/core-editor/kit/core-kind'
import {
  applyMtprotoFields,
  emptyMtprotoWebVhost,
  isValidWebBasePath,
  mtprotoConfigIssues,
  mtprotoWebDefaults,
  readMtprotoFields,
  type MtprotoConfigIssue,
  type MtprotoFields,
  type MtprotoModes,
  type MtprotoWebFields,
  type MtprotoWebVhostFields,
} from '@/features/core-editor/kit/mtproto-config'
import useDirDetection from '@/hooks/use-dir-detection'
import { DEFAULT_MTPROTO_CORE_CONFIG_JSON } from '@/lib/default-mtproto-core-config'
import { cn } from '@/lib/utils'
import { getGetCoreConfigQueryKey, useCreateCoreConfig, useGetCoreConfig, useModifyCoreConfig } from '@/service/api'
import { queryClient } from '@/utils/query-client'
import { ArrowLeft, ExternalLink, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

type EditorSnapshot = { name: string; text: string }

const WEB_GUIDE_URL = 'https://github.com/PasarGuard/node#web-mode'

/** A whole number from a number input, `null` for an empty one, `undefined` while it is not a whole number. */
function parsePortInput(value: string): number | null | undefined {
  const raw = value.trim()
  if (raw === '') return null
  const port = Number(raw)
  return Number.isInteger(port) ? port : undefined
}

const MODE_SWITCHES: ReadonlyArray<{ key: keyof MtprotoModes; labelKey: string; defaultLabel: string }> = [
  { key: 'tls', labelKey: 'coreEditor.mtproto.modeTls', defaultLabel: 'Fake TLS (ee, recommended)' },
  { key: 'secure', labelKey: 'coreEditor.mtproto.modeSecure', defaultLabel: 'Secure (dd)' },
  { key: 'classic', labelKey: 'coreEditor.mtproto.modeClassic', defaultLabel: 'Classic' },
]

function parseConfigText(text: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(text)
    return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function formatConfig(config: unknown): string {
  return JSON.stringify(config ?? {}, null, 2)
}

/** Full-page editor for an MTProto (telemt) core. The JSON text is the source of truth; `coreId` `null` creates a core. */
export function MtprotoCoreEditorPage({ coreId }: { coreId: number | null }) {
  const dir = useDirDetection()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const [, setSearchParams] = useSearchParams()
  const isNew = coreId === null

  const { data: coreData, isLoading, isError } = useGetCoreConfig(coreId ?? 0, { query: { enabled: !isNew } })
  const createMutation = useCreateCoreConfig()
  const modifyMutation = useModifyCoreConfig()

  const serverSnapshot = useMemo<EditorSnapshot | null>(() => (!isNew && coreData ? { name: coreData.name, text: formatConfig(coreData.config) } : null), [isNew, coreData])

  const [baseline, setBaseline] = useState<EditorSnapshot | null>(() => (isNew ? { name: carriedCoreName(location.state), text: DEFAULT_MTPROTO_CORE_CONFIG_JSON } : serverSnapshot))
  const [name, setName] = useState(() => baseline?.name ?? '')
  const [text, setText] = useState(() => baseline?.text ?? '')
  const [lastValidConfig, setLastValidConfig] = useState<Record<string, unknown>>(() => (baseline ? (parseConfigText(baseline.text) ?? {}) : {}))
  const [restartNodes, setRestartNodes] = useState(true)
  const [saving, setSaving] = useState(false)
  const [discardOpen, setDiscardOpen] = useState(false)
  const [nameSubmitAttempted, setNameSubmitAttempted] = useState(false)
  /** The server snapshot last loaded into the editor (the store page's `serverHydratedConfigJson`). */
  const hydratedFromRef = useRef<EditorSnapshot | null>(serverSnapshot)

  const dirty = baseline !== null && (name !== baseline.name || text !== baseline.text)

  const updateText = useCallback((next: string) => {
    setText(next)
    const parsed = parseConfigText(next)
    if (parsed) setLastValidConfig(parsed)
  }, [])

  const loadSnapshot = useCallback(
    (snapshot: EditorSnapshot) => {
      setBaseline(snapshot)
      setName(snapshot.name)
      updateText(snapshot.text)
    },
    [updateText],
  )

  useEffect(() => {
    if (!serverSnapshot) return
    const hydratedFrom = hydratedFromRef.current
    if (hydratedFrom && hydratedFrom.name === serverSnapshot.name && hydratedFrom.text === serverSnapshot.text) return
    // A refetch replaces the editor only while it has no unsaved edits, like the store page.
    if (hydratedFrom && dirty) return
    hydratedFromRef.current = serverSnapshot
    loadSnapshot(serverSnapshot)
  }, [serverSnapshot, dirty, loadSnapshot])

  const parsedConfig = useMemo(() => parseConfigText(text), [text])
  const fields = useMemo(() => readMtprotoFields(lastValidConfig), [lastValidConfig])
  const issues = useMemo(() => new Set<MtprotoConfigIssue>(parsedConfig ? mtprotoConfigIssues(parsedConfig) : []), [parsedConfig])
  const fieldsDisabled = parsedConfig === null

  const changeFields = (patch: Partial<MtprotoFields>) => {
    if (!parsedConfig) return
    updateText(formatConfig(applyMtprotoFields(parsedConfig, { ...readMtprotoFields(parsedConfig), ...patch })))
  }

  const issueText = (issue: MtprotoConfigIssue) => t(`coreEditor.mtproto.issue.${issue}`)

  const changeTlsDomains = (tlsDomains: string[]) => changeFields({ tlsDomains })

  const changeWeb = (patch: Partial<MtprotoWebFields>) => {
    if (fields.web) changeFields({ web: { ...fields.web, ...patch } })
  }

  const changeVhost = (index: number, patch: Partial<MtprotoWebVhostFields>) => {
    if (fields.web) changeWeb({ vhosts: fields.web.vhosts.map((vhost, i) => (i === index ? { ...vhost, ...patch } : vhost)) })
  }

  const removeVhost = (index: number) => {
    if (fields.web) changeWeb({ vhosts: fields.web.vhosts.filter((_, i) => i !== index) })
  }

  const addVhost = () => {
    if (fields.web) changeWeb({ vhosts: [...fields.web.vhosts, emptyMtprotoWebVhost()] })
  }

  const handleBack = useCallback(() => {
    if (dirty) {
      setDiscardOpen(true)
      return
    }
    navigate('/nodes/cores')
  }, [dirty, navigate])

  const discardDraft = useCallback(() => {
    if (!baseline) return
    setName(baseline.name)
    updateText(baseline.text)
    setNameSubmitAttempted(false)
  }, [baseline, updateText])

  const confirmDiscardAndLeave = useCallback(() => {
    discardDraft()
    setDiscardOpen(false)
    navigate('/nodes/cores')
  }, [discardDraft, navigate])

  const switchNewCoreKind = (value: string) => {
    if (!isNew || value === 'mtproto') return
    setSearchParams(
      prev => {
        const p = new URLSearchParams(prev)
        if (value === 'wg') p.set('kind', 'wg')
        else p.delete('kind')
        return p
      },
      { replace: true, state: { coreName: name } },
    )
  }

  const handleSave = useCallback(async () => {
    const trimmedName = name.trim()
    if (!trimmedName) {
      setNameSubmitAttempted(true)
      toast.error(t('coreConfigModal.nameRequired', { defaultValue: 'Core name is required' }))
      return
    }
    setNameSubmitAttempted(false)
    const config = parseConfigText(text)
    if (!config) {
      toast.error(t('coreEditor.mtproto.invalidJson', { defaultValue: 'The config is not valid JSON.' }))
      return
    }
    const [firstIssue] = mtprotoConfigIssues(config)
    if (firstIssue) {
      toast.error(t(`coreEditor.mtproto.issue.${firstIssue}`))
      return
    }
    const data = { name: trimmedName, type: 'mtproto' as const, config, exclude_inbound_tags: [], fallbacks_inbound_tags: [] }
    setSaving(true)
    try {
      if (coreId === null) {
        const res = await createMutation.mutateAsync({ data })
        toast.success(t('coreConfigModal.createSuccess', { name: trimmedName }))
        setBaseline({ name, text })
        queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
        queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
        navigate(`/nodes/cores/${res.id}`, { replace: true })
      } else {
        await modifyMutation.mutateAsync({ coreId, data, params: { restart_nodes: restartNodes } })
        toast.success(t('coreConfigModal.editSuccess', { name: trimmedName }))
        setBaseline({ name, text })
        queryClient.invalidateQueries({ queryKey: ['/api/cores'] })
        queryClient.invalidateQueries({ queryKey: ['/api/cores/simple'] })
        queryClient.invalidateQueries({ queryKey: getGetCoreConfigQueryKey(coreId) })
      }
    } catch (e: unknown) {
      const err = e as { data?: { detail?: unknown }; response?: { _data?: { detail?: unknown }; data?: { detail?: unknown } }; message?: string }
      const detail = err?.data?.detail ?? err?.response?._data?.detail ?? err?.response?.data?.detail
      const msg = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : (err?.message ?? String(e))
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }, [name, text, coreId, restartNodes, createMutation, modifyMutation, navigate, t])

  if (!isNew && (isError || (!isLoading && !coreData))) {
    return (
      <div className="space-y-4 py-8">
        <p className="text-destructive text-sm">{t('coreEditor.loadFailed', { defaultValue: 'Could not load this core.' })}</p>
        <Button type="button" variant="outline" onClick={() => navigate('/nodes/cores')}>
          {t('coreEditor.backToList', { defaultValue: 'Back to cores' })}
        </Button>
      </div>
    )
  }

  if (!isNew && (isLoading || baseline === null)) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-4 p-4" aria-busy="true">
        <Skeleton className="h-10 w-full max-w-2xl" />
        <Skeleton className="h-64 w-full rounded-md" />
      </div>
    )
  }

  const nameRequiredMessage = t('coreConfigModal.nameRequired', { defaultValue: 'Core name is required' })
  const showNameRequired = nameSubmitAttempted && name.trim() === ''

  const header = (
    <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
      <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
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
          <div className="grid max-w-2xl grid-cols-[1fr_auto] items-center gap-2 sm:gap-3">
            <Input
              value={name}
              onChange={e => {
                const nextName = e.target.value
                setName(nextName)
                if (nextName.trim()) setNameSubmitAttempted(false)
              }}
              isError={showNameRequired}
              className="h-10 font-medium"
              placeholder={showNameRequired ? nameRequiredMessage : t('coreConfigModal.namePlaceholder', { defaultValue: 'Core name' })}
              aria-invalid={showNameRequired}
            />
            <Select value="mtproto" onValueChange={switchNewCoreKind} disabled={!isNew}>
              <SelectTrigger className="h-10 w-28 shrink-0 px-2 sm:w-[180px] sm:px-3" aria-label={t('coreConfigModal.backendType', { defaultValue: 'Backend type' })}>
                <SelectValue placeholder={t('coreConfigModal.backendType', { defaultValue: 'Type' })} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="xray">Xray</SelectItem>
                <SelectItem value="wg">WireGuard</SelectItem>
                <SelectItem value="mtproto">MTProto</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>
    </div>
  )

  const issueMessage = (issue: MtprotoConfigIssue) => (issues.has(issue) ? <p className="text-destructive text-xs">{issueText(issue)}</p> : null)

  const main = (
    <div className="space-y-6">
      {fieldsDisabled && (
        <Alert variant="destructive">
          <AlertDescription>{t('coreEditor.mtproto.invalidJson', { defaultValue: 'The config is not valid JSON.' })}</AlertDescription>
        </Alert>
      )}
      <div className="grid grid-cols-1 gap-x-4 gap-y-5 sm:grid-cols-2">
        <div className="space-y-2">
          <Label htmlFor="mtproto-inbound-tag">{t('coreEditor.mtproto.inboundTag', { defaultValue: 'Inbound tag' })}</Label>
          <Input
            id="mtproto-inbound-tag"
            dir="ltr"
            disabled={fieldsDisabled}
            value={fields.inboundTag}
            isError={issues.has('inboundTag')}
            onChange={e => changeFields({ inboundTag: e.target.value })}
          />
          <p className="text-muted-foreground text-xs">{t('coreEditor.mtproto.inboundTagHint', { defaultValue: 'Unique across all cores. Hosts and groups refer to it.' })}</p>
          {issueMessage('inboundTag')}
        </div>
        <div className="space-y-2">
          <Label htmlFor="mtproto-port">{t('coreEditor.mtproto.port', { defaultValue: 'Port' })}</Label>
          <Input
            id="mtproto-port"
            dir="ltr"
            type="number"
            inputMode="numeric"
            min={1}
            max={65535}
            placeholder="443"
            disabled={fieldsDisabled}
            value={fields.port ?? ''}
            isError={issues.has('port') || issues.has('listenerPort')}
            onChange={e => {
              const port = parsePortInput(e.target.value)
              if (port !== undefined) changeFields({ port })
            }}
          />
          {issueMessage('port')}
          {issueMessage('listenerPort')}
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="mtproto-tls-domain">{t('coreEditor.mtproto.tlsDomain', { defaultValue: 'TLS domain' })}</Label>
          <Input id="mtproto-tls-domain" dir="ltr" disabled={fieldsDisabled} value={fields.tlsDomain} isError={issues.has('tlsDomain')} onChange={e => changeFields({ tlsDomain: e.target.value })} />
          <p className="text-muted-foreground text-xs">
            {t('coreEditor.mtproto.tlsDomainHint', { defaultValue: 'The site fake TLS imitates. Changing it later breaks every ee link already shared.' })}
          </p>
          {issueMessage('tlsDomain')}
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label>{t('coreEditor.mtproto.tlsDomains', { defaultValue: 'Extra fake TLS domains' })}</Label>
          {fields.tlsDomains.map((domain, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                dir="ltr"
                disabled={fieldsDisabled}
                value={domain}
                aria-label={t('coreEditor.mtproto.tlsDomains', { defaultValue: 'Extra fake TLS domains' })}
                onChange={e => changeTlsDomains(fields.tlsDomains.map((item, i) => (i === index ? e.target.value : item)))}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="shrink-0"
                disabled={fieldsDisabled}
                aria-label={t('coreEditor.mtproto.remove', { defaultValue: 'Remove' })}
                onClick={() => changeTlsDomains(fields.tlsDomains.filter((_, i) => i !== index))}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm" disabled={fieldsDisabled} onClick={() => changeTlsDomains([...fields.tlsDomains, ''])}>
            <Plus className="h-4 w-4" />
            {t('coreEditor.mtproto.tlsDomainsAdd', { defaultValue: 'Add domain' })}
          </Button>
          <p className="text-muted-foreground text-xs">
            {t('coreEditor.mtproto.tlsDomainsHint', { defaultValue: 'Optional. More sites fake TLS clients can present, next to the TLS domain above.' })}
          </p>
          {issueMessage('tlsDomains')}
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label>{t('coreEditor.mtproto.modes', { defaultValue: 'Modes' })}</Label>
          <div className="grid gap-2 sm:grid-cols-3">
            {MODE_SWITCHES.map(mode => (
              <div key={mode.key} className="flex items-center justify-between gap-3 rounded-md border p-3">
                <Label htmlFor={`mtproto-mode-${mode.key}`} className="font-normal">
                  {t(mode.labelKey, { defaultValue: mode.defaultLabel })}
                </Label>
                <Switch
                  id={`mtproto-mode-${mode.key}`}
                  checked={fields.modes[mode.key]}
                  disabled={fieldsDisabled}
                  onCheckedChange={checked => changeFields({ modes: { ...fields.modes, [mode.key]: checked } })}
                />
              </div>
            ))}
          </div>
          {issueMessage('modes')}
        </div>
      </div>
      <div className="space-y-4 rounded-md border p-4">
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor="mtproto-web-enabled">{t('coreEditor.mtproto.webEnable', { defaultValue: 'WEB mode' })}</Label>
          <Switch
            id="mtproto-web-enabled"
            checked={fields.web !== null}
            disabled={fieldsDisabled}
            onCheckedChange={checked => {
              if (parsedConfig) changeFields({ web: checked ? mtprotoWebDefaults(parsedConfig) : null })
            }}
          />
        </div>
        <div className="text-muted-foreground space-y-1 text-xs">
          <p>
            {t('coreEditor.mtproto.webHint', {
              defaultValue: 'WEB carries MTProto over HTTPS. It needs an HTTPS front (Caddy or nginx) on the server that holds the certificate and forwards to the WEB listener.',
            })}
          </p>
          <p>{t('coreEditor.mtproto.webOneServer', { defaultValue: 'WEB settings are for one server; with several MTProto nodes, use one core per node.' })}</p>
          <a href={WEB_GUIDE_URL} target="_blank" rel="noreferrer" className="text-primary inline-flex items-center gap-1 hover:underline">
            {t('coreEditor.mtproto.webGuide', { defaultValue: 'How to set up WEB' })}
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>
        {fields.web && (
          <>
            <div className="space-y-2 sm:max-w-xs">
              <Label htmlFor="mtproto-web-port">{t('coreEditor.mtproto.webListenerPort', { defaultValue: 'WEB listener port' })}</Label>
              <Input
                id="mtproto-web-port"
                dir="ltr"
                type="number"
                inputMode="numeric"
                min={1}
                max={65535}
                disabled={fieldsDisabled}
                value={fields.web.listenerPort ?? ''}
                isError={issues.has('webListener')}
                onChange={e => {
                  const port = parsePortInput(e.target.value)
                  if (port !== undefined) changeWeb({ listenerPort: port })
                }}
              />
              <p className="text-muted-foreground text-xs">
                {t('coreEditor.mtproto.webListenerPortHint', { defaultValue: 'The local port the front forwards to. It must differ from the MTProto port.' })}
              </p>
              {issueMessage('webListener')}
            </div>
            <div className="space-y-3">
              <Label>{t('coreEditor.mtproto.webVhosts', { defaultValue: 'Domains' })}</Label>
              {fields.web.vhosts.map((vhost, index) => (
                <div key={index} className="grid grid-cols-1 gap-3 rounded-md border p-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor={`mtproto-web-host-${index}`} className="text-xs font-normal">
                      {t('coreEditor.mtproto.webHost', { defaultValue: 'Domain' })}
                    </Label>
                    <Input
                      id={`mtproto-web-host-${index}`}
                      dir="ltr"
                      placeholder="proxy.example.com"
                      disabled={fieldsDisabled}
                      value={vhost.host}
                      onChange={e => changeVhost(index, { host: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`mtproto-web-path-${index}`} className="text-xs font-normal">
                      {t('coreEditor.mtproto.webBasePath', { defaultValue: 'Path (optional)' })}
                    </Label>
                    <Input
                      id={`mtproto-web-path-${index}`}
                      dir="ltr"
                      disabled={fieldsDisabled}
                      value={vhost.basePath}
                      isError={!isValidWebBasePath(vhost.basePath)}
                      onChange={e => changeVhost(index, { basePath: e.target.value })}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`mtproto-web-public-${index}`} className="text-xs font-normal">
                      {t('coreEditor.mtproto.webPublicAddr', { defaultValue: 'Public address' })}
                    </Label>
                    <Input
                      id={`mtproto-web-public-${index}`}
                      dir="ltr"
                      placeholder="203.0.113.10:443"
                      disabled={fieldsDisabled}
                      value={vhost.publicAddr}
                      onChange={e => changeVhost(index, { publicAddr: e.target.value })}
                    />
                    <p className="text-muted-foreground text-xs">{t('coreEditor.mtproto.webPublicAddrHint', { defaultValue: "The server's public IP and port 443." })}</p>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`mtproto-web-decoy-${index}`} className="text-xs font-normal">
                      {t('coreEditor.mtproto.webDecoyUpstream', { defaultValue: 'Decoy site URL' })}
                    </Label>
                    <Input
                      id={`mtproto-web-decoy-${index}`}
                      dir="ltr"
                      placeholder="http://127.0.0.1:8080"
                      disabled={fieldsDisabled}
                      value={vhost.decoyUpstream}
                      onChange={e => changeVhost(index, { decoyUpstream: e.target.value })}
                    />
                    <p className="text-muted-foreground text-xs">
                      {t('coreEditor.mtproto.webDecoyUpstreamHint', { defaultValue: 'Other visitors see this site. Its address must be a loopback or private IP.' })}
                    </p>
                  </div>
                  <div className="flex items-end justify-between gap-2 sm:col-span-2">
                    <div className="w-full max-w-[200px] space-y-1">
                      <Label className="text-xs font-normal">{t('coreEditor.mtproto.webSecretMode', { defaultValue: 'Secret mode' })}</Label>
                      <Select value={vhost.secretMode} disabled={fieldsDisabled} onValueChange={value => changeVhost(index, { secretMode: value === 'plain' ? 'plain' : 'dd' })}>
                        <SelectTrigger aria-label={t('coreEditor.mtproto.webSecretMode', { defaultValue: 'Secret mode' })}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="dd">{t('coreEditor.mtproto.webSecretModeDd', { defaultValue: 'dd (recommended)' })}</SelectItem>
                          <SelectItem value="plain">{t('coreEditor.mtproto.webSecretModePlain', { defaultValue: 'Plain' })}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="shrink-0"
                      disabled={fieldsDisabled}
                      aria-label={t('coreEditor.mtproto.remove', { defaultValue: 'Remove' })}
                      onClick={() => removeVhost(index)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
              <Button type="button" variant="outline" size="sm" disabled={fieldsDisabled} onClick={addVhost}>
                <Plus className="h-4 w-4" />
                {t('coreEditor.mtproto.webVhostAdd', { defaultValue: 'Add domain' })}
              </Button>
              {issueMessage('webBasePath')}
              {issueMessage('webVhost')}
            </div>
          </>
        )}
      </div>
      <div className="space-y-2">
        <Label>{t('coreEditor.mtproto.config', { defaultValue: 'Config (JSON)' })}</Label>
        <CodeEditorPanel value={text} onChange={updateText} language="json" enableFullscreen />
      </div>
    </div>
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <CoreEditorLayout
        header={header}
        sectionHeader={<PageHeader title="coreEditor.section.mtproto" description="coreEditor.sectionDesc.mtproto" className="flex-wrap gap-x-3 gap-y-2 py-2.5 sm:gap-4 sm:py-4 md:pt-6" />}
        showSectionTabs={false}
        main={main}
        dirty={dirty}
        canSave={isNew || dirty}
        saveLabel={isNew ? t('create', { defaultValue: 'Create' }) : undefined}
        onSave={handleSave}
        onDiscard={discardDraft}
        onCancel={handleBack}
        saving={saving || createMutation.isPending || modifyMutation.isPending}
        showRestart={!isNew}
        restartNodes={restartNodes}
        onRestartChange={setRestartNodes}
      />
      <AlertDialog open={discardOpen} onOpenChange={setDiscardOpen}>
        <AlertDialogContent dir={dir}>
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

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { certificateItems, newCertificateItem, serializeCertificates, type TlsCertificateItem } from '@/features/core-editor/kit/tls-certificates'
import { cn } from '@/lib/utils'
import { inspectCertificate, type CertificateInspection, type CertificateInspectionRequest } from '@/service/certificates'
import { AlertTriangle, Check, ChevronDown, Copy, Eye, EyeOff, FileKey2, FolderOpen, Loader2, Plus, RefreshCw, Search, ShieldCheck, Trash2, Upload, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

interface Props {
  value: unknown
  onChange: (value: Record<string, unknown>[]) => void
  serverName?: string
}

type InspectionState = { signature: string; result?: CertificateInspection; failed?: boolean }
type Translate = (key: string, values?: Record<string, unknown>) => string
type Filter = 'all' | 'attention' | 'valid'

function requestFor(item: TlsCertificateItem, serverName: string): CertificateInspectionRequest {
  return {
    ...(item.mode === 'content' ? { certificate: item.certificate, key: item.key } : { certificate_file: item.certificateFile.trim(), key_file: item.keyFile.trim() }),
    serve_on_node: item.serveOnNode,
    server_name: serverName,
  }
}

const hasMaterial = (item: TlsCertificateItem) => Boolean(item.mode === 'content' ? item.certificate.trim() || item.key.trim() : item.certificateFile.trim() || item.keyFile.trim())
const statusVariant = (status?: string) =>
  status === 'valid' ? 'green' : status === 'expiring' || status === 'unavailable' ? 'yellow' : status === 'expired' || status === 'invalid' || status === 'not_yet_valid' ? 'red' : 'secondary'
const needsAttention = (result?: CertificateInspection) =>
  Boolean(
    result &&
    (result.status !== 'valid' ||
      result.key_status !== 'matched' ||
      result.server_name_matches === false ||
      result.chain_linked === false ||
      result.certificates[0]?.is_ca ||
      result.certificates[0]?.self_signed ||
      (result.certificates.length > 0 && result.certificates[0].domains.length === 0) ||
      result.certificates.some(cert => cert.status !== 'valid')),
  )

function Metadata({ result, failed, loading, tr, language }: { result?: CertificateInspection; failed?: boolean; loading: boolean; tr: Translate; language: string }) {
  const [copied, setCopied] = useState(false)
  const leaf = result?.certificates[0]
  const formatDate = (value: string) => new Intl.DateTimeFormat(language, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  const copyFingerprint = async () => {
    if (!leaf) return
    try {
      await navigator.clipboard.writeText(leaf.fingerprint)
      setCopied(true)
    } catch {
      toast.error(tr('copyFailed'))
    }
  }
  if (loading)
    return (
      <p role="status" className="text-muted-foreground flex items-center gap-2 text-xs">
        <Loader2 className="size-3.5 animate-spin" />
        {tr('checking')}
      </p>
    )
  if (failed)
    return (
      <p role="alert" className="text-destructive text-xs">
        {tr('requestFailed')}
      </p>
    )
  if (!result || result.status === 'empty') return <p className="text-muted-foreground text-xs">{tr('previewHint')}</p>
  if (!leaf)
    return (
      <p role="status" className="text-muted-foreground flex items-start gap-2 text-xs">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
        {tr(`errors.${result.error || 'invalid_certificate'}`)}
      </p>
    )
  const days = Math.max(0, Math.ceil((Date.parse(leaf.not_after) - Date.parse(result.checked_at)) / 86_400_000))
  return (
    <div className="space-y-3" aria-label={tr('details')}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={statusVariant(result.status)}>{tr(`status.${result.status}`)}</Badge>
        <Badge variant={result.key_status === 'matched' ? 'green' : result.key_status === 'missing' || result.key_status === 'unavailable' ? 'secondary' : 'red'}>
          {tr(`keyStatus.${result.key_status}`)}
        </Badge>
        {leaf.self_signed && <Badge variant="yellow">{tr('selfSigned')}</Badge>}
        {leaf.is_ca && <Badge variant="yellow">{tr('caCertificate')}</Badge>}
        {result.server_name_matches !== null && <Badge variant={result.server_name_matches ? 'green' : 'red'}>{tr(result.server_name_matches ? 'sniMatches' : 'sniMismatch')}</Badge>}
      </div>
      <dl className="grid min-w-0 gap-x-6 gap-y-3 text-xs sm:grid-cols-2">
        <div className="min-w-0 sm:col-span-2">
          <dt className="text-muted-foreground mb-1.5">{tr('domains')}</dt>
          <dd className="flex flex-wrap gap-1.5" dir="ltr">
            {leaf.domains.length ? (
              leaf.domains.map(domain => (
                <span key={domain} className="bg-muted rounded border px-2 py-1 font-mono break-all">
                  {domain}
                </span>
              ))
            ) : (
              <span>{tr('noSan', { name: leaf.common_name || '—' })}</span>
            )}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground mb-1">{tr('issuer')}</dt>
          <dd className="break-words">{leaf.issuer || '—'}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground mb-1">{tr('remaining')}</dt>
          <dd>{result.status === 'expired' ? tr('status.expired') : tr('daysRemaining', { count: days })}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground mb-1">{tr('notBefore')}</dt>
          <dd>
            <time dateTime={leaf.not_before}>{formatDate(leaf.not_before)}</time>
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground mb-1">{tr('notAfter')}</dt>
          <dd>
            <time dateTime={leaf.not_after}>{formatDate(leaf.not_after)}</time>
          </dd>
        </div>
      </dl>
      {result.key_error && (
        <p role="alert" className="text-destructive text-xs">
          {tr(`errors.${result.key_error}`)}
        </p>
      )}
      <details className="group rounded-md border text-xs">
        <summary className="text-muted-foreground cursor-pointer px-3 py-2">{tr('technicalDetails', { count: result.certificates.length })}</summary>
        <div className="space-y-3 border-t p-3">
          <div>
            <span className="text-muted-foreground">SHA-256</span>
            <div className="mt-1 flex items-start gap-2">
              <code className="min-w-0 flex-1 break-all" dir="ltr">
                {leaf.fingerprint}
              </code>
              <Button type="button" variant="ghost" size="icon" className="size-7 shrink-0" aria-label={tr('copyFingerprint')} onClick={copyFingerprint}>
                {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
              </Button>
            </div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <span className="text-muted-foreground">{tr('algorithm')}</span>
              <p className="mt-1 break-all" dir="ltr">
                {leaf.public_key_algorithm}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">{tr('serialNumber')}</span>
              <p className="mt-1 break-all" dir="ltr">
                {leaf.serial_number}
              </p>
            </div>
          </div>
          {result.chain_linked !== null && <p className={result.chain_linked ? 'text-muted-foreground' : 'text-destructive'}>{tr(result.chain_linked ? 'chainLinked' : 'chainBroken')}</p>}
          <ol className="space-y-2">
            {result.certificates.map((cert, index) => (
              <li key={`${cert.fingerprint}-${index}`} className="bg-muted/40 space-y-1 rounded-md p-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="min-w-0 flex-1 font-medium break-all" dir="ltr">
                    {cert.common_name || cert.subject || tr('unnamed')}
                  </span>
                  <Badge variant={statusVariant(cert.status)}>{tr(`status.${cert.status}`)}</Badge>
                </div>
                <p className="text-muted-foreground">
                  {tr('notAfter')}: {formatDate(cert.not_after)}
                </p>
              </li>
            ))}
          </ol>
        </div>
      </details>
      <p className="text-muted-foreground text-[11px] leading-relaxed">{tr('trustHint')}</p>
      <p className="text-muted-foreground text-[11px]">{tr('checkedAt', { date: formatDate(result.checked_at) })}</p>
    </div>
  )
}

export function TlsCertificatesEditor({ value, onChange, serverName = '' }: Props) {
  const { t, i18n } = useTranslation()
  const tr: Translate = (key, values) => t(`coreEditor.inbound.tlsCertificates.manager.${key}`, values ?? {})
  const [items, setItems] = useState(() => certificateItems(value))
  const lastValue = useRef(JSON.stringify(value))
  const itemsRef = useRef(items)
  itemsRef.current = items
  const [openIds, setOpenIds] = useState<Set<string>>(() => new Set(items.length === 1 ? [items[0].id] : []))
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [deleteIds, setDeleteIds] = useState<string[]>([])
  const [revealedIds, setRevealedIds] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState('configured')
  const [inspections, setInspections] = useState<Record<string, InspectionState>>({})
  const [refresh, setRefresh] = useState(0)
  const [fileError, setFileError] = useState<Record<string, string>>({})
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    const snapshot = JSON.stringify(value)
    if (snapshot === lastValue.current) return
    lastValue.current = snapshot
    // An external JSON edit or profile replacement starts a new form snapshot.
    // Ordinary edits retain UUIDs; neither indices nor PEM contents are keys.
    const next = certificateItems(value)
    itemsRef.current = next
    setItems(next)
    setOpenIds(new Set(next.length === 1 ? [next[0].id] : []))
    setSelectedIds(new Set())
    setDeleteIds([])
    setRevealedIds(new Set())
    setInspections({})
    setPinnedIds(new Set())
  }, [value])

  function commit(next: TlsCertificateItem[]) {
    itemsRef.current = next
    setItems(next)
    const serialized = serializeCertificates(next)
    lastValue.current = JSON.stringify(serialized.length ? serialized : undefined)
    onChange(serialized)
  }

  function patch(id: string, changes: Partial<TlsCertificateItem>) {
    // Keep the card being edited visible if a changed domain or status stops
    // matching its current search/filter. Choosing a new filter releases it.
    if (query || filter !== 'all') setPinnedIds(current => new Set([...current, id]))
    commit(itemsRef.current.map(item => (item.id === id ? { ...item, ...changes } : item)))
  }

  function removeCertificates(ids: string[]) {
    const removed = new Set(ids)
    commit(itemsRef.current.filter(item => !removed.has(item.id)))
    const retain = (current: Set<string>) => new Set([...current].filter(id => !removed.has(id)))
    setSelectedIds(retain)
    setOpenIds(retain)
    setRevealedIds(retain)
    setPinnedIds(retain)
    setInspections(current => Object.fromEntries(Object.entries(current).filter(([id]) => !removed.has(id))))
    setFileError(current => Object.fromEntries(Object.entries(current).filter(([key]) => !ids.some(id => key.startsWith(`${id}-`)))))
    setDeleteIds([])
  }

  const requests = useMemo(
    () =>
      items.map(item => {
        const body = requestFor(item, serverName)
        return { id: item.id, body, signature: JSON.stringify(body), enabled: hasMaterial(item) }
      }),
    [items, serverName],
  )
  const inspectionRef = useRef(inspections)
  inspectionRef.current = inspections

  function recheck(id?: string) {
    const next = Object.fromEntries(Object.entries(inspections).map(([key, state]) => [key, !id || key === id ? { ...state, signature: '' } : state]))
    inspectionRef.current = next
    setInspections(next)
    setRefresh(count => count + 1)
  }

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      const pending = requests.filter(request => request.enabled && inspectionRef.current[request.id]?.signature !== request.signature)
      let cursor = 0
      async function worker() {
        while (cursor < pending.length && !controller.signal.aborted) {
          const request = pending[cursor++]
          try {
            const result = await inspectCertificate(request.body, controller.signal)
            if (!controller.signal.aborted) setInspections(current => ({ ...current, [request.id]: { signature: request.signature, result } }))
          } catch {
            if (!controller.signal.aborted) setInspections(current => ({ ...current, [request.id]: { signature: request.signature, failed: true } }))
          }
        }
      }
      void Promise.all(Array.from({ length: Math.min(4, pending.length) }, worker))
    }, 450)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [requests, refresh])

  const byId = new Map(requests.map(request => [request.id, request]))
  function stateFor(id: string): InspectionState | undefined {
    const state = inspections[id]
    return state?.signature === byId.get(id)?.signature ? state : undefined
  }
  function titleFor(item: TlsCertificateItem) {
    const leaf = inspections[item.id]?.result?.certificates[0]
    return leaf?.domains[0] || leaf?.common_name || (item.mode === 'path' ? item.certificateFile.split(/[\\/]/).pop() : '') || tr('unnamed')
  }
  const fingerprints = new Map<string, number>()
  items.forEach(item => {
    const fingerprint = stateFor(item.id)?.result?.certificates[0]?.fingerprint
    if (fingerprint) fingerprints.set(fingerprint, (fingerprints.get(fingerprint) || 0) + 1)
  })
  const isDuplicate = (id: string) => (fingerprints.get(stateFor(id)?.result?.certificates[0]?.fingerprint || '') || 0) > 1
  const attention = (item: TlsCertificateItem) => needsAttention(stateFor(item.id)?.result) || Boolean(stateFor(item.id)?.failed) || isDuplicate(item.id)
  const healthy = (item: TlsCertificateItem) => stateFor(item.id)?.result?.status === 'valid' && !attention(item)
  const visible = items
    .filter(item => {
      const result = inspections[item.id]?.result
      const haystack = [titleFor(item), item.certificateFile, result?.certificates[0]?.issuer, ...(result?.certificates[0]?.domains || []), result?.certificates[0]?.fingerprint]
        .join(' ')
        .toLowerCase()
      return pinnedIds.has(item.id) || (haystack.includes(query.trim().toLowerCase()) && (filter === 'all' || (filter === 'attention' ? attention(item) : healthy(item))))
    })
    .sort((a, b) =>
      sort === 'domain'
        ? titleFor(a).localeCompare(titleFor(b))
        : sort === 'expiry'
          ? (Date.parse(stateFor(a.id)?.result?.certificates[0]?.not_after || '') || Infinity) - (Date.parse(stateFor(b.id)?.result?.certificates[0]?.not_after || '') || Infinity)
          : 0,
    )
  const allVisibleSelected = visible.length > 0 && visible.every(item => selectedIds.has(item.id))
  const allVisibleOpen = visible.length > 0 && visible.every(item => openIds.has(item.id))
  const toggle = (current: Set<string>, id: string) => {
    const next = new Set(current)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  }

  async function importFile(id: string, field: 'certificate' | 'key', file?: File) {
    if (!file) return
    const limit = field === 'certificate' ? 1_048_576 : 65_536
    const errorKey = `${id}-${field}`
    if (file.size > limit) {
      setFileError(current => ({ ...current, [errorKey]: tr('fileTooLarge', { size: field === 'certificate' ? '1 MB' : '64 KB' }) }))
      return
    }
    try {
      const content = await file.text()
      const marker = field === 'certificate' ? /-----BEGIN CERTIFICATE-----/ : /-----BEGIN (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----/
      if (!marker.test(content)) {
        setFileError(current => ({ ...current, [errorKey]: tr('pemOnly') }))
        return
      }
      patch(id, { mode: 'content', [field]: content })
      setFileError(current => ({ ...current, [errorKey]: '' }))
    } catch {
      setFileError(current => ({ ...current, [errorKey]: tr('fileReadFailed') }))
    }
  }

  return (
    <section className="min-w-0 space-y-3 sm:col-span-2" aria-label={tr('title')}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <ShieldCheck className="size-4 text-sky-500" />
          <h4 className="text-sm font-semibold">{tr('title')}</h4>
          <Badge variant="secondary" className="tabular-nums">
            {items.length}
          </Badge>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" variant="ghost" size="sm" disabled={!items.length} onClick={() => recheck()}>
            <RefreshCw className="me-1.5 size-3.5" />
            {tr('refresh')}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              const item = newCertificateItem()
              commit([...itemsRef.current, item])
              setQuery('')
              setFilter('all')
              setOpenIds(current => new Set([...current, item.id]))
            }}
          >
            <Plus className="me-1.5 size-4" />
            {tr('add')}
          </Button>
        </div>
      </div>
      {items.length > 0 && (
        <>
          <div className="bg-muted/30 flex flex-wrap gap-1 rounded-lg border p-1" aria-label={tr('filter')}>
            {(['all', 'attention', 'valid'] as const).map(kind => (
              <Button
                type="button"
                key={kind}
                size="sm"
                variant={filter === kind ? 'secondary' : 'ghost'}
                className="h-8 gap-2 text-xs"
                aria-pressed={filter === kind}
                onClick={() => {
                  setPinnedIds(new Set())
                  setFilter(kind)
                }}
              >
                {tr(`filters.${kind}`)}
                <span className="text-muted-foreground tabular-nums">{kind === 'all' ? items.length : items.filter(kind === 'attention' ? attention : healthy).length}</span>
              </Button>
            ))}
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <div className="relative min-w-0 flex-1">
              <Search className="text-muted-foreground pointer-events-none absolute start-3 top-3 size-3.5" />
              <Input
                aria-label={tr('search')}
                placeholder={tr('search')}
                className="ps-9 text-xs"
                value={query}
                onChange={event => {
                  setPinnedIds(new Set())
                  setQuery(event.target.value)
                }}
              />
            </div>
            <Select
              value={sort}
              onValueChange={value => {
                setPinnedIds(new Set())
                setSort(value)
              }}
            >
              <SelectTrigger className="h-9 w-full text-xs sm:w-44" aria-label={tr('sort')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="configured">{tr('sortConfigured')}</SelectItem>
                <SelectItem value="expiry">{tr('sortExpiry')}</SelectItem>
                <SelectItem value="domain">{tr('sortDomain')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <div className="flex items-center gap-2">
              <Checkbox
                id="tls-cert-select-visible"
                checked={allVisibleSelected ? true : visible.some(item => selectedIds.has(item.id)) ? 'indeterminate' : false}
                onCheckedChange={() =>
                  setSelectedIds(current => {
                    const next = new Set(current)
                    visible.forEach(item => {
                      if (allVisibleSelected) next.delete(item.id)
                      else next.add(item.id)
                    })
                    return next
                  })
                }
              />
              <Label htmlFor="tls-cert-select-visible" className="text-muted-foreground text-xs">
                {tr('selectVisible', { count: visible.length })}
              </Label>
            </div>
            <div className="flex items-center gap-1">
              {selectedIds.size > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-destructive h-7 text-xs"
                  onClick={() => setDeleteIds(items.filter(item => selectedIds.has(item.id)).map(item => item.id))}
                >
                  <Trash2 className="me-1 size-3.5" />
                  {tr('deleteSelected', { count: selectedIds.size })}
                </Button>
              )}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="text-muted-foreground h-7 text-xs"
                onClick={() =>
                  setOpenIds(current => {
                    const next = new Set(current)
                    visible.forEach(item => {
                      if (allVisibleOpen) next.delete(item.id)
                      else next.add(item.id)
                    })
                    return next
                  })
                }
              >
                {tr(allVisibleOpen ? 'collapseAll' : 'expandAll')}
              </Button>
            </div>
          </div>
        </>
      )}
      {items.length === 0 ? (
        <div className="text-muted-foreground flex flex-col items-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center text-xs">
          <FileKey2 className="size-7 opacity-50" />
          <p>{tr('empty')}</p>
        </div>
      ) : visible.length === 0 ? (
        <div className="text-muted-foreground rounded-lg border border-dashed p-6 text-center text-xs">
          <p>{tr('noResults')}</p>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="mt-2"
            onClick={() => {
              setQuery('')
              setFilter('all')
            }}
          >
            <X className="me-1 size-3.5" />
            {tr('clearFilters')}
          </Button>
        </div>
      ) : (
        <div className="space-y-2">
          {visible.map(item => {
            const state = stateFor(item.id)
            const result = state?.result
            const leaf = result?.certificates[0]
            const open = openIds.has(item.id)
            const loading = hasMaterial(item) && !state
            const title = titleFor(item)
            const fieldId = (field: string) => `tls-${item.id}-${field}`
            return (
              <article
                key={item.id}
                className={cn(
                  'min-w-0 overflow-hidden rounded-lg border border-s-2',
                  attention(item) ? 'border-s-amber-500/80' : result?.status === 'valid' ? 'border-s-emerald-500/80' : 'border-s-border',
                )}
              >
                <div className={cn('flex items-start gap-2 px-3 py-3', open && 'bg-muted/25')}>
                  <Checkbox
                    className="mt-1"
                    checked={selectedIds.has(item.id)}
                    aria-label={tr('selectCertificate', { name: title })}
                    onCheckedChange={() => setSelectedIds(current => toggle(current, item.id))}
                  />
                  <button
                    type="button"
                    className="focus-visible:ring-ring flex min-w-0 flex-1 items-start gap-2 rounded text-start focus-visible:ring-2 focus-visible:outline-none"
                    aria-expanded={open}
                    aria-controls={fieldId('body')}
                    onClick={() => setOpenIds(current => toggle(current, item.id))}
                  >
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex min-w-0 items-center gap-2">
                        <span className="text-muted-foreground font-mono text-[10px] tabular-nums">{String(items.indexOf(item) + 1).padStart(2, '0')}</span>
                        <span dir="ltr" className="min-w-0 truncate text-sm font-medium" title={title}>
                          {title}
                        </span>
                        {loading && <Loader2 className="text-muted-foreground size-3.5 shrink-0 animate-spin" />}
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant={statusVariant(state?.failed ? 'invalid' : result?.status)}>
                          {tr(state?.failed ? 'checkFailed' : loading ? 'checking' : `status.${result?.status || 'empty'}`)}
                        </Badge>
                        {item.serveOnNode && <Badge variant="outline">{tr('nodeLocal')}</Badge>}
                        {isDuplicate(item.id) && <Badge variant="yellow">{tr('duplicate')}</Badge>}
                        {leaf?.self_signed && <Badge variant="yellow">{tr('selfSigned')}</Badge>}
                        {(result?.chain_linked === false || result?.certificates.slice(1).some(cert => cert.status !== 'valid')) && <Badge variant="yellow">{tr('chainAttention')}</Badge>}
                        {result?.key_status && result.key_status !== 'matched' && (
                          <Badge variant={result.key_status === 'mismatch' || result.key_status === 'invalid' ? 'red' : 'secondary'}>{tr(`keyStatus.${result.key_status}`)}</Badge>
                        )}
                        {result?.server_name_matches === false && <Badge variant="red">{tr('sniMismatch')}</Badge>}
                        {leaf && (
                          <span className="text-muted-foreground text-[11px]">
                            {tr('expiresOn', { date: new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }).format(new Date(leaf.not_after)) })}
                          </span>
                        )}
                      </div>
                    </div>
                    <ChevronDown className={cn('text-muted-foreground mt-0.5 size-4 shrink-0 transition-transform', open && 'rotate-180')} />
                  </button>
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="text-destructive -mt-1 size-8 shrink-0"
                    aria-label={tr('deleteCertificate', { name: title })}
                    onClick={() => {
                      if (!hasMaterial(item)) removeCertificates([item.id])
                      else setDeleteIds([item.id])
                    }}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
                {open && (
                  <div id={fieldId('body')} className="space-y-4 border-t p-3 sm:p-4">
                    <div className="bg-muted/20 space-y-2 rounded-md border p-3">
                      <div className="flex justify-end">
                        <Button type="button" size="sm" variant="ghost" className="h-7 text-xs" disabled={!hasMaterial(item) || loading} onClick={() => recheck(item.id)}>
                          <RefreshCw className="me-1 size-3" />
                          {tr('recheckOne')}
                        </Button>
                      </div>
                      <Metadata result={result} failed={state?.failed} loading={loading} tr={tr} language={i18n.language} />
                    </div>
                    <Tabs value={item.mode} onValueChange={mode => patch(item.id, { mode: mode === 'content' ? 'content' : 'path' })}>
                      <TabsList className="grid w-full grid-cols-2">
                        <TabsTrigger value="path" className="gap-1.5">
                          <FolderOpen className="size-3.5" />
                          {tr('filePath')}
                        </TabsTrigger>
                        <TabsTrigger value="content" className="gap-1.5">
                          <FileKey2 className="size-3.5" />
                          {tr('fileContent')}
                        </TabsTrigger>
                      </TabsList>
                    </Tabs>
                    <div className="flex items-start gap-2 rounded-md border border-dashed p-3">
                      <Checkbox id={fieldId('node')} checked={item.serveOnNode} onCheckedChange={checked => patch(item.id, { serveOnNode: checked === true })} />
                      <div className="space-y-1">
                        <Label htmlFor={fieldId('node')} className="text-xs">
                          {tr('serveOnNode')}
                        </Label>
                        <p className="text-muted-foreground text-[11px] leading-relaxed">{tr('serveOnNodeHint')}</p>
                      </div>
                    </div>
                    {item.mode === 'path' ? (
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div className="space-y-1.5">
                          <Label htmlFor={fieldId('certificateFile')} className="text-xs">
                            {tr('certificateFile')}
                          </Label>
                          <Input
                            id={fieldId('certificateFile')}
                            className="font-mono text-xs"
                            placeholder="/etc/letsencrypt/live/example.com/fullchain.pem"
                            value={item.certificateFile}
                            maxLength={4096}
                            onChange={event => patch(item.id, { certificateFile: event.target.value })}
                          />
                        </div>
                        <div className="space-y-1.5">
                          <Label htmlFor={fieldId('keyFile')} className="text-xs">
                            {tr('keyFile')}
                          </Label>
                          <Input
                            id={fieldId('keyFile')}
                            className="font-mono text-xs"
                            placeholder="/etc/letsencrypt/live/example.com/privkey.pem"
                            value={item.keyFile}
                            maxLength={4096}
                            onChange={event => patch(item.id, { keyFile: event.target.value })}
                          />
                        </div>
                        <p className="text-muted-foreground text-[11px] sm:col-span-2">{tr('pathHint')}</p>
                      </div>
                    ) : (
                      <div className="grid min-w-0 gap-3 sm:grid-cols-2">
                        {(['certificate', 'key'] as const).map(field => (
                          <div key={field} className="min-w-0 space-y-1.5">
                            <div className="flex min-h-7 items-center justify-between gap-1">
                              <Label htmlFor={fieldId(field)} className="text-xs">
                                {tr(field === 'certificate' ? 'certificateContent' : 'keyContent')}
                              </Label>
                              <div className="flex items-center gap-1">
                                {field === 'key' && (
                                  <Button
                                    type="button"
                                    size="icon"
                                    variant="ghost"
                                    className="size-7"
                                    aria-label={tr(revealedIds.has(item.id) ? 'hideKey' : 'showKey')}
                                    onClick={() => setRevealedIds(current => toggle(current, item.id))}
                                  >
                                    {revealedIds.has(item.id) ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
                                  </Button>
                                )}
                                <Label
                                  htmlFor={fieldId(`${field}-upload`)}
                                  className="focus-within:ring-ring hover:bg-accent inline-flex cursor-pointer items-center gap-1 rounded-md px-2 py-1 text-[11px] focus-within:ring-2"
                                >
                                  <Upload className="size-3" />
                                  {tr('importFile')}
                                  <input
                                    id={fieldId(`${field}-upload`)}
                                    className="sr-only"
                                    type="file"
                                    accept=".pem,.crt,.cer,.key,text/plain,application/x-pem-file"
                                    onChange={event => {
                                      void importFile(item.id, field, event.target.files?.[0])
                                      event.target.value = ''
                                    }}
                                  />
                                </Label>
                              </div>
                            </div>
                            {field === 'key' && !revealedIds.has(item.id) && item.key ? (
                              <div className="bg-muted/30 flex min-h-[136px] flex-col items-center justify-center gap-2 rounded-lg border px-3 py-4 text-center text-xs">
                                <ShieldCheck className="text-muted-foreground size-5" />
                                <span className="text-muted-foreground">{tr('keyHidden')}</span>
                                <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={() => setRevealedIds(current => new Set([...current, item.id]))}>
                                  {tr('showKey')}
                                </Button>
                              </div>
                            ) : (
                              <Textarea
                                id={fieldId(field)}
                                dir="ltr"
                                rows={6}
                                spellCheck={false}
                                autoComplete="off"
                                className="min-h-[136px] font-mono text-[11px]"
                                placeholder={field === 'certificate' ? '-----BEGIN CERTIFICATE-----' : '-----BEGIN PRIVATE KEY-----'}
                                value={item[field]}
                                maxLength={field === 'certificate' ? 1_048_576 : 65_536}
                                onChange={event => {
                                  if (field === 'key') setRevealedIds(current => new Set([...current, item.id]))
                                  patch(item.id, { [field]: event.target.value })
                                }}
                              />
                            )}
                            {fileError[`${item.id}-${field}`] && (
                              <p role="alert" className="text-destructive text-xs">
                                {fileError[`${item.id}-${field}`]}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="max-w-sm space-y-1.5">
                      <Label htmlFor={fieldId('ocsp')} className="text-xs">
                        {tr('ocsp')}
                      </Label>
                      <Input
                        id={fieldId('ocsp')}
                        type="number"
                        min={0}
                        step={1}
                        className="text-xs"
                        placeholder="3600"
                        value={item.ocspStapling}
                        onChange={event => {
                          const raw = event.target.value
                          if (raw === '' || (/^\d+$/.test(raw) && Number.isSafeInteger(Number(raw)))) patch(item.id, { ocspStapling: raw })
                        }}
                      />
                    </div>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}
      <AlertDialog
        open={deleteIds.length > 0}
        onOpenChange={open => {
          if (!open) setDeleteIds([])
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{tr('deleteTitle', { count: deleteIds.length })}</AlertDialogTitle>
            <AlertDialogDescription>{tr('deleteHint')}</AlertDialogDescription>
          </AlertDialogHeader>
          <ul className="max-h-48 space-y-1 overflow-auto text-sm">
            {items
              .filter(item => deleteIds.includes(item.id))
              .map(item => (
                <li key={item.id} className="truncate font-mono" dir="ltr">
                  {titleFor(item)}
                </li>
              ))}
          </ul>
          <AlertDialogFooter>
            <AlertDialogCancel>{tr('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                removeCertificates(deleteIds)
              }}
            >
              {tr('confirmDelete', { count: deleteIds.length })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}

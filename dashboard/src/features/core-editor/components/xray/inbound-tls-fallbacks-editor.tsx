import type { Fallback } from '@pasarguard/xray-config-kit'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { ListTree, Plus, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

export type TlsFallbackEditorRow = {
  id: string
  name: string
  alpn: string
  path: string
  dest: string
  xver: 0 | 1 | 2
}

function newRow(): TlsFallbackEditorRow {
  return {
    id: globalThis.crypto?.randomUUID?.() ?? `r-${Math.random().toString(36).slice(2)}`,
    name: '',
    alpn: '',
    path: '',
    dest: '',
    xver: 0,
  }
}

export function fallbacksToEditorRows(fallbacks: readonly Fallback[] | undefined): TlsFallbackEditorRow[] {
  if (!fallbacks?.length) return [newRow()]
  return fallbacks.map((fb, i) => ({
    id: `fb-${i}-${String(fb.dest)}`,
    name: fb.name ?? '',
    alpn: fb.alpn ?? '',
    path: fb.path ?? '',
    dest: typeof fb.dest === 'number' ? String(fb.dest) : String(fb.dest ?? ''),
    xver: fb.xver === 1 || fb.xver === 2 ? fb.xver : 0,
  }))
}

export function editorRowsToFallbacks(rows: TlsFallbackEditorRow[]): Fallback[] | undefined {
  const out: Fallback[] = []
  for (const r of rows) {
    const d = r.dest.trim()
    if (d === '') continue
    const dest: string | number = /^\d+$/.test(d) ? Number(d) : d
    out.push({
      dest,
      ...(r.name.trim() ? { name: r.name.trim() } : {}),
      ...(r.alpn.trim() ? { alpn: r.alpn.trim() } : {}),
      ...(r.path.trim() ? { path: r.path.trim() } : {}),
      ...(r.xver === 1 || r.xver === 2 ? { xver: r.xver } : {}),
    })
  }
  return out.length > 0 ? out : undefined
}

/** Same chrome as DNS rules / Freedom sub-accordions in outbound settings. */
const TLS_FALLBACKS_ACCORDION_ITEM_CLASS =
  'rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline'

export interface InboundTlsFallbacksEditorProps {
  className?: string
  fallbacks: Fallback[] | undefined
  onPersist: (next: Fallback[] | undefined) => void
}

export function InboundTlsFallbacksEditor({
  className,
  fallbacks,
  onPersist,
}: InboundTlsFallbacksEditorProps) {
  const { t } = useTranslation()
  const fbKey = useMemo(() => JSON.stringify(fallbacks ?? null), [fallbacks])
  const [rows, setRows] = useState<TlsFallbackEditorRow[]>(() => fallbacksToEditorRows(fallbacks))
  const rowsRef = useRef(rows)
  rowsRef.current = rows

  useEffect(() => {
    setRows(fallbacksToEditorRows(fallbacks))
  }, [fbKey])

  const commit = (next: TlsFallbackEditorRow[]) => {
    setRows(next)
    onPersist(editorRowsToFallbacks(next))
  }

  const updateRow = (id: string, patch: Partial<Omit<TlsFallbackEditorRow, 'id'>>) => {
    const next = rowsRef.current.map(r => (r.id === id ? { ...r, ...patch } : r))
    commit(next)
  }

  const addRow = () => commit([...rowsRef.current, newRow()])

  const removeRow = (id: string) => {
    const filtered = rowsRef.current.filter(r => r.id !== id)
    commit(filtered.length > 0 ? filtered : [newRow()])
  }

  return (
    <Accordion type="single" collapsible className={cn('w-full min-w-0', className)}>
      <AccordionItem value="tls-fallbacks" className={TLS_FALLBACKS_ACCORDION_ITEM_CLASS}>
        <AccordionTrigger>
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <ListTree className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
            <span className="truncate text-left">
              {t('coreEditor.inbound.tlsFallbacks.title', { defaultValue: 'TLS fallbacks' })}
            </span>
          </div>
        </AccordionTrigger>
        <AccordionContent className="space-y-4 px-2 pb-4">
          <p className="text-xs leading-relaxed text-muted-foreground">
            {t('coreEditor.inbound.tlsFallbacks.hint', {
              defaultValue:
                'For VLESS or Trojan with TCP and TLS. Xray matches SNI, ALPN, and path on the first bytes after TLS, then forwards to dest (port, host:port, or UDS path). Rows without dest are ignored.',
            })}
          </p>

          <div className="space-y-4">
            {rows.map((row, idx) => (
              <div key={row.id} className="rounded-lg border border-border bg-muted/15 p-4 shadow-sm">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground">
                    {t('coreEditor.inbound.tlsFallbacks.rowLabel', {
                      index: idx + 1,
                      defaultValue: 'Rule {{index}}',
                    })}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                    title={t('coreEditor.inbound.tlsFallbacks.remove', { defaultValue: 'Remove rule' })}
                    aria-label={t('coreEditor.inbound.tlsFallbacks.remove', { defaultValue: 'Remove rule' })}
                    onClick={() => removeRow(row.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="flex min-w-0 flex-col gap-1.5">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.inbound.tlsFallbacks.name', { defaultValue: 'SNI (name)' })}
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 w-full min-w-0 text-xs"
                      value={row.name}
                      onChange={e => updateRow(row.id, { name: e.target.value })}
                      placeholder="cdn.example.com"
                    />
                  </div>
                  <div className="flex min-w-0 flex-col gap-1.5">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.inbound.tlsFallbacks.alpn', { defaultValue: 'ALPN' })}
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 w-full min-w-0 text-xs"
                      value={row.alpn}
                      onChange={e => updateRow(row.id, { alpn: e.target.value })}
                      placeholder="http/1.1"
                    />
                  </div>
                  <div className="flex min-w-0 w-full flex-col gap-1.5 sm:col-span-2">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.inbound.tlsFallbacks.path', { defaultValue: 'Path' })}
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 w-full min-w-0 text-xs"
                      value={row.path}
                      onChange={e => updateRow(row.id, { path: e.target.value })}
                      placeholder="/ws"
                    />
                  </div>
                  <div className="flex min-w-0 w-full flex-col gap-1.5 sm:col-span-2">
                    <Label className="text-xs font-medium text-muted-foreground">
                      {t('coreEditor.inbound.tlsFallbacks.dest', { defaultValue: 'Destination (dest)' })}{' '}
                      <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      dir="ltr"
                      className="h-10 w-full min-w-0 text-xs"
                      value={row.dest}
                      onChange={e => updateRow(row.id, { dest: e.target.value })}
                      placeholder="80 · 127.0.0.1:8080 · /path/to.sock"
                    />
                  </div>
                  <div className="flex min-w-0 w-full flex-col gap-1.5 sm:col-span-2">
                    <Label className="text-xs font-medium text-muted-foreground">
                      PROXY protocol (xver)
                    </Label>
                    <Select
                      value={String(row.xver)}
                      onValueChange={v => updateRow(row.id, { xver: Number(v) as 0 | 1 | 2 })}
                    >
                      <SelectTrigger className="h-10 w-full min-w-0">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="0">{t('coreEditor.inbound.tlsFallbacks.xver0', { defaultValue: 'Off (0)' })}</SelectItem>
                        <SelectItem value="1">v1</SelectItem>
                        <SelectItem value="2">v2</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <Button type="button" variant="secondary" size="sm" className="w-full gap-1.5" onClick={addRow}>
            <Plus className="h-4 w-4" />
            {t('coreEditor.inbound.tlsFallbacks.addRow', { defaultValue: 'Add fallback rule' })}
          </Button>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}

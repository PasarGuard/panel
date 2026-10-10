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

export type FallbackEditorRow = {
  id: string
  name: string
  alpn: string
  path: string
  dest: string
  xver: 0 | 1 | 2
}

function newRow(): FallbackEditorRow {
  return {
    id: globalThis.crypto?.randomUUID?.() ?? `r-${Math.random().toString(36).slice(2)}`,
    name: '',
    alpn: '',
    path: '',
    dest: '',
    xver: 0,
  }
}

function fallbackPathIsInvalid(path: string): boolean {
  const trimmed = path.trim()
  return trimmed !== '' && !trimmed.startsWith('/')
}

export function fallbacksToEditorRows(fallbacks: readonly Fallback[] | undefined): FallbackEditorRow[] {
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

export function editorRowsToFallbacks(rows: FallbackEditorRow[]): Fallback[] | undefined {
  const out: Fallback[] = []
  for (const r of rows) {
    const d = r.dest.trim()
    if (d === '') continue
    const dest: string | number = /^\d+$/.test(d) ? Number(d) : d
    out.push({
      dest,
      ...(r.name.trim() ? { name: r.name.trim() } : {}),
      ...(r.alpn.trim() ? { alpn: r.alpn.trim() } : {}),
      ...(r.path.trim() && !fallbackPathIsInvalid(r.path) ? { path: r.path.trim() } : {}),
      ...(r.xver === 1 || r.xver === 2 ? { xver: r.xver } : {}),
    })
  }
  return out.length > 0 ? out : undefined
}

/** Same chrome as DNS rules / Freedom sub-accordions in outbound settings. */
const FALLBACKS_ACCORDION_ITEM_CLASS = 'rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline'

export interface InboundFallbacksEditorProps {
  className?: string
  fallbacks: Fallback[] | undefined
  onPersist: (next: Fallback[] | undefined) => void
}

export function InboundFallbacksEditor({ className, fallbacks, onPersist }: InboundFallbacksEditorProps) {
  const { t } = useTranslation()
  const fbKey = useMemo(() => JSON.stringify(fallbacks ?? null), [fallbacks])
  const [rows, setRows] = useState<FallbackEditorRow[]>(() => fallbacksToEditorRows(fallbacks))
  const rowsRef = useRef(rows)
  rowsRef.current = rows

  useEffect(() => {
    setRows(fallbacksToEditorRows(fallbacks))
  }, [fbKey])

  const commit = (next: FallbackEditorRow[]) => {
    setRows(next)
    onPersist(editorRowsToFallbacks(next))
  }

  const updateRow = (id: string, patch: Partial<Omit<FallbackEditorRow, 'id'>>) => {
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
      <AccordionItem value="fallbacks" className={FALLBACKS_ACCORDION_ITEM_CLASS}>
        <AccordionTrigger>
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <ListTree className="text-muted-foreground h-4 w-4 shrink-0" aria-hidden />
            <span className="truncate text-left">{t('coreEditor.inbound.fallbacks.title', { defaultValue: 'Fallbacks' })}</span>
          </div>
        </AccordionTrigger>
        <AccordionContent className="space-y-4 px-2 pb-4">
          <p className="text-muted-foreground text-xs leading-relaxed">
            {t('coreEditor.inbound.fallbacks.hint', {
              defaultValue:
                'For VLESS or Trojan TCP inbounds. Xray forwards matching traffic to dest (port, host:port, or UDS path). SNI and ALPN only apply when TLS is enabled. Rows without dest are ignored.',
            })}
          </p>

          <div className="space-y-4">
            {rows.map((row, idx) => {
              const pathInvalid = fallbackPathIsInvalid(row.path)
              return (
                <div key={row.id} className="border-border bg-muted/15 rounded-lg border p-4 shadow-sm">
                  <div className="mb-3 flex items-center justify-between gap-2">
                    <span className="text-muted-foreground text-xs font-medium">
                      {t('coreEditor.inbound.fallbacks.rowLabel', {
                        index: idx + 1,
                        defaultValue: 'Rule {{index}}',
                      })}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="text-muted-foreground hover:text-destructive h-8 w-8 shrink-0"
                      title={t('coreEditor.inbound.fallbacks.remove', { defaultValue: 'Remove rule' })}
                      aria-label={t('coreEditor.inbound.fallbacks.remove', { defaultValue: 'Remove rule' })}
                      onClick={() => removeRow(row.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="flex min-w-0 flex-col gap-1.5">
                      <Label className="text-muted-foreground text-xs font-medium">{t('coreEditor.inbound.fallbacks.name', { defaultValue: 'SNI (name)' })}</Label>
                      <Input dir="ltr" className="h-10 w-full min-w-0 text-xs" value={row.name} onChange={e => updateRow(row.id, { name: e.target.value })} placeholder="cdn.example.com" />
                    </div>
                    <div className="flex min-w-0 flex-col gap-1.5">
                      <Label className="text-muted-foreground text-xs font-medium">{t('coreEditor.inbound.fallbacks.alpn', { defaultValue: 'ALPN' })}</Label>
                      <Input dir="ltr" className="h-10 w-full min-w-0 text-xs" value={row.alpn} onChange={e => updateRow(row.id, { alpn: e.target.value })} placeholder="http/1.1" />
                    </div>
                    <div className="flex w-full min-w-0 flex-col gap-1.5 sm:col-span-2">
                      <Label className="text-muted-foreground text-xs font-medium">{t('coreEditor.inbound.fallbacks.path', { defaultValue: 'Path' })}</Label>
                      <Input
                        dir="ltr"
                        className="h-10 w-full min-w-0 text-xs"
                        value={row.path}
                        onChange={e => updateRow(row.id, { path: e.target.value })}
                        placeholder="/ws"
                        aria-invalid={pathInvalid}
                      />
                      {pathInvalid && (
                        <p className="text-destructive text-[11px] leading-relaxed">{t('coreEditor.inbound.fallbacks.pathMustStartSlash', { defaultValue: 'Path must start with /.' })}</p>
                      )}
                    </div>
                    <div className="flex w-full min-w-0 flex-col gap-1.5 sm:col-span-2">
                      <Label className="text-muted-foreground text-xs font-medium">
                        {t('coreEditor.inbound.fallbacks.dest', { defaultValue: 'Destination (dest)' })} <span className="text-destructive">*</span>
                      </Label>
                      <Input
                        dir="ltr"
                        className="h-10 w-full min-w-0 text-xs"
                        value={row.dest}
                        onChange={e => updateRow(row.id, { dest: e.target.value })}
                        placeholder="80, 127.0.0.1:8080, /path/to.sock"
                      />
                    </div>
                    <div className="flex w-full min-w-0 flex-col gap-1.5 sm:col-span-2">
                      <Label className="text-muted-foreground text-xs font-medium">PROXY protocol (xver)</Label>
                      <Select value={String(row.xver)} onValueChange={v => updateRow(row.id, { xver: Number(v) as 0 | 1 | 2 })}>
                        <SelectTrigger className="h-10 w-full min-w-0">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="0">{t('coreEditor.inbound.fallbacks.xver0', { defaultValue: 'Off (0)' })}</SelectItem>
                          <SelectItem value="1">v1</SelectItem>
                          <SelectItem value="2">v2</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <Button type="button" variant="secondary" size="sm" className="w-full gap-1.5" onClick={addRow}>
            <Plus className="h-4 w-4" />
            {t('coreEditor.inbound.fallbacks.addRow', { defaultValue: 'Add fallback rule' })}
          </Button>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}

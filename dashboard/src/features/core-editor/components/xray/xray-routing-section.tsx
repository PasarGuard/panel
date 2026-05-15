import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Button } from '@/components/ui/button'
import { Form, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { XrayParityFormControl, isBooleanParityField, transportParityFieldLabel, type XrayProfileTagOptions } from '@/features/core-editor/components/shared/xray-parity-form-control'
import { CoreEditorDataTable } from '@/features/core-editor/components/shared/core-editor-data-table'
import { CoreEditorFormDialog } from '@/features/core-editor/components/shared/core-editor-form-dialog'
import { useSectionHeaderAddPulseEffect, type SectionHeaderAddPulse } from '@/features/core-editor/hooks/use-section-header-add-pulse'
import { useXrayPersistModifyGuard } from '@/features/core-editor/hooks/use-xray-persist-modify-guard'
import { profileDuplicateTagMessage, profileTagHasDuplicateUsage } from '@/features/core-editor/kit/profile-tag-uniqueness'
import { remapIndexAfterArrayMove } from '@/features/core-editor/kit/remap-index-after-move'
import {
  collectRoutingRuleDialogFormErrors,
  collectRoutingRuleDialogIssues,
  routingRuleDialogHasBlockingErrors,
} from '@/features/core-editor/kit/routing-rule-dialog-validation'
import { inferParityFieldMode, parseRoutingRuleFieldValue, routingRuleFieldToString } from '@/features/core-editor/kit/xray-parity-value'
import { ValidationSummary } from '@/features/core-editor/components/shared/validation-summary'
import { useCoreEditorStore } from '@/features/core-editor/state/core-editor-store'
import { createDefaultRoutingRule, getRoutingRuleFormCapabilities } from '@pasarguard/xray-config-kit'
import type { Issue, Profile, Routing, RoutingRule, XrayGeneratedFormField } from '@pasarguard/xray-config-kit'
import type { ColumnDef } from '@tanstack/react-table'
import useDirDetection from '@/hooks/use-dir-detection'
import { arrayMove } from '@dnd-kit/sortable'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { ArrowRightFromLine, Filter, Info, Pencil, Plus, Settings2, Tag } from 'lucide-react'

// ─── Routing helpers ─────────────────────────────────────────────────────────

function defaultRouting(): Routing {
  return { domainStrategy: 'AsIs', rules: [] }
}

function replaceRule(profile: Profile, index: number, rule: RoutingRule): Profile {
  const routing = profile.routing ?? defaultRouting()
  const rules = [...routing.rules]
  rules[index] = rule
  return { ...profile, routing: { ...routing, rules } }
}

function removeRule(profile: Profile, index: number): Profile {
  const routing = profile.routing ?? defaultRouting()
  return { ...profile, routing: { ...routing, rules: routing.rules.filter((_, i) => i !== index) } }
}

function routingRuleAsRecord(r: RoutingRule): Record<string, unknown> {
  return r as unknown as Record<string, unknown>
}

function routingRuleDomainSummary(r: RoutingRule): string {
  const o = routingRuleAsRecord(r)
  const domains = o.domains
  if (Array.isArray(domains) && domains.length > 0) {
    const parts = domains.map(d => String(d))
    return parts.length > 2 ? `${parts.slice(0, 2).join(', ')} (+${parts.length - 2})` : parts.join(', ')
  }
  const domain = o.domain
  if (domain !== undefined && domain !== null && String(domain).trim() !== '') {
    return String(domain)
  }
  return ''
}

function routingRulePortLabel(r: RoutingRule): string {
  const o = routingRuleAsRecord(r)
  const port = o.port ?? o.sourcePort
  if (port === undefined || port === null) return ''
  if (typeof port === 'object') {
    try {
      return JSON.stringify(port)
    } catch {
      return String(port)
    }
  }
  return String(port)
}

function routingRuleSearchHaystack(r: RoutingRule): string {
  const o = routingRuleAsRecord(r)
  const parts: string[] = [
    String(o.outboundTag ?? ''),
    String(o.balancerTag ?? ''),
    String(o.inboundTag ?? ''),
    String(o.sourceTag ?? ''),
    String(o.network ?? ''),
    String(o.protocol ?? ''),
    String(o.user ?? ''),
    String(o.ip ?? ''),
    routingRulePortLabel(r),
    String(o.source ?? ''),
    String(o.attrs ?? ''),
  ]
  if (Array.isArray(o.domains)) {
    parts.push(...(o.domains as unknown[]).map(String))
  }
  if (o.domain !== undefined && o.domain !== null) parts.push(String(o.domain))
  for (const k of ['geosite', 'geoip', 'processName', 'domainMatcher'] as const) {
    const v = o[k]
    if (v !== undefined && v !== null) parts.push(String(v))
  }
  try {
    parts.push(JSON.stringify(r))
  } catch {
    parts.push(String(r))
  }
  return parts.join(' ')
}

// ─── Field section definitions ───────────────────────────────────────────────

/** Keys that are internal / not user-facing. */
const SKIP_ROUTING_KEYS = new Set(['type'])

const ROUTING_SECTIONS = [
  {
    id: 'routing-action',
    label: 'Routing Action',
    icon: ArrowRightFromLine,
    keys: ['outboundTag', 'balancerTag'],
  },
  {
    id: 'match-conditions',
    label: 'Match Conditions',
    icon: Filter,
    keys: [
      'inboundTag',
      'domain',
      'domains',
      'ip',
      'port',
      'sourcePort',
      'sourceIP',
      'source',
      'localIP',
      'localPort',
      'network',
      'protocol',
      'user',
      'vlessRoute',
      'process',
    ],
  },
  {
    id: 'advanced',
    label: 'Advanced',
    icon: Settings2,
    keys: ['attrs', 'webhook'],
  },
  {
    id: 'identification',
    label: 'Identification',
    icon: Tag,
    keys: ['ruleTag'],
  },
] as const

type RoutingSectionId = (typeof ROUTING_SECTIONS)[number]['id']

/**
 * Groups fieldOrder keys into sections.
 * Keys not found in any section list are appended to 'match-conditions'.
 * Returns only sections that have at least one field.
 */
/** Ensures outbound/balancer tags appear in the form even if parity field order omits them. */
function mergeCriticalRoutingKeys(
  order: readonly string[],
  defs: Record<string, XrayGeneratedFormField>,
): string[] {
  const critical = ['outboundTag', 'balancerTag'] as const
  const next = [...order]
  const missing = critical.filter(k => defs[k] != null && !next.includes(k))
  return missing.length === 0 ? next : [...missing, ...next]
}

function buildSectionedFields(fieldOrder: readonly string[]): Map<RoutingSectionId, string[]> {
  const keyToSection = new Map<string, RoutingSectionId>()
  for (const section of ROUTING_SECTIONS) {
    for (const key of section.keys) {
      keyToSection.set(key, section.id)
    }
  }

  const result = new Map<RoutingSectionId, string[]>(
    ROUTING_SECTIONS.map(s => [s.id, []]),
  )

  for (const key of fieldOrder) {
    if (SKIP_ROUTING_KEYS.has(key)) continue
    const sectionId = keyToSection.get(key)
    if (sectionId) {
      result.get(sectionId)!.push(key)
    } else {
      result.get('match-conditions')!.push(key)
    }
  }

  const matchKeys = result.get('match-conditions')!
  if (matchKeys.includes('inboundTag')) {
    result.set(
      'match-conditions',
      ['inboundTag', ...matchKeys.filter(k => k !== 'inboundTag')],
    )
  }

  return result
}

// ─── Types ────────────────────────────────────────────────────────────────────

type DialogMode = 'add' | 'edit'

interface XrayRoutingSectionProps {
  headerAddPulse?: SectionHeaderAddPulse
  headerAddEpoch?: number
}

// ─── Component ───────────────────────────────────────────────────────────────

export function XrayRoutingSection({ headerAddPulse, headerAddEpoch }: XrayRoutingSectionProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const profile = useCoreEditorStore(s => s.xrayProfile)
  const updateXrayProfile = useCoreEditorStore(s => s.updateXrayProfile)
  const { assertNoPersistBlockingErrors } = useXrayPersistModifyGuard()
  const [selected, setSelected] = useState(0)
  const [detailOpen, setDetailOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>('edit')
  const [draftRule, setDraftRule] = useState<RoutingRule | null>(null)
  const [discardDraftOpen, setDiscardDraftOpen] = useState(false)
  const [blockAddWhileDraftOpen, setBlockAddWhileDraftOpen] = useState(false)
  const [ruleDialogIssues, setRuleDialogIssues] = useState<Issue[]>([])
  const routing = profile?.routing ?? defaultRouting()
  const rules = routing.rules

  const rule = useMemo(() => {
    if (dialogMode === 'add' && draftRule) return draftRule
    return rules[selected]
  }, [dialogMode, draftRule, rules, selected])

  const routingCaps = useMemo(() => {
    const caps = getRoutingRuleFormCapabilities(profile ? { profile } : undefined)
    const sorted = [...caps.fieldOrder].sort((a, b) => {
      const defA = caps.fieldDefinitions[a]
      const defB = caps.fieldDefinitions[b]
      const isBoolA = defA ? isBooleanParityField(defA) : false
      const isBoolB = defB ? isBooleanParityField(defB) : false
      if (isBoolA && !isBoolB) return 1
      if (!isBoolA && isBoolB) return -1
      return 0
    })
    const fieldOrder = mergeCriticalRoutingKeys(sorted, caps.fieldDefinitions)
    return { ...caps, fieldOrder }
  }, [profile])

  const profileTagOptions = useMemo<XrayProfileTagOptions>(
    () => ({
      outboundTags: routingCaps.outboundTags,
      inboundTags: routingCaps.inboundTags,
      balancerTags: routingCaps.balancerTags,
    }),
    [routingCaps],
  )

  const sectionedFields = useMemo(
    () => buildSectionedFields(routingCaps.fieldOrder),
    [routingCaps.fieldOrder],
  )

  const defaultOpenAccordion = useMemo(() => {
    if ((sectionedFields.get('routing-action') ?? []).length > 0) return 'routing-action'
    if ((sectionedFields.get('match-conditions') ?? []).length > 0) return 'match-conditions'
    if ((sectionedFields.get('advanced') ?? []).length > 0) return 'advanced'
    return 'identification'
  }, [sectionedFields])

  const form = useForm<Record<string, string>>({})

  const profileRef = useRef(profile)
  profileRef.current = profile

  const routingCapsRef = useRef(routingCaps)
  routingCapsRef.current = routingCaps

  useEffect(() => {
    if (!detailOpen) return
    setRuleDialogIssues([])
    form.clearErrors('tag')
    const p = profileRef.current
    if (!p) return
    const r = dialogMode === 'add' && draftRule ? draftRule : p.routing?.rules?.[selected]
    if (!r) return
    const caps = routingCapsRef.current
    const next: Record<string, string> = {}
    for (const key of caps.fieldOrder) {
      const def = caps.fieldDefinitions[key]
      if (!def) continue
      next[key] = routingRuleFieldToString(r, key, def)
    }
    form.reset(next)
  }, [detailOpen, selected, dialogMode, draftRule, form])

  const beginAddRule = useCallback(() => {
    if (!profile) return
    if (detailOpen && dialogMode === 'add' && draftRule !== null) {
      setBlockAddWhileDraftOpen(true)
      return
    }
    const nextRule = createDefaultRoutingRule({})
    setDraftRule(nextRule)
    setDialogMode('add')
    setDetailOpen(true)
  }, [profile, detailOpen, dialogMode, draftRule])

  useSectionHeaderAddPulseEffect(headerAddPulse, headerAddEpoch, 'routing', beginAddRule)

  const columns = useMemo<ColumnDef<RoutingRule, unknown>[]>(
    () => [
      {
        id: 'index',
        header: '#',
        cell: ({ row }) => row.index + 1,
      },
      {
        id: 'inbound',
        header: () => t('coreEditor.routing.inbound', { defaultValue: 'Inbound' }),
        cell: ({ row }) => {
          const tag = routingRuleAsRecord(row.original).inboundTag
          return <span className="text-xs">{tag != null && String(tag) !== '' ? String(tag) : '—'}</span>
        },
      },
      {
        id: 'outbound',
        header: () => t('coreEditor.routing.outbound', { defaultValue: 'Outbound' }),
        cell: ({ row }) => <span className="text-xs">{row.original.outboundTag ?? '—'}</span>,
      },
      {
        id: 'balancer',
        header: () => t('coreEditor.routing.balancer', { defaultValue: 'Balancer' }),
        cell: ({ row }) => <span className="text-xs">{row.original.balancerTag ?? '—'}</span>,
      },
      {
        id: 'domain',
        header: () => t('coreEditor.routing.domain', { defaultValue: 'Domain / rule' }),
        cell: ({ row }) => {
          const summary = routingRuleDomainSummary(row.original)
          return (
            <span className="line-clamp-2 min-w-0 max-w-56 text-xs" title={summary || undefined}>
              {summary || '—'}
            </span>
          )
        },
      },
      {
        id: 'port',
        header: () => t('coreEditor.routing.port', { defaultValue: 'Port' }),
        cell: ({ row }) => {
          const label = routingRulePortLabel(row.original)
          return <span className="text-xs">{label || '—'}</span>
        },
      },
    ],
    [t],
  )

  if (!profile) return null

  const finalizeDetailClose = () => {
    setDetailOpen(false)
    setDialogMode('edit')
    setDraftRule(null)
  }

  const handleDetailOpenChange = (open: boolean) => {
    if (open) {
      setDetailOpen(true)
      return
    }
    if (dialogMode === 'add' && draftRule !== null) {
      setDiscardDraftOpen(true)
      return
    }
    finalizeDetailClose()
  }

  const validateRoutingRuleForm = () => {
    const errors = collectRoutingRuleDialogFormErrors(form.getValues(), t)
    form.clearErrors()
    if (errors.length === 0) return true
    for (const error of errors) {
      form.setError(error.name, { type: 'validate', message: error.message })
    }
    return false
  }

  const commitAddRule = () => {
    if (!draftRule) return
    if (!validateRoutingRuleForm()) return
    const ruleTagTrim = String(routingRuleAsRecord(draftRule).tag ?? '').trim()
    if (ruleTagTrim && profile && profileTagHasDuplicateUsage(profile, ruleTagTrim)) {
      form.setError('tag', { type: 'validate', message: profileDuplicateTagMessage(t, ruleTagTrim) })
      return
    }
    if (!assertNoPersistBlockingErrors()) return
    const issues = collectRoutingRuleDialogIssues(draftRule, {
      outboundTags: routingCaps.outboundTags,
      balancerTags: routingCaps.balancerTags,
      t,
    })
    if (routingRuleDialogHasBlockingErrors(issues)) {
      setRuleDialogIssues(issues)
      return
    }
    setRuleDialogIssues([])
    updateXrayProfile(p => {
      const r = p.routing ?? defaultRouting()
      return { ...p, routing: { ...r, rules: [...r.rules, draftRule] } }
    })
    setSelected(rules.length)
    finalizeDetailClose()
  }

  const commitEditRule = () => {
    if (dialogMode !== 'edit' || !rule) return
    if (!validateRoutingRuleForm()) return
    const ruleTagTrim = String(routingRuleAsRecord(rule).tag ?? '').trim()
    if (ruleTagTrim && profile && profileTagHasDuplicateUsage(profile, ruleTagTrim, { owner: 'routingRule', index: selected })) {
      form.setError('tag', { type: 'validate', message: profileDuplicateTagMessage(t, ruleTagTrim) })
      return
    }
    const issues = collectRoutingRuleDialogIssues(rule, {
      outboundTags: routingCaps.outboundTags,
      balancerTags: routingCaps.balancerTags,
      t,
    })
    if (routingRuleDialogHasBlockingErrors(issues)) {
      setRuleDialogIssues(issues)
      return
    }
    setRuleDialogIssues([])
    finalizeDetailClose()
  }

  const patchRule = (patch: Partial<RoutingRule>) => {
    setRuleDialogIssues([])
    if (dialogMode === 'add' && draftRule !== null) {
      setDraftRule({ ...draftRule, ...patch })
      return
    }
    if (!rule) return
    updateXrayProfile(p => replaceRule(p, selected, { ...rule, ...patch }))
  }

  /** Render a single parity field wrapped in FormField + FormItem. */
  const renderField = (jsonKey: string, colSpan?: 'full') => {
    const def = routingCaps.fieldDefinitions[jsonKey]
    if (!def) return null
    const mode = inferParityFieldMode(def)
    const isJsonMode = mode === 'json'
    return (
      <FormField
        key={jsonKey}
        control={form.control}
        name={jsonKey}
        render={({ field }) => (
          <FormItem
            className={cn(
              'min-w-0',
              (isJsonMode || colSpan === 'full') && 'sm:col-span-2',
            )}
          >
            <FormLabel className="text-xs font-medium">
              {transportParityFieldLabel(def, t)}
            </FormLabel>
            <XrayParityFormControl
              field={def}
              value={field.value ?? ''}
              profileTagOptions={profileTagOptions}
              onChange={v => {
                field.onChange(v)
                try {
                  const { value, clearDomains, clearDomain } = parseRoutingRuleFieldValue(jsonKey, def, v)
                  const patch: Record<string, unknown> = { [jsonKey]: value }
                  if (clearDomains) patch.domains = undefined
                  if (clearDomain) patch.domain = undefined
                  patchRule(patch as Partial<RoutingRule>)
                  if (jsonKey === 'tag') {
                    const nextTag = String(value ?? '').trim()
                    const snap = useCoreEditorStore.getState().xrayProfile
                    if (
                      nextTag &&
                      snap &&
                      profileTagHasDuplicateUsage(
                        snap,
                        nextTag,
                        dialogMode === 'edit' ? { owner: 'routingRule', index: selected } : undefined,
                      )
                    ) {
                      form.setError('tag', { type: 'validate', message: profileDuplicateTagMessage(t, nextTag) })
                    } else {
                      form.clearErrors('tag')
                    }
                  }
                } catch {
                  /* invalid JSON — do not patch until parse succeeds */
                }
              }}
            />
            <FormMessage />
          </FormItem>
        )}
      />
    )
  }

  return (
    <div className="space-y-6">
      <CoreEditorDataTable
        columns={columns}
        data={rules}
        getSearchableText={routingRuleSearchHaystack}
        searchPlaceholder={t('coreEditor.routing.searchPlaceholder', {
          defaultValue: 'Search by tags, domain, port, network…',
        })}
        bulkDeleteTitle={t('coreEditor.routing.bulkDeleteTitle', {
          defaultValue: 'Remove selected routing rules',
        })}
        emptyLabel={t('coreEditor.routing.emptyRules', { defaultValue: 'No routing rules' })}
        getRowId={(_, i) => String(i)}
        onRowClick={(_row, rowIndex) => {
          if (detailOpen && dialogMode === 'add' && draftRule !== null) {
            setBlockAddWhileDraftOpen(true)
            return
          }
          setDraftRule(null)
          setDialogMode('edit')
          setSelected(rowIndex)
          setDetailOpen(true)
        }}
        onRemoveRow={i => {
          updateXrayProfile(p => removeRule(p, i))
          setSelected(0)
        }}
        onBulkRemove={indices => {
          const rm = new Set(indices)
          updateXrayProfile(p => ({
            ...p,
            routing: {
              ...(p.routing ?? defaultRouting()),
              rules: (p.routing ?? defaultRouting()).rules.filter((_, idx) => !rm.has(idx)),
            },
          }))
          setSelected(0)
        }}
        enableReorder
        onReorder={(from, to) => {
          updateXrayProfile(p => {
            const r = p.routing ?? defaultRouting()
            return { ...p, routing: { ...r, rules: arrayMove(r.rules, from, to) } }
          })
          setSelected(sel => remapIndexAfterArrayMove(sel, from, to))
        }}
      />

      <CoreEditorFormDialog
        isDialogOpen={detailOpen}
        onOpenChange={handleDetailOpenChange}
        leadingIcon={dialogMode === 'add' ? <Plus className="h-5 w-5 shrink-0" /> : <Pencil className="h-5 w-5 shrink-0" />}
        title={
          dialogMode === 'add'
            ? t('coreEditor.routing.dialogTitleAdd', { defaultValue: 'Add routing rule' })
            : t('coreEditor.routing.dialogTitleEdit', { defaultValue: 'Edit routing rule' })
        }
        size="lg"
        footerExtra={
          dialogMode === 'add' && draftRule ? (
            <Button type="button" className="sm:min-w-[88px]" onClick={commitAddRule}>
              {t('coreEditor.routing.addToList', { defaultValue: 'Add to list' })}
            </Button>
          ) : dialogMode === 'edit' && rule ? (
            <Button type="button" className="sm:min-w-[88px]" onClick={commitEditRule}>
              {t('modify')}
            </Button>
          ) : undefined
        }
      >
        {rule && (
          <Form {...form}>
            <form className="pb-2" onSubmit={e => e.preventDefault()}>
              {ruleDialogIssues.length > 0 ? (
                <ValidationSummary
                  className="mb-4"
                  items={ruleDialogIssues.map(issue => ({ source: 'xray' as const, issue }))}
                />
              ) : null}
              <Accordion
                type="single"
                collapsible
                defaultValue={defaultOpenAccordion}
                className="!mt-0 flex w-full flex-col gap-y-4"
              >
                {/* ── Section 1: Routing Action ───────────────────────────── */}
                {(() => {
                  const sectionKeys = sectionedFields.get('routing-action') ?? []
                  if (sectionKeys.length === 0) return null
                  return (
                    <AccordionItem
                      value="routing-action"
                      className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline"
                    >
                      <AccordionTrigger>
                        <div className="flex items-center gap-2">
                          <ArrowRightFromLine className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <span>{t('coreEditor.routing.sectionRoutingAction', { defaultValue: 'Routing Action' })}</span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-2 pb-4">
                        <div className="mb-4 flex items-start gap-2 rounded-md border bg-muted/30 px-3 py-2.5 text-xs text-muted-foreground">
                          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-foreground/70" />
                          <span>
                            {t('coreEditor.routing.routingActionHint', {
                              defaultValue:
                                'Choose one target for matched traffic. When both are set, outboundTag takes precedence over balancerTag.',
                            })}
                          </span>
                        </div>
                        <div className="grid gap-4 sm:grid-cols-2">
                          {sectionKeys.map(k => renderField(k))}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  )
                })()}

                {/* ── Section 2: Match Conditions ─────────────────────────── */}
                {(() => {
                  const sectionKeys = sectionedFields.get('match-conditions') ?? []
                  if (sectionKeys.length === 0) return null
                  return (
                    <AccordionItem
                      value="match-conditions"
                      className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline"
                    >
                      <AccordionTrigger>
                        <div className="flex items-center gap-2">
                          <Filter className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <span>{t('coreEditor.routing.sectionMatchConditions', { defaultValue: 'Match Conditions' })}</span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-2 pb-4">
                        <div className="mb-3 text-xs text-muted-foreground">
                          {t('coreEditor.routing.matchConditionsHint', {
                            defaultValue: 'All specified conditions must be satisfied for this rule to apply.',
                          })}
                        </div>
                        <div className="grid gap-4 sm:grid-cols-2">
                          {sectionKeys.map((k, idx) => {
                            // Force the trailing field of an odd-count grid to span both columns.
                            const isLastSolo = idx === sectionKeys.length - 1 && sectionKeys.length % 2 === 1
                            return renderField(k, isLastSolo ? 'full' : undefined)
                          })}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  )
                })()}

                {/* ── Section 3: Advanced ─────────────────────────────────── */}
                {(() => {
                  const sectionKeys = sectionedFields.get('advanced') ?? []
                  if (sectionKeys.length === 0) return null
                  return (
                    <AccordionItem
                      value="advanced"
                      className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline"
                    >
                      <AccordionTrigger>
                        <div className="flex items-center gap-2">
                          <Settings2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <span>{t('coreEditor.routing.sectionAdvanced', { defaultValue: 'Advanced' })}</span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-2 pb-4">
                        <div className="grid gap-4">
                          {sectionKeys.map(k => renderField(k, 'full'))}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  )
                })()}

                {/* ── Section 4: Identification ───────────────────────────── */}
                {(() => {
                  const sectionKeys = sectionedFields.get('identification') ?? []
                  if (sectionKeys.length === 0) return null
                  return (
                    <AccordionItem
                      value="identification"
                      className="rounded-sm border px-4 [&_[data-state=closed]]:no-underline [&_[data-state=open]]:no-underline"
                    >
                      <AccordionTrigger>
                        <div className="flex items-center gap-2">
                          <Tag className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <span>{t('coreEditor.routing.sectionIdentification', { defaultValue: 'Identification' })}</span>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent className="px-2 pb-4">
                        <div className="mb-3 text-xs text-muted-foreground">
                          {t('coreEditor.routing.identificationHint', {
                            defaultValue: 'Optional label for debugging. When set, matched rules are logged at Info level.',
                          })}
                        </div>
                        <div className="grid gap-4 sm:grid-cols-2">
                          {sectionKeys.map(k => renderField(k, 'full'))}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  )
                })()}
              </Accordion>
            </form>
          </Form>
        )}
      </CoreEditorFormDialog>

      <AlertDialog open={discardDraftOpen} onOpenChange={setDiscardDraftOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('coreEditor.routing.discardDraftTitle', { defaultValue: 'Discard new rule?' })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.routing.discardDraftDescription', {
                defaultValue: 'This rule is not in the list yet. Closing without adding will discard your changes.',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setDiscardDraftOpen(false)
                finalizeDetailClose()
              }}
            >
              {t('coreEditor.routing.discardDraftAction', { defaultValue: 'Discard' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={blockAddWhileDraftOpen} onOpenChange={setBlockAddWhileDraftOpen}>
        <AlertDialogContent dir={dir}>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('coreEditor.routing.finishCurrentTitle', { defaultValue: 'Finish the current rule first' })}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('coreEditor.routing.finishCurrentDescription', {
                defaultValue:
                  'Add it to the list, or close the dialog and discard the draft, before starting another rule.',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction type="button" className="sm:min-w-[88px]" onClick={() => setBlockAddWhileDraftOpen(false)}>
              {t('close', { defaultValue: 'Close' })}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

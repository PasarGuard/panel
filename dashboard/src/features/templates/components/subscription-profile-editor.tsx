import { CodeEditorPanel } from '@/components/common/code-editor-panel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { parseSubscriptionProfileForEditing, serializeSubscriptionProfile, type SubscriptionProfileFormValue } from '@/features/templates/forms/subscription-profile-form'
import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface SubscriptionProfileEditorProps {
  value: string
  onChange: (value: string) => void
  onValidate: (markers: unknown[]) => void
  dialogOpen: boolean
  onFullscreenChange: (fullscreen: boolean) => void
}

function RoutingRuleEditor({
  value,
  onChange,
  onDraftValidityChange,
}: {
  value: Record<string, unknown>
  onChange: (value: Record<string, unknown>) => void
  onDraftValidityChange: (isValid: boolean) => void
}) {
  const [draft, setDraft] = useState(() => JSON.stringify(value, null, 2))
  const serializedValue = JSON.stringify(value, null, 2)

  useEffect(() => {
    setDraft(serializedValue)
  }, [serializedValue])

  return (
    <Textarea
      className="min-h-24 font-mono text-xs"
      value={draft}
      onChange={event => {
        const nextDraft = event.target.value
        setDraft(nextDraft)
        try {
          const nextRule = JSON.parse(nextDraft)
          if (nextRule && !Array.isArray(nextRule) && typeof nextRule === 'object') {
            onChange(nextRule)
            onDraftValidityChange(true)
          } else {
            onDraftValidityChange(false)
          }
        } catch {
          onDraftValidityChange(false)
        }
      }}
    />
  )
}

export function SubscriptionProfileEditor({ value, onChange, onValidate, dialogOpen, onFullscreenChange }: SubscriptionProfileEditorProps) {
  const { t } = useTranslation()
  const [tab, setTab] = useState('structured')
  const invalidRuleDrafts = useRef(new Set<number>())
  const parsed = parseSubscriptionProfileForEditing(value)

  useEffect(() => {
    if (!dialogOpen) invalidRuleDrafts.current.clear()
  }, [dialogOpen])

  const reportRuleDraftValidation = () => {
    onValidate(invalidRuleDrafts.current.size ? [{ message: t('clientTemplates.profile.invalidRuleJson', { defaultValue: 'Routing rule must be a valid JSON object.' }) }] : [])
  }

  const handleRuleDraftValidity = (index: number, isValid: boolean) => {
    if (isValid) invalidRuleDrafts.current.delete(index)
    else invalidRuleDrafts.current.add(index)
    reportRuleDraftValidation()
  }

  const updateProfile = (updater: (profile: SubscriptionProfileFormValue) => SubscriptionProfileFormValue) => {
    if (!parsed.success) return
    onChange(serializeSubscriptionProfile(updater(parsed.data)))
    reportRuleDraftValidation()
  }

  return (
    <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-[450px] flex-col">
      <TabsList className="grid w-full grid-cols-2">
        <TabsTrigger value="structured">{t('clientTemplates.profile.structured', { defaultValue: 'Structured' })}</TabsTrigger>
        <TabsTrigger value="raw">{t('clientTemplates.profile.rawJson', { defaultValue: 'Raw JSON' })}</TabsTrigger>
      </TabsList>

      <TabsContent value="structured" className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
        {!parsed.success ? (
          <div className="border-destructive/40 bg-destructive/5 rounded-lg border p-4 text-sm">
            <p className="text-destructive font-medium">{t('clientTemplates.profile.cannotOpenStructured', { defaultValue: 'This profile cannot be opened in the structured editor.' })}</p>
            <p className="text-muted-foreground mt-1 break-words">{parsed.error}</p>
            <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => setTab('raw')}>
              {t('clientTemplates.profile.openRawJson', { defaultValue: 'Open Raw JSON' })}
            </Button>
          </div>
        ) : (
          <div className="space-y-5 pb-2">
            <section className="space-y-3 rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-sm font-medium">{t('clientTemplates.profile.pools', { defaultValue: 'Pools' })}</h3>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const used = new Set(parsed.data.pools.map(pool => pool.id))
                    let suffix = parsed.data.pools.length + 1
                    while (used.has(`pool-${suffix}`)) suffix += 1
                    updateProfile(profile => ({ ...profile, pools: [...profile.pools, { id: `pool-${suffix}`, enabled: true }] }))
                  }}
                >
                  <Plus className="mr-1 h-4 w-4" />
                  {t('clientTemplates.profile.addPool', { defaultValue: 'Add pool' })}
                </Button>
              </div>

              <label className="grid gap-1.5 text-sm">
                <span>{t('clientTemplates.profile.defaultPool', { defaultValue: 'Default pool' })}</span>
                <Select value={parsed.data.default_pool} onValueChange={default_pool => updateProfile(profile => ({ ...profile, default_pool }))}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {parsed.data.pools
                      .filter(pool => pool.enabled)
                      .map(pool => (
                        <SelectItem key={pool.id} value={pool.id}>
                          {pool.id}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </label>

              <div className="space-y-3">
                {parsed.data.pools.map((pool, index) => (
                  <div key={`${pool.id}-${index}`} className="grid gap-3 rounded-md border p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
                    <label className="grid gap-1.5 text-sm">
                      <span>{t('clientTemplates.profile.poolName', { defaultValue: 'Pool name' })}</span>
                      <Input
                        value={pool.id}
                        onChange={event => {
                          const id = event.target.value.toLowerCase()
                          updateProfile(profile => {
                            const oldId = profile.pools[index].id
                            return {
                              ...profile,
                              default_pool: profile.default_pool === oldId ? id : profile.default_pool,
                              pools: profile.pools.map((entry, entryIndex) => ({
                                ...entry,
                                id: entryIndex === index ? id : entry.id,
                                fallback_pool: entry.fallback_pool === oldId ? id : entry.fallback_pool,
                              })),
                            }
                          })
                        }}
                      />
                    </label>
                    <label className="grid gap-1.5 text-sm">
                      <span>{t('clientTemplates.profile.fallbackPool', { defaultValue: 'Fallback pool' })}</span>
                      <Select
                        value={pool.fallback_pool ?? 'none'}
                        onValueChange={fallback =>
                          updateProfile(profile => ({
                            ...profile,
                            pools: profile.pools.map((entry, entryIndex) => (entryIndex === index ? { ...entry, fallback_pool: fallback === 'none' ? null : fallback } : entry)),
                          }))
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">{t('clientTemplates.profile.noFallback', { defaultValue: 'No fallback' })}</SelectItem>
                          {parsed.data.pools
                            .filter(candidate => candidate.id !== pool.id && candidate.enabled)
                            .map(candidate => (
                              <SelectItem key={candidate.id} value={candidate.id}>
                                {candidate.id}
                              </SelectItem>
                            ))}
                        </SelectContent>
                      </Select>
                    </label>
                    <div className="flex items-end gap-2">
                      <label className="flex h-10 items-center gap-2 text-sm">
                        <Switch
                          checked={pool.enabled}
                          disabled={pool.id === parsed.data.default_pool}
                          onCheckedChange={enabled =>
                            updateProfile(profile => ({ ...profile, pools: profile.pools.map((entry, entryIndex) => (entryIndex === index ? { ...entry, enabled } : entry)) }))
                          }
                        />
                        {t('clientTemplates.profile.enabled', { defaultValue: 'Enabled' })}
                      </label>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        disabled={parsed.data.pools.length === 1}
                        onClick={() =>
                          updateProfile(profile => {
                            const remainingPools = profile.pools.filter((_, entryIndex) => entryIndex !== index)
                            const nextDefaultPool = profile.default_pool === pool.id ? (remainingPools.find(entry => entry.enabled)?.id ?? remainingPools[0].id) : profile.default_pool
                            return {
                              ...profile,
                              default_pool: nextDefaultPool,
                              pools: remainingPools.map(entry => ({ ...entry, fallback_pool: entry.fallback_pool === pool.id ? null : entry.fallback_pool })),
                            }
                          })
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                        <span className="sr-only">{t('clientTemplates.profile.removePool', { defaultValue: 'Remove pool' })}</span>
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="space-y-3 rounded-lg border p-3">
              <h3 className="text-sm font-medium">{t('clientTemplates.profile.healthCheck', { defaultValue: 'Health check' })}</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1.5 text-sm sm:col-span-2">
                  <span>{t('clientTemplates.profile.healthUrl', { defaultValue: 'Probe URL' })}</span>
                  <Input value={parsed.data.health_check.url} onChange={event => updateProfile(profile => ({ ...profile, health_check: { ...profile.health_check, url: event.target.value } }))} />
                </label>
                {(['interval', 'tolerance', 'timeout'] as const).map(field => (
                  <label key={field} className="grid gap-1.5 text-sm">
                    <span>{t(`clientTemplates.profile.${field}`, { defaultValue: field[0].toUpperCase() + field.slice(1) })}</span>
                    <Input
                      type={field === 'tolerance' ? 'number' : 'text'}
                      min={field === 'tolerance' ? 0 : undefined}
                      max={field === 'tolerance' ? 65535 : undefined}
                      value={parsed.data.health_check[field]}
                      onChange={event =>
                        updateProfile(profile => ({ ...profile, health_check: { ...profile.health_check, [field]: field === 'tolerance' ? Number(event.target.value) : event.target.value } }))
                      }
                    />
                  </label>
                ))}
              </div>
            </section>

            <section className="space-y-3 rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-medium">{t('clientTemplates.profile.routingRules', { defaultValue: 'Routing rules' })}</h3>
                  <p className="text-muted-foreground text-xs">{t('clientTemplates.profile.routingRulesHelp', { defaultValue: 'Each item is one client-native routing rule.' })}</p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => updateProfile(profile => ({ ...profile, routing_rules: [...profile.routing_rules, {}] }))}>
                  <Plus className="mr-1 h-4 w-4" />
                  {t('clientTemplates.profile.addRule', { defaultValue: 'Add rule' })}
                </Button>
              </div>
              {parsed.data.routing_rules.map((rule, index) => (
                <div key={index} className="flex items-start gap-2">
                  <RoutingRuleEditor
                    value={rule}
                    onChange={nextRule => updateProfile(profile => ({ ...profile, routing_rules: profile.routing_rules.map((entry, entryIndex) => (entryIndex === index ? nextRule : entry)) }))}
                    onDraftValidityChange={isValid => handleRuleDraftValidity(index, isValid)}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t('clientTemplates.profile.removeRule', { defaultValue: 'Remove routing rule' })}
                    onClick={() => {
                      invalidRuleDrafts.current = new Set(
                        [...invalidRuleDrafts.current].flatMap(invalidIndex => (invalidIndex === index ? [] : [invalidIndex > index ? invalidIndex - 1 : invalidIndex])),
                      )
                      updateProfile(profile => ({ ...profile, routing_rules: profile.routing_rules.filter((_, entryIndex) => entryIndex !== index) }))
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                    <span className="sr-only">{t('clientTemplates.profile.removeRule', { defaultValue: 'Remove routing rule' })}</span>
                  </Button>
                </div>
              ))}
            </section>

            <section className="space-y-3 rounded-lg border p-3">
              <h3 className="text-sm font-medium">{t('clientTemplates.profile.clientOptions', { defaultValue: 'Client options' })}</h3>
              <label className="grid gap-1.5 text-sm">
                <span>{t('clientTemplates.profile.client', { defaultValue: 'Client' })}</span>
                <Select
                  value={parsed.data.client}
                  onValueChange={client =>
                    updateProfile(profile => ({
                      ...profile,
                      client: client as SubscriptionProfileFormValue['client'],
                      happ_deeplink: client === 'happ' ? profile.happ_deeplink : null,
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {['generic', 'happ', 'incy', 'v2rayn'].map(client => (
                      <SelectItem key={client} value={client}>
                        {client}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              {parsed.data.client === 'happ' && (
                <label className="grid gap-1.5 text-sm">
                  <span>{t('clientTemplates.profile.happDeeplink', { defaultValue: 'Happ deeplink (optional)' })}</span>
                  <Input value={parsed.data.happ_deeplink ?? ''} onChange={event => updateProfile(profile => ({ ...profile, happ_deeplink: event.target.value || null }))} placeholder="happ://..." />
                </label>
              )}
            </section>
          </div>
        )}
      </TabsContent>

      <TabsContent value="raw" className="mt-3 min-h-0 flex-1">
        <CodeEditorPanel
          value={value}
          language="json"
          onChange={nextValue => {
            invalidRuleDrafts.current.clear()
            onChange(nextValue)
          }}
          onValidate={onValidate}
          enableFullscreen
          dialogOpen={dialogOpen}
          onFullscreenChange={onFullscreenChange}
          embeddedContainerClassName="h-[calc(50vh-1rem)] sm:h-[calc(55vh-1rem)] md:min-h-[450px]"
        />
      </TabsContent>
    </Tabs>
  )
}

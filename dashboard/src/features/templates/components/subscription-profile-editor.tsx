import { CodeEditorPanel } from '@/components/common/code-editor-panel'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { parseSubscriptionProfileForEditing, serializeSubscriptionProfile, type SubscriptionProfileFormValue } from '@/features/templates/forms/subscription-profile-form'
import { Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

interface SubscriptionProfileEditorProps {
  /** Which generator will read this profile. Half the settings are read by one
   *  core and ignored by the other, and the editor used to show them all. */
  core: 'xray' | 'sing_box'
  structuredOnly?: boolean
  showIntro?: boolean
  value: string
  onChange: (value: string) => void
  onValidate: (markers: unknown[]) => void
  dialogOpen: boolean
  onFullscreenChange: (fullscreen: boolean) => void
}

const splitList = (value: string) =>
  value
    .split(',')
    .map(entry => entry.trim())
    .filter(Boolean)

function CommaListEditor({ value, placeholder, onChange }: { value: string[]; placeholder?: string; onChange: (value: string[]) => void }) {
  const joined = value.join(', ')
  const [draft, setDraft] = useState(joined)

  useEffect(() => {
    // Only adopt an outside edit. Rewriting the draft from the parsed list
    // would swallow the separator the operator is in the middle of typing.
    setDraft(current => (splitList(current).join(', ') === joined ? current : joined))
  }, [joined])

  return (
    <Input
      value={draft}
      placeholder={placeholder}
      onChange={event => {
        setDraft(event.target.value)
        onChange(splitList(event.target.value))
      }}
    />
  )
}

// Strategies that ignore the observatory ignore these knobs too.
const OBSERVATORY_STRATEGIES = new Set(['leastPing', 'leastLoad'])

type BalancerSettings = NonNullable<SubscriptionProfileFormValue['balancer_settings']>

/** Drops the object once both knobs are cleared, so an untouched profile keeps
 *  serializing exactly as it did before the operator opened this section. */
function withBalancerSetting(current: SubscriptionProfileFormValue['balancer_settings'], patch: Partial<BalancerSettings>): BalancerSettings | null {
  const next = { ...current, ...patch }
  const { expected, baselines, ...rest } = next
  if (expected == null && (baselines == null || baselines.length === 0) && Object.keys(rest).length === 0) return null
  return next
}

export function SubscriptionProfileEditor({ core, value, onChange, onValidate, dialogOpen, onFullscreenChange, structuredOnly = false, showIntro = true }: SubscriptionProfileEditorProps) {
  const { t } = useTranslation()
  // Verified against the two generators: build_singbox_profile reaches none of
  // domain_strategy, balancer_strategy, balancer_settings,
  // publish_endpoint_configs, health_check.burst or a pool's fallback_pool,
  // and build_xray_profile reaches none of health_check.tolerance. Showing
  // them anyway is an invitation to configure something that does nothing.
  const isXray = core === 'xray'
  const [tab, setTab] = useState('structured')
  const parsed = parseSubscriptionProfileForEditing(value)

  const updateProfile = (updater: (profile: SubscriptionProfileFormValue) => SubscriptionProfileFormValue) => {
    if (!parsed.success) return
    onChange(serializeSubscriptionProfile(updater(parsed.data)))
    onValidate([])
  }

  return (
    <Tabs value={tab} onValueChange={setTab} className="flex h-full min-h-[450px] flex-col">
      {!structuredOnly && (
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="structured">{t('clientTemplates.profile.structured', { defaultValue: 'Server groups' })}</TabsTrigger>
          <TabsTrigger value="raw">{t('clientTemplates.profile.rawJson', { defaultValue: 'Generator JSON' })}</TabsTrigger>
        </TabsList>
      )}

      <TabsContent value="structured" className="mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
        {!parsed.success ? (
          <div className="border-destructive/40 bg-destructive/5 rounded-lg border p-4 text-sm">
            <p className="text-destructive font-medium">{t('clientTemplates.profile.cannotOpenStructured', { defaultValue: 'This profile cannot be opened in the structured editor.' })}</p>
            <p className="text-muted-foreground mt-1 break-words">{parsed.error}</p>
            <Button type="button" variant="outline" size="sm" className="mt-3" onClick={() => setTab('raw')} hidden={structuredOnly}>
              {t('clientTemplates.profile.openRawJson', { defaultValue: 'Open Raw JSON' })}
            </Button>
          </div>
        ) : (
          <div className="space-y-5 pb-2">
            {showIntro && (
              <p className="text-muted-foreground text-xs">
                {t('clientTemplates.profile.scopeHelp', {
                  defaultValue: 'Configure automatic server groups and health checks here. Advanced generator fields remain available in optional JSON.',
                })}
              </p>
            )}
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

              {isXray && (
                <label className="grid gap-1.5 text-sm">
                  <span>{t('clientTemplates.profile.balancerStrategy', { defaultValue: 'Balancer strategy' })}</span>
                  <Select
                    value={parsed.data.balancer_strategy}
                    onValueChange={value =>
                      updateProfile(profile => ({
                        ...profile,
                        balancer_strategy: value as typeof profile.balancer_strategy,
                        // The tuning box unmounts for the strategies that ignore
                        // these, so a value left behind would keep reaching the
                        // config with nothing in the form able to show or clear
                        // it. Only clear on the way out of a strategy that read
                        // it: between two that never did, this switch is not
                        // what put the value there and must not delete it.
                        balancer_settings: OBSERVATORY_STRATEGIES.has(profile.balancer_strategy) && !OBSERVATORY_STRATEGIES.has(value) ? null : profile.balancer_settings,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(['random', 'roundRobin', 'leastPing', 'leastLoad'] as const).map(option => (
                        <SelectItem key={option} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-muted-foreground text-xs">
                    {t('clientTemplates.profile.balancerStrategyHelp', {
                      defaultValue: 'leastPing and leastLoad need latency probing enabled below.',
                    })}
                  </p>
                </label>
              )}

              {isXray && OBSERVATORY_STRATEGIES.has(parsed.data.balancer_strategy) && (
                <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-2">
                  <p className="text-sm font-medium sm:col-span-2">{t('clientTemplates.profile.balancerSettings', { defaultValue: 'Balancer tuning' })}</p>
                  <label className="grid gap-1.5 text-sm">
                    <span>{t('clientTemplates.profile.balancerExpected', { defaultValue: 'Servers to spread across' })}</span>
                    <Input
                      type="number"
                      min={1}
                      max={64}
                      value={parsed.data.balancer_settings?.expected ?? ''}
                      onChange={event => {
                        const expected = event.target.value === '' ? null : Number(event.target.value)
                        updateProfile(profile => ({ ...profile, balancer_settings: withBalancerSetting(profile.balancer_settings, { expected }) }))
                      }}
                    />
                    <p className="text-muted-foreground text-xs">
                      {t('clientTemplates.profile.balancerExpectedHelp', {
                        defaultValue: 'leastLoad picks at random among this many of the fastest servers. Leave empty to always use the single fastest one.',
                      })}
                    </p>
                  </label>
                  <label className="grid gap-1.5 text-sm">
                    <span>{t('clientTemplates.profile.balancerBaselines', { defaultValue: 'Latency baselines' })}</span>
                    <CommaListEditor
                      value={parsed.data.balancer_settings?.baselines ?? []}
                      placeholder="1500ms, 3s"
                      onChange={baselines =>
                        updateProfile(profile => ({ ...profile, balancer_settings: withBalancerSetting(profile.balancer_settings, { baselines: baselines.length ? baselines : null }) }))
                      }
                    />
                    <p className="text-muted-foreground text-xs">
                      {t('clientTemplates.profile.balancerBaselinesHelp', {
                        defaultValue: 'Comma-separated, for example 1500ms, 3s. A server slower than every baseline is used only as a last resort.',
                      })}
                    </p>
                  </label>
                </div>
              )}

              {isXray && (
                <label className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
                  <span className="grid gap-1">
                    <span>{t('clientTemplates.profile.publishEndpointConfigs', { defaultValue: 'Publish a config per server' })}</span>
                    <span className="text-muted-foreground text-xs">
                      {t('clientTemplates.profile.publishEndpointConfigsHelp', {
                        defaultValue: 'Lets the user pick one server instead of only an automatic group.',
                      })}
                    </span>
                  </span>
                  <Switch checked={parsed.data.publish_endpoint_configs} onCheckedChange={publish_endpoint_configs => updateProfile(profile => ({ ...profile, publish_endpoint_configs }))} />
                </label>
              )}

              {isXray && (
                <label className="flex items-center justify-between gap-3 rounded-md border p-3 text-sm">
                  <span className="grid gap-1">
                    <span>{t('clientTemplates.profile.burstObservatory', { defaultValue: 'Measure latency (burst observatory)' })}</span>
                    <span className="text-muted-foreground text-xs">
                      {t('clientTemplates.profile.burstObservatoryHelp', {
                        defaultValue: 'Required by leastPing and leastLoad; plain probing only tracks alive or dead.',
                      })}
                    </span>
                  </span>
                  <Switch checked={parsed.data.health_check.burst} onCheckedChange={burst => updateProfile(profile => ({ ...profile, health_check: { ...profile.health_check, burst } }))} />
                </label>
              )}

              <div className="space-y-3">
                {parsed.data.pools.map((pool, index) => (
                  <div key={`${pool.id}-${index}`} className="grid gap-3 rounded-md border p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
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
                      <span>{t('clientTemplates.profile.poolTitle', { defaultValue: 'Display name' })}</span>
                      <Input
                        value={pool.title ?? ''}
                        placeholder={`Auto (${pool.id})`}
                        onChange={event => {
                          const title = event.target.value
                          updateProfile(profile => ({
                            ...profile,
                            pools: profile.pools.map((entry, entryIndex) => (entryIndex === index ? { ...entry, title: title || null } : entry)),
                          }))
                        }}
                      />
                    </label>
                    {isXray && (
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
                    )}
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
                <label className="grid gap-1.5 text-sm">
                  <span>{t('clientTemplates.profile.interval', { defaultValue: 'Interval' })}</span>
                  <Input
                    value={parsed.data.health_check.interval}
                    onChange={event => updateProfile(profile => ({ ...profile, health_check: { ...profile.health_check, interval: event.target.value } }))}
                  />
                </label>
                {!isXray && (
                  <label className="grid gap-1.5 text-sm">
                    <span>{t('clientTemplates.profile.tolerance', { defaultValue: 'Tolerance' })}</span>
                    <Input
                      type="number"
                      min={0}
                      max={65535}
                      value={parsed.data.health_check.tolerance}
                      onChange={event => updateProfile(profile => ({ ...profile, health_check: { ...profile.health_check, tolerance: Number(event.target.value) } }))}
                    />
                  </label>
                )}
                {!isXray && (
                  <label className="grid gap-1.5 text-sm">
                    <span>{t('clientTemplates.profile.idleTimeout', { defaultValue: 'Idle timeout' })}</span>
                    <Input
                      value={parsed.data.health_check.timeout}
                      onChange={event => updateProfile(profile => ({ ...profile, health_check: { ...profile.health_check, timeout: event.target.value } }))}
                    />
                  </label>
                )}
                {isXray && parsed.data.health_check.burst && (
                  <label className="grid gap-1.5 text-sm">
                    <span>{t('clientTemplates.profile.probeTimeout', { defaultValue: 'Probe timeout' })}</span>
                    <Input
                      value={parsed.data.health_check.probe_timeout}
                      onChange={event => updateProfile(profile => ({ ...profile, health_check: { ...profile.health_check, probe_timeout: event.target.value } }))}
                    />
                  </label>
                )}
              </div>
            </section>
          </div>
        )}
      </TabsContent>

      <TabsContent value="raw" className="mt-3 min-h-0 flex-1">
        <CodeEditorPanel
          value={value}
          language="json"
          onChange={nextValue => {
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

import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { applyEdits, modify } from 'jsonc-parser'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { parseSubscriptionProfileForEditing } from '@/features/templates/forms/subscription-profile-form'

/** Edits generator parameters only. Native config fields never enter this editor. */
export function GeneratorConfigurationEditor({
  content,
  core,
  section,
  onChange,
  onDirtyChange,
}: {
  content: string
  core: 'xray' | 'sing_box'
  section: 'routing' | 'dns'
  onChange: (content: string) => void
  onDirtyChange: (dirty: boolean) => void
}) {
  const { t } = useTranslation()
  const parsed = useMemo(() => parseSubscriptionProfileForEditing(content), [content])
  const value = parsed.success ? (section === 'routing' ? JSON.stringify(parsed.data.routing_rules, null, 2) : parsed.data.dns.servers.join('\n')) : ''
  const [draft, setDraft] = useState(value)
  useEffect(() => setDraft(value), [value])
  const changeDraft = (next: string) => {
    onDirtyChange(next !== value)
    setDraft(next)
  }
  const dirty = draft !== value
  useEffect(() => {
    onDirtyChange(dirty)
  }, [dirty, onDirtyChange])
  let patch: unknown
  let error = ''
  try {
    patch =
      section === 'routing'
        ? JSON.parse(draft)
        : draft
            .split(/\r?\n/)
            .map(item => item.trim())
            .filter(Boolean)
    if (!Array.isArray(patch) || (section === 'routing' && patch.some(item => !item || Array.isArray(item) || typeof item !== 'object'))) throw new Error('invalid')
  } catch {
    error = t('clientSettings.native.invalidValue', 'Enter a valid value.')
  }
  if (!parsed.success)
    return (
      <p role="alert" className="text-destructive text-sm">
        {parsed.error}
      </p>
    )
  const update = (path: (string | number)[], value: unknown) => onChange(applyEdits(content, modify(content, path, value, { formattingOptions: { insertSpaces: true, tabSize: 2 } })))
  const example = core === 'xray' ? '[{"type":"field","domain":["domain:example.com"],"outboundTag":"direct"}]' : '[{"domain_suffix":["example.com"],"outbound":"direct"}]'
  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">
        {section === 'routing'
          ? t('clientSettings.generatorRoutingHelp', 'Ordered routing_rules parameters (JSON array). Rules use the selected core’s matching fields. An empty list uses the default pool.')
          : t('clientSettings.generatorDnsHelp', 'DNS resolver addresses, one per line: an IP address or an https://host/path DoH URL.')}
      </p>
      {section === 'routing' && (
        <>
          <p className="text-muted-foreground text-xs">{t('clientSettings.generatorRouteExample', 'Example: direct traffic for example.com')}</p>
          <code className="block overflow-x-auto rounded border p-2 text-xs">{example}</code>
          <p className="text-muted-foreground text-xs">
            {t('clientSettings.generatorRouteTargets', 'Use stable target IDs below, never display titles. Preview verifies targets against this user’s available servers.')}{' '}
            {parsed.data.pools
              .filter(pool => pool.enabled)
              .map(pool => (core === 'xray' ? `balancerTag: pg-auto-${pool.id}` : `outbound: ${pool.id} / pg-auto-${pool.id}`))
              .join('; ')}
          </p>
          {core === 'xray' && (
            <label className="grid gap-1 text-sm">
              {t('clientSettings.generatorDomainStrategy', 'Domain resolution strategy')}
              <select className="bg-background h-10 rounded-md border px-3" value={parsed.data.domain_strategy} disabled={dirty} onChange={event => update(['domain_strategy'], event.target.value)}>
                {['AsIs', 'IPIfNonMatch', 'IPOnDemand'].map(value => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
          )}
        </>
      )}
      <label className="grid gap-1 text-sm">
        {section === 'routing' ? t('clientSettings.generatorRoutingParameters', 'Routing parameters (JSON)') : t('clientSettings.generatorDnsServers', 'DNS resolvers')}
        <Textarea className="min-h-40 font-mono text-xs" value={draft} onChange={event => changeDraft(event.target.value)} />
      </label>
      {dirty && (
        <div className="flex gap-2">
          <Button size="sm" disabled={Boolean(error)} onClick={() => update(section === 'routing' ? ['routing_rules'] : ['dns', 'servers'], patch)}>
            {t('clientSettings.native.apply', 'Apply')}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => changeDraft(value)}>
            {t('clientSettings.native.cancel', 'Cancel')}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      )}
    </div>
  )
}

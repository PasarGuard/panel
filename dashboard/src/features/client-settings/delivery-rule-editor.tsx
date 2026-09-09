import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { ClientTemplateResponse } from '@/service/api'
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { bindRule, CLIENT_APPLICATIONS, configurationLabel, compatibleTemplates, ruleTemplateId, type DraftRule } from './workspace-model'
export const selectClass = 'bg-background flex h-10 w-full min-w-0 rounded-md border px-3 py-2 text-sm'
const TARGETS = ['links', 'links_base64', 'xray', 'sing_box', 'clash', 'clash_meta', 'wireguard', 'outline', 'block'] as const
export function DeliveryRuleEditor({
  rule,
  templates,
  onChange,
  lockedSource = false,
  applicationContext = false,
}: {
  rule: DraftRule
  templates: ClientTemplateResponse[]
  onChange: (rule: DraftRule) => void
  lockedSource?: boolean
  applicationContext?: boolean
}) {
  const { t } = useTranslation()
  const sourceId = ruleTemplateId(rule)
  const sources = compatibleTemplates(templates, rule.target)
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="space-y-1 text-sm">
          <span>{t('clientSettings.condition', 'User-Agent expression')}</span>
          <Input value={rule.pattern} onChange={event => onChange({ ...rule, pattern: event.target.value })} className="font-mono" />
        </label>
        {!applicationContext && (
          <label className="space-y-1 text-sm">
            <span>{t('clientSettings.application', 'Application')}</span>
            <select disabled={lockedSource} className={selectClass} value={rule.ui_application ?? ''} onChange={event => onChange({ ...rule, ui_application: event.target.value || null })}>
              <option value="">{t('clientSettings.unassigned', 'Not assigned')}</option>
              {rule.ui_application && !CLIENT_APPLICATIONS.some(app => app.id === rule.ui_application) && <option value={rule.ui_application}>{rule.ui_application}</option>}
              {CLIENT_APPLICATIONS.map(app => (
                <option key={app.id} value={app.id}>
                  {app.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="space-y-1 text-sm">
          <span>{t('clientSettings.format', 'Response format')}</span>
          <select
            disabled={lockedSource}
            className={selectClass}
            value={rule.target}
            onChange={event => {
              const target = event.target.value as DraftRule['target']
              const compatible = sourceId && compatibleTemplates(templates, target).some(item => item.id === sourceId)
              onChange({ ...rule, target, ...(compatible ? {} : { template_id: undefined, happ_routing: undefined }) })
            }}
          >
            {TARGETS.map(target => (
              <option key={target} value={target}>
                {t(`settings.subscriptions.configFormats.${target}`, configurationLabel(target))}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span>{t('clientSettings.configuration', 'Configuration')}</span>
          <select
            disabled={lockedSource}
            className={selectClass}
            value={lockedSource ? '__draft' : (sourceId ?? '')}
            onChange={event => {
              const source = sources.find(item => item.id === Number(event.target.value))
              onChange(source ? bindRule(rule, source.template_type, source.id) : { ...rule, template_id: undefined, happ_routing: undefined })
            }}
          >
            {lockedSource && <option value="__draft">{t('clientSettings.draftDocument', 'This document draft')}</option>}
            <option value="">{t('clientSettings.currentDefault', 'Current default')}</option>
            {sourceId && !sources.some(item => item.id === sourceId) && (
              <option value={sourceId}>
                #{sourceId} · {t('clientSettings.unavailable', 'Unavailable')}
              </option>
            )}
            {sources.map(item => (
              <option key={item.id} value={item.id}>
                {item.name} · {configurationLabel(item.template_type)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {!applicationContext && (
        <p className="text-muted-foreground text-xs">{t('clientSettings.assignmentHelp', 'The application label organizes rules. Matching still uses the expression and order.')}</p>
      )}
      {rule.happ_routing && (
        <div className="grid gap-3 rounded-lg border p-3 sm:grid-cols-3">
          <label className="space-y-1 text-sm">
            {t('clientSettings.transport', 'Routing delivery')}
            <select
              className={selectClass}
              value={rule.happ_routing.transport}
              onChange={e => onChange({ ...rule, target: e.target.value === 'body' ? 'links' : rule.target, happ_routing: { ...rule.happ_routing!, transport: e.target.value as 'body' | 'header' } })}
            >
              <option value="body">{t('clientSettings.body', 'Subscription body')}</option>
              <option value="header">{t('clientSettings.header', 'Response header')}</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            {t('clientSettings.action', 'Import action')}
            <select className={selectClass} value={rule.happ_routing.action} onChange={e => onChange({ ...rule, happ_routing: { ...rule.happ_routing!, action: e.target.value as 'add' | 'onadd' } })}>
              <option value="onadd">onadd</option>
              <option value="add">add</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            {t('clientSettings.routingEnabled', 'Enable routing')}
            <select
              className={selectClass}
              value={String(rule.happ_routing.enabled)}
              onChange={e => onChange({ ...rule, happ_routing: { ...rule.happ_routing!, enabled: e.target.value === 'null' ? null : e.target.value === 'true' } })}
            >
              <option value="null">{t('clientSettings.keepClientChoice', 'Keep client choice')}</option>
              <option value="true">{t('clientSettings.enabled', 'Enabled')}</option>
              <option value="false">{t('clientSettings.disabled', 'Disabled')}</option>
            </select>
          </label>
        </div>
      )}
      <details className="rounded-lg border p-3">
        <summary className="cursor-pointer text-sm">
          {t('clientSettings.headers', 'Response headers')} · {Object.keys(rule.response_headers ?? {}).length}
        </summary>
        <div className="mt-4 space-y-3">
          <p className="text-sm">{t('clientSettings.headers', 'Response headers')}</p>
          {Object.entries(rule.response_headers ?? {}).map(([key, value], index) => (
            <div key={index} className="flex gap-2">
              <Input
                aria-label={t('clientSettings.headerName', 'Header name')}
                value={key}
                onChange={e =>
                  onChange({ ...rule, response_headers: Object.fromEntries(Object.entries(rule.response_headers ?? {}).map(([name, item]) => [name === key ? e.target.value : name, item])) })
                }
              />
              <Input
                aria-label={t('clientSettings.headerValue', 'Header value')}
                value={typeof value === 'string' ? value : JSON.stringify(value)}
                onChange={e => onChange({ ...rule, response_headers: { ...rule.response_headers, [key]: e.target.value } })}
              />
              <Button
                variant="ghost"
                size="icon"
                aria-label={t('clientSettings.removeHeader', 'Remove header')}
                onClick={() => onChange({ ...rule, response_headers: Object.fromEntries(Object.entries(rule.response_headers ?? {}).filter(([name]) => name !== key)) })}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>
          ))}
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              let number = Object.keys(rule.response_headers ?? {}).length + 1
              while (`x-header-${number}` in (rule.response_headers ?? {})) number++
              onChange({ ...rule, response_headers: { ...rule.response_headers, [`x-header-${number}`]: '' } })
            }}
          >
            {t('clientSettings.addHeader', 'Add header')}
          </Button>
        </div>
      </details>
    </div>
  )
}
export function DeliveryRules({ rules, templates, onChange, readOnly }: { rules: DraftRule[]; templates: ClientTemplateResponse[]; onChange: (rules: DraftRule[]) => void; readOnly: boolean }) {
  const { t } = useTranslation()
  const move = (index: number, direction: number) => {
    const next = [...rules]
    ;[next[index], next[index + direction]] = [next[index + direction], next[index]]
    onChange(next)
  }
  return (
    <div className="space-y-4">
      <p className="text-muted-foreground text-sm">{t('clientSettings.rulesHelp', 'The first matching rule wins. Existing expressions and their order are preserved until you edit them.')}</p>
      <fieldset disabled={readOnly} className="min-w-0 space-y-4">
        {rules.map((rule, index) => (
          <article key={index} className="bg-card space-y-4 rounded-xl border p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-medium">
                {t('clientSettings.rule', 'Rule')} {index + 1}{' '}
                <span className="text-muted-foreground text-sm">
                  · {CLIENT_APPLICATIONS.find(app => app.id === rule.ui_application)?.name ?? rule.ui_application ?? t('clientSettings.unassigned', 'Not assigned')}
                </span>
              </h3>
              <div className="flex gap-1">
                <Button variant="ghost" size="icon" disabled={index === 0} aria-label={t('clientSettings.moveUp', 'Move up')} onClick={() => move(index, -1)}>
                  <ArrowUp className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon" disabled={index === rules.length - 1} aria-label={t('clientSettings.moveDown', 'Move down')} onClick={() => move(index, 1)}>
                  <ArrowDown className="h-4 w-4" />
                </Button>
                <Button variant="ghost" size="icon" aria-label={t('clientSettings.removeRule', 'Remove rule')} onClick={() => onChange(rules.filter((_, item) => index !== item))}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <DeliveryRuleEditor rule={rule} templates={templates} onChange={value => onChange(rules.map((item, i) => (i === index ? value : item)))} />
          </article>
        ))}
        <Button variant="outline" onClick={() => onChange([...rules, { pattern: '.*', target: 'links_base64' }])}>
          <Plus className="mr-2 h-4 w-4" />
          {t('clientSettings.addRule', 'Add rule')}
        </Button>
      </fieldset>
    </div>
  )
}

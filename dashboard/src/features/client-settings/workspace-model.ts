import type { ClientTemplateResponse, ClientTemplateType, SubRule, Subscription } from '@/service/api'
import { parseTree, printParseErrorCode, type ParseError } from 'jsonc-parser'
import { parseDocument } from 'yaml'

export type ApplicationId = 'happ' | 'mihomo' | 'sing_box' | 'xray'
export type NativeFormat = 'happ' | 'clash' | 'sing_box' | 'xray'
export const CLIENT_APPLICATIONS: { id: ApplicationId; name: string; format: NativeFormat; target: SubRule['target']; pattern: string; userAgent: string }[] = [
  { id: 'happ', name: 'Happ', format: 'happ', target: 'links', pattern: '^[Hh]app', userAgent: 'Happ/1.0' },
  { id: 'mihomo', name: 'Mihomo / Clash', format: 'clash', target: 'clash_meta', pattern: '^([Mm]ihomo|[Cc]lash|[Ff][Ll][Cc]lash)', userAgent: 'mihomo/1.19' },
  { id: 'sing_box', name: 'Sing-box', format: 'sing_box', target: 'sing_box', pattern: '^(sing-box|SFA|SFI|SFM|SFT)', userAgent: 'sing-box/1.12' },
  { id: 'xray', name: 'Xray', format: 'xray', target: 'xray', pattern: '^([Vv]2rayNG|[Vv]2rayN|[Ss]treisand)', userAgent: 'v2rayNG/1.10' },
]
export const NATIVE_TYPES: Record<NativeFormat, ClientTemplateType> = { happ: 'happ_routing', clash: 'clash_subscription', sing_box: 'singbox_subscription', xray: 'xray_subscription' }
export interface WorkspaceSnapshot {
  sync_warning?: 'worker_notification_failed' | 'cache_refresh_failed' | null
  revision: string
  subscription: Subscription
  templates: ClientTemplateResponse[]
}
export interface TemplateDraft {
  id?: number
  name: string
  template_type: ClientTemplateType
  content: string
  is_default: boolean
}
export type DraftRule = Omit<SubRule, 'happ_routing'> & { happ_routing?: (Omit<NonNullable<SubRule['happ_routing']>, 'template_id'> & { template_id?: number }) | null }
export interface WorkspaceChange {
  expected_revision: string
  template?: TemplateDraft
  rules: DraftRule[]
  bind_rule_indices?: number[]
}
export function assignedRules(rules: readonly DraftRule[], application: ApplicationId) {
  return rules.flatMap((rule, index) => (rule.ui_application === application ? [{ rule, index }] : []))
}
export function ruleTemplateId(rule: DraftRule | undefined): number | undefined {
  return rule?.happ_routing?.template_id ?? rule?.template_id ?? rule?.profile_id ?? undefined
}
export function templateUsages(rules: readonly DraftRule[], id: number) {
  return rules.flatMap((rule, index) => (rule.template_id === id || rule.profile_id === id || rule.happ_routing?.template_id === id ? [{ rule, index }] : []))
}
export const isGeneratorType = (type: string) => type === 'xray_profile' || type === 'singbox_profile'
export function applicationTypes(app: (typeof CLIENT_APPLICATIONS)[number]): ClientTemplateType[] {
  if (app.id === 'happ') return ['happ_routing', 'xray_subscription', 'xray_profile']
  if (app.id === 'xray') return ['xray_subscription', 'xray_profile']
  if (app.id === 'sing_box') return ['singbox_subscription', 'singbox_profile']
  return ['clash_subscription']
}
export function formatForType(type: ClientTemplateType): NativeFormat {
  if (type === 'happ_routing') return 'happ'
  if (type.startsWith('clash')) return 'clash'
  if (type.startsWith('singbox')) return 'sing_box'
  return 'xray'
}
export function configurationLabel(type: string): string {
  const label =
    type === 'user_agent'
      ? 'HTTP User-Agent'
      : type === 'grpc_user_agent'
        ? 'gRPC User-Agent'
        : type.startsWith('happ')
          ? 'Happ'
          : type.startsWith('clash') || type === 'mihomo'
            ? 'Mihomo / Clash'
            : type.startsWith('sing')
              ? 'Sing-box'
              : type.startsWith('xray')
                ? 'Xray'
                : type
  return label
}
export function editAssignedDocument(source: ClientTemplateResponse): TemplateDraft {
  return { id: source.id, name: source.name, template_type: source.template_type, content: source.content, is_default: source.is_default }
}
export function applicationDocument(source: ClientTemplateResponse, application: string): TemplateDraft {
  return source.is_default || source.is_system ? copyForApplication(source, application) : editAssignedDocument(source)
}
/** Ignore object key ordering and omitted optional fields when comparing API rules. */
function comparable(value: unknown): string {
  return JSON.stringify(value, (_key, item) => (item && typeof item === 'object' && !Array.isArray(item) ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item))
}
export function workspaceHasChanges(snapshot: WorkspaceSnapshot | null, change: WorkspaceChange | null): boolean {
  if (!snapshot || !change) return false
  if (comparable(snapshot.subscription.rules) !== comparable(change.rules)) return true
  if (!change.template) return false
  const saved = snapshot.templates.find(item => item.id === change.template!.id)
  return !saved || comparable(editAssignedDocument(saved)) !== comparable(change.template)
}
export interface SourceError {
  message: string
  line: number
  column: number
}
export function codeSourceError(type: ClientTemplateType, content: string): SourceError | null {
  // Native subscription documents can contain Jinja control flow. Their full
  // syntax is checked by the server renderer during preview/save.
  if (/\{[{%#]/.test(content) && type !== 'happ_routing' && !isGeneratorType(type)) return null
  if (type === 'clash_subscription') {
    const document = parseDocument(content)
    const error = document.errors[0]
    if (!error) return null
    return { message: error.code, line: error.linePos?.[0].line ?? 1, column: error.linePos?.[0].col ?? 1 }
  }
  const errors: ParseError[] = []
  parseTree(content, errors, { allowTrailingComma: false, disallowComments: true })
  const first = errors[0]
  if (!first) return null
  const prefix = content.slice(0, first.offset).split('\n')
  return { message: printParseErrorCode(first.error), line: prefix.length, column: prefix[prefix.length - 1].length + 1 }
}
export function workspaceErrorDetail(error: unknown): string | null {
  const detail = (error as { data?: { detail?: unknown } })?.data?.detail
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return null
  const messages = detail.flatMap(value => {
    if (!value || typeof value !== 'object' || typeof value.msg !== 'string') return []
    const path = Array.isArray(value.loc) ? value.loc.filter((part: unknown) => typeof part === 'string' || typeof part === 'number').join('.') : ''
    return [`${path ? `${path}: ` : ''}${value.msg}`]
  })
  return messages.length ? messages.join('\n') : null
}
export function compatibleTemplates(templates: readonly ClientTemplateResponse[], target: string) {
  const format = target === 'clash_meta' || target === 'clash' ? 'clash' : target === 'sing_box' ? 'sing_box' : target === 'xray' ? 'xray' : null
  return templates.filter(item =>
    format
      ? item.template_type === NATIVE_TYPES[format] || (format === 'xray' && item.template_type === 'xray_profile') || (format === 'sing_box' && item.template_type === 'singbox_profile')
      : (target === 'links' || target === 'links_base64') && item.template_type === 'happ_routing',
  )
}
/** Binding is explicit. Unknown UA expressions are never interpreted as ownership. */
export function bindRule(rule: DraftRule, type: ClientTemplateType, id?: number): DraftRule {
  const next = { ...rule, template_id: undefined, profile_id: undefined, happ_routing: undefined }
  if (type === 'happ_routing')
    return {
      ...next,
      target: rule.happ_routing && (rule.target === 'links' || rule.target === 'links_base64') ? rule.target : 'links',
      happ_routing: { transport: 'body', action: 'onadd', enabled: null, ...rule.happ_routing, template_id: id },
    }
  return isGeneratorType(type) ? { ...next, profile_id: id } : { ...next, template_id: id }
}
export function copyForApplication(source: Pick<ClientTemplateResponse, 'name' | 'content' | 'template_type'>, application: string): TemplateDraft {
  return { name: `${application} · ${source.name}`.slice(0, 64), content: source.content, template_type: source.template_type, is_default: false }
}
export function changeForApplication(
  snapshot: { revision: string; subscription: { rules: DraftRule[] } },
  app: (typeof CLIENT_APPLICATIONS)[number],
  template: TemplateDraft,
  existingIndex?: number,
): WorkspaceChange {
  const rules: DraftRule[] = structuredClone(snapshot.subscription.rules)
  const index = existingIndex ?? 0
  const target =
    template.template_type === 'happ_routing'
      ? existingIndex !== undefined && rules[index].happ_routing
        ? rules[index].target
        : 'links'
      : formatForType(template.template_type) === 'clash'
        ? 'clash_meta'
        : formatForType(template.template_type) === 'sing_box'
          ? 'sing_box'
          : 'xray'
  const rule = bindRule(
    existingIndex === undefined ? { pattern: app.pattern, target, ui_application: app.id } : { ...rules[index], target, ui_application: app.id },
    template.template_type,
    template.id,
  )
  if (existingIndex === undefined) rules.unshift(rule)
  else rules[index] = rule
  return { expected_revision: snapshot.revision, template, rules, bind_rule_indices: [index] }
}
export function isRevisionConflict(error: unknown) {
  const value = error as { status?: number; statusCode?: number; response?: { status?: number }; data?: { detail?: unknown } }
  const conflict = value?.status === 409 || value?.statusCode === 409 || value?.response?.status === 409
  // A duplicate document name also uses HTTP 409 in the legacy template API.
  // It can be corrected in the draft without reloading the workspace.
  return conflict && value?.data?.detail !== 'Template with this name already exists for this type'
}
export function switchConfigurationDraft(
  current: TemplateDraft,
  type: ClientTemplateType,
  drafts: Partial<Record<ClientTemplateType, TemplateDraft>>,
  createContent: (type: ClientTemplateType) => string,
): TemplateDraft {
  drafts[current.template_type] = current
  return drafts[type] ?? { name: current.name, template_type: type, content: createContent(type), is_default: false }
}

import { describe, expect, it } from 'bun:test'
import {
  assignedRules,
  applicationDocument,
  workspaceHasChanges,
  bindRule,
  changeForApplication,
  CLIENT_APPLICATIONS,
  compatibleTemplates,
  copyForApplication,
  configurationLabel,
  editAssignedDocument,
  codeSourceError,
  workspaceErrorDetail,
  isRevisionConflict,
  switchConfigurationDraft,
  templateUsages,
  type TemplateDraft,
  type WorkspaceSnapshot,
} from './workspace-model'

const templates: WorkspaceSnapshot['templates'] = [
  { id: 1, name: 'Global Xray', content: '{"routing":{}}', template_type: 'xray_subscription', is_default: true, is_system: true },
  { id: 2, name: 'Shared Happ', content: '{"Name":"Shared"}', template_type: 'happ_routing', is_default: false, is_system: false },
]
const snapshot: WorkspaceSnapshot = {
  revision: 'original',
  templates,
  subscription: {
    rules: [
      { pattern: '^([Hh]app|[Vv]2rayNG)', target: 'xray', response_headers: { routing: 'legacy-link', custom: 'keep' } },
      { pattern: '.*', target: 'links_base64' },
    ],
  },
}

describe('client workspace transaction model', () => {
  it('duplicate document names are editable validation conflicts, not stale revisions', () => {
    expect(isRevisionConflict({ status: 409, data: { detail: 'Template with this name already exists for this type' } })).toBe(false)
    expect(isRevisionConflict({ status: 409, data: { detail: 'Workspace changed; reload before applying' } })).toBe(true)
  })
  it('edits an assigned document in place without creating a duplicate', () => {
    const configured = structuredClone(snapshot)
    configured.subscription.rules[0] = { pattern: '^Happ', target: 'links', ui_application: 'happ', happ_routing: { template_id: 2, transport: 'body', action: 'onadd', enabled: null } }
    const draft = editAssignedDocument(templates[1])
    draft.content = '{"Name":"Updated"}'
    const payload = changeForApplication(configured, CLIENT_APPLICATIONS[0], draft, 0)
    expect(payload.template?.id).toBe(2)
    expect(payload.rules[0].happ_routing?.template_id).toBe(2)
    expect(payload.template?.is_default).toBe(false)
    expect(templates[1].content).toBe('{"Name":"Shared"}')
    expect(copyForApplication(templates[1], 'Happ').id).toBeUndefined()
  })
  it('starts editable application drafts without copying ordinary assigned documents', () => {
    expect(applicationDocument(templates[1], 'Happ').id).toBe(2)
    expect(applicationDocument(templates[0], 'Xray').id).toBeUndefined()
    expect(applicationDocument({ ...templates[1], is_system: true }, 'Happ').is_default).toBe(false)
  })
  it('detects actual document and rule changes, including reverting a draft', () => {
    const change = { expected_revision: snapshot.revision, rules: structuredClone(snapshot.subscription.rules), template: editAssignedDocument(templates[1]) }
    expect(workspaceHasChanges(snapshot, change)).toBe(false)
    change.template.content = '{"Name":"Changed"}'
    expect(workspaceHasChanges(snapshot, change)).toBe(true)
    change.template.content = templates[1].content
    expect(workspaceHasChanges(snapshot, change)).toBe(false)
    change.rules[0].pattern = '^Changed'
    expect(workspaceHasChanges(snapshot, change)).toBe(true)
    expect(workspaceHasChanges(snapshot, { ...change, rules: snapshot.subscription.rules, template: copyForApplication(templates[1], 'Happ') })).toBe(true)
  })
  it('uses product names for native configuration labels', () => {
    expect(configurationLabel('xray_subscription')).toBe('Xray')
    expect(configurationLabel('singbox_subscription')).toBe('Sing-box')
    expect(configurationLabel('clash_subscription')).toBe('Mihomo / Clash')
    expect(configurationLabel('happ_routing')).toBe('Happ')
  })
  it('reports invalid JSON and YAML locations without rewriting the source', () => {
    const json = '{\n  "Name":\n}'
    expect(codeSourceError('happ_routing', json)).toMatchObject({ line: 3, column: 1 })
    expect(json).toBe('{\n  "Name":\n}')
    expect(codeSourceError('clash_subscription', 'dns:\n  nameserver: [\n')).toMatchObject({ line: 3, column: 1 })
    expect(codeSourceError('xray_subscription', '{"routing": {"rules": []}}')).toBeNull()
    expect(codeSourceError('user_agent', '{"list":["Mozilla/5.0"]}')).toBeNull()
    expect(codeSourceError('grpc_user_agent', 'Mozilla/5.0')).not.toBeNull()
    expect(codeSourceError('xray_subscription', '{/* comment */"routing":{}}')).not.toBeNull()
    expect(codeSourceError('xray_subscription', '{% for proxy in proxies %}{{ proxy }}{% endfor %}')).toBeNull()
  })
  it('keeps error messages and locations while excluding validation input values', () => {
    expect(workspaceErrorDetail({ data: { detail: [{ loc: ['body', 'template', 'content'], msg: 'Unknown group', input: 'secret' }] } })).toBe('body.template.content: Unknown group')
    expect(workspaceErrorDetail({ data: { detail: 'Configuration references an unavailable group' } })).toBe('Configuration references an unavailable group')
  })
  it('never guesses assignments from expressions', () => {
    expect(assignedRules(snapshot.subscription.rules, 'happ')).toEqual([])
  })
  it('configure copies a default into an isolated nondefault draft without an ID', () => {
    const draft = copyForApplication(templates[0], 'Xray')
    expect(draft).toEqual({ name: 'Xray · Global Xray', template_type: 'xray_subscription', content: templates[0].content, is_default: false })
    expect(templates[0].is_default).toBe(true)
  })
  it('new Happ flow atomically binds a new document without a placeholder ID', () => {
    const draft = copyForApplication(templates[1], 'Happ')
    const change = changeForApplication(snapshot, CLIENT_APPLICATIONS[0], draft)
    expect(change.expected_revision).toBe('original')
    expect(change.bind_rule_indices).toEqual([0])
    expect(change.rules[0]).toMatchObject({ ui_application: 'happ', target: 'links', happ_routing: { transport: 'body', action: 'onadd', enabled: null } })
    expect(JSON.stringify(change.rules[0])).not.toContain('template_id')
    expect(change.rules.slice(1)).toEqual(snapshot.subscription.rules)
    expect(snapshot.subscription.rules).toHaveLength(2)
  })
  it('editing one assigned rule preserves order, headers and other rules', () => {
    const configured = structuredClone(snapshot)
    configured.subscription.rules[0].ui_application = 'xray'
    const change = changeForApplication(configured, CLIENT_APPLICATIONS[3], copyForApplication(templates[0], 'Xray'), 0)
    expect(change.rules).toHaveLength(2)
    expect(change.rules[0].pattern).toBe(configured.subscription.rules[0].pattern)
    expect(change.rules[0].response_headers).toEqual(configured.subscription.rules[0].response_headers)
    expect(change.rules[1]).toEqual(configured.subscription.rules[1])
  })
  it('native binding removes incompatible Happ sources', () => {
    expect(bindRule({ pattern: '.*', target: 'xray', happ_routing: { template_id: 2, action: 'add', transport: 'header', enabled: true } }, 'xray_subscription', 1)).toMatchObject({
      template_id: 1,
      happ_routing: undefined,
    })
    expect(compatibleTemplates(templates, 'xray').map(item => item.id)).toEqual([1])
    expect(compatibleTemplates(templates, 'links').map(item => item.id)).toEqual([2])
  })
  it('changing an existing Happ document preserves delivery options and target', () => {
    const configured = structuredClone(snapshot)
    configured.subscription.rules[0] = {
      pattern: '^Happ',
      target: 'links_base64',
      ui_application: 'happ',
      happ_routing: { template_id: 2, transport: 'header', action: 'add', enabled: false },
      response_headers: { custom: 'keep' },
    }
    const changed = changeForApplication(configured, CLIENT_APPLICATIONS[0], copyForApplication(templates[1], 'Happ'), 0)
    expect(changed.rules[0]).toMatchObject({ target: 'links_base64', happ_routing: { transport: 'header', action: 'add', enabled: false }, response_headers: { custom: 'keep' } })
    expect(changed.rules[0].happ_routing?.template_id).toBeUndefined()
    expect(bindRule(configured.subscription.rules[0], 'happ_routing', 8).happ_routing).toEqual({ template_id: 8, transport: 'header', action: 'add', enabled: false })
  })
  it('reports shared usages across all binding kinds', () => {
    expect(
      templateUsages(
        [
          { pattern: 'a', target: 'xray', template_id: 1 },
          { pattern: 'b', target: 'xray', template_id: 1 },
        ],
        1,
      ).map(item => item.index),
    ).toEqual([0, 1])
  })
  it('retains independent native mode drafts', () => {
    const drafts = {}
    const happ: TemplateDraft = { name: 'Mine', template_type: 'happ_routing', content: '{"Name":"edited"}', is_default: false }
    const xray = switchConfigurationDraft(happ, 'xray_subscription', drafts, () => '{"routing":{}}')
    xray.content = '{"routing":{"rules":[]}}'
    expect(switchConfigurationDraft(xray, 'happ_routing', drafts, () => '{}')).toEqual(happ)
    expect(switchConfigurationDraft(happ, 'xray_subscription', drafts, () => '{}').content).toBe('{"routing":{"rules":[]}}')
  })
  it('recognizes revision conflicts without mutating the submitted draft', () => {
    const change = changeForApplication(snapshot, CLIENT_APPLICATIONS[0], copyForApplication(templates[1], 'Happ'))
    const before = JSON.stringify(change)
    expect(isRevisionConflict({ response: { status: 409 } })).toBe(true)
    expect(isRevisionConflict({ statusCode: 409 })).toBe(true)
    expect(isRevisionConflict({ status: 422 })).toBe(false)
    expect(JSON.stringify(change)).toBe(before)
  })
})

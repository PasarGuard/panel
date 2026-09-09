import { afterEach, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import type { WorkspaceChange, WorkspaceSnapshot } from './workspace-model'

const browser = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window: browser,
  document: browser.document,
  navigator: browser.navigator,
  HTMLElement: browser.HTMLElement,
  HTMLInputElement: browser.HTMLInputElement,
  HTMLTextAreaElement: browser.HTMLTextAreaElement,
  HTMLFormElement: browser.HTMLFormElement,
  HTMLSelectElement: browser.HTMLSelectElement,
  Element: browser.Element,
  Node: browser.Node,
  DocumentFragment: browser.DocumentFragment,
  CustomEvent: browser.CustomEvent,
  MutationObserver: browser.MutationObserver,
  ResizeObserver: browser.ResizeObserver,
  Event: browser.Event,
  requestAnimationFrame: browser.requestAnimationFrame.bind(browser),
  cancelAnimationFrame: browser.cancelAnimationFrame.bind(browser),
  getComputedStyle: browser.getComputedStyle.bind(browser),
  IS_REACT_ACT_ENVIRONMENT: true,
})
const original: WorkspaceSnapshot = {
  revision: '1',
  subscription: { rules: [{ pattern: '^Happ', target: 'links', ui_application: 'happ', happ_routing: { template_id: 2, transport: 'body', action: 'onadd', enabled: null } }] },
  templates: [
    { id: 2, name: 'Happ separate', template_type: 'happ_routing', content: '{"Name":"Happ","DirectSites":[],"GlobalProxy":"true"}', is_default: false, is_system: false },
    { id: 3, name: 'HTTP User-Agent default', template_type: 'user_agent', content: '{"list":["Mozilla/5.0"]}', is_default: true, is_system: false },
  ],
}
let activeSnapshot = structuredClone(original)
const saves: WorkspaceChange[] = []
// Monaco's worker imports require Vite. These DOM tests exercise visual drafts and navigation.
mock.module('@/components/common/code-editor-panel', () => ({
  CodeEditorPanel: ({ value, onChange, readOnly }: { value: string; onChange: (value: string) => void; readOnly: boolean }) =>
    createElement('textarea', { 'data-testid': 'source-code', value, readOnly, onChange: (event: { target: { value: string } }) => onChange(event.target.value) }),
}))
mock.module('@/hooks/use-admin', () => ({ useAdmin: () => ({ admin: { username: 'owner', role: { is_owner: true } } }) }))
mock.module('./workspace-api', () => ({
  getWorkspace: async () => structuredClone(activeSnapshot),
  applyWorkspace: async (change: WorkspaceChange) => {
    saves.push(structuredClone(change))
    return {
      ...structuredClone(activeSnapshot),
      revision: '2',
      subscription: { rules: change.rules },
      templates: [{ ...activeSnapshot.templates[0], ...change.template, id: change.template?.id ?? 9 }],
    }
  },
  previewWorkspace: async () => ({}),
}))
const { createElement, act } = await import('react')
const { createRoot } = await import('react-dom/client')
const { createMemoryRouter, RouterProvider } = await import('react-router')
const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
const { default: ClientSettingsPage } = await import('@/pages/_dashboard.client-settings')
const { default: i18n } = await import('i18next')
await i18n.init({ lng: 'en', resources: {} })
let root: ReturnType<typeof createRoot> | null = null
let client: InstanceType<typeof QueryClient> | null = null
afterEach(async () => {
  await act(async () => root?.unmount())
  client?.clear()
  browser.document.body.innerHTML = ''
  saves.length = 0
  activeSnapshot = structuredClone(original)
})

test('assigned app edits keep the ID and native drafts survive Routing/DNS and blocked navigation', async () => {
  const element = browser.document.createElement('div')
  browser.document.body.append(element)
  root = createRoot(element as unknown as HTMLElement)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter([{ path: '/client-settings/*', element: createElement(ClientSettingsPage) }], { initialEntries: ['/client-settings/applications/happ'] })
  await act(async () => {
    root!.render(createElement(QueryClientProvider, { client: client! }, createElement(RouterProvider, { router })))
    await new Promise(resolve => setTimeout(resolve, 20))
  })
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 20))
  })
  const button = (text: string) => [...browser.document.body.querySelectorAll('button')].find(item => item.textContent?.trim() === text)!
  expect(button('Edit')).toBeUndefined()
  expect(button('Save')).toBeUndefined()
  const textarea = element.querySelector('textarea')!
  const setter = Object.getOwnPropertyDescriptor(browser.HTMLTextAreaElement.prototype, 'value')!.set!
  await act(async () => {
    setter.call(textarea, 'example.com')
    textarea.dispatchEvent(new browser.Event('input', { bubbles: true }))
  })
  expect(button('Save').disabled).toBe(true)
  await act(async () => button('DNS').click())
  await act(async () => button('Routing').click())
  expect(element.querySelector('textarea')).toBe(textarea)
  expect(textarea.value).toBe('example.com')
  let confirmations = 0
  Object.assign(browser, {
    confirm: () => {
      confirmations++
      return false
    },
  })
  await act(async () => element.querySelector<import('happy-dom').HTMLButtonElement>('button[aria-label="Back"]')!.click())
  expect(confirmations).toBe(1)
  expect(router.state.location.pathname).toBe('/client-settings/applications/happ')
  expect(textarea.value).toBe('example.com')
  await act(async () => button('Apply').click())
  expect(button('Save').disabled).toBe(false)
  await act(async () => button('Save').click())
  expect(saves).toHaveLength(1)
  expect(saves[0].template?.id).toBe(2)
  expect(JSON.parse(saves[0].template!.content).DirectSites).toEqual(['example.com'])
  expect(button('Edit')).toBeUndefined()
  expect(button('Save')).toBeUndefined()
  await act(async () => button('DNS').click())
  await act(async () => button('Routing').click())
  expect(button('Save')).toBeUndefined()
  expect(saves).toHaveLength(1)
})

test('unapplied library fields guard navigation before a document change exists', async () => {
  const element = browser.document.createElement('div')
  browser.document.body.append(element)
  root = createRoot(element as unknown as HTMLElement)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter([{ path: '/client-settings/*', element: createElement(ClientSettingsPage) }], { initialEntries: ['/client-settings/configurations/2'] })
  await act(async () => {
    root!.render(createElement(QueryClientProvider, { client: client! }, createElement(RouterProvider, { router })))
    await new Promise(resolve => setTimeout(resolve, 20))
  })
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 20))
  })
  const button = (text: string) => [...browser.document.body.querySelectorAll('button')].find(item => item.textContent?.trim() === text)!
  expect(element.textContent).not.toContain('Use as the default for this format')
  const textarea = element.querySelector('textarea')!
  const setter = Object.getOwnPropertyDescriptor(browser.HTMLTextAreaElement.prototype, 'value')!.set!
  await act(async () => {
    setter.call(textarea, 'unapplied.example')
    textarea.dispatchEvent(new browser.Event('input', { bubbles: true }))
  })
  let confirmations = 0
  Object.assign(browser, {
    confirm: () => {
      confirmations++
      return false
    },
  })
  await act(async () => element.querySelector<import('happy-dom').HTMLButtonElement>('button[aria-label="Back"]')!.click())
  expect(confirmations).toBe(1)
  expect(router.state.location.pathname).toBe('/client-settings/configurations/2')
  expect(button('Save').disabled).toBe(true)
  await act(async () => button('Cancel').click())
  expect(element.querySelector('textarea')!.value).toBe('')
  expect(saves).toHaveLength(0)
})

async function openPage(path: string) {
  const element = browser.document.createElement('div')
  browser.document.body.append(element)
  root = createRoot(element as unknown as HTMLElement)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const router = createMemoryRouter([{ path: '/client-settings/*', element: createElement(ClientSettingsPage) }], { initialEntries: [path] })
  await act(async () => {
    root!.render(createElement(QueryClientProvider, { client: client! }, createElement(RouterProvider, { router })))
    await new Promise(resolve => setTimeout(resolve, 20))
  })
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 20))
  })
  return { element, router, button: (text: string) => [...browser.document.body.querySelectorAll('button')].find(item => item.textContent?.trim() === text)! }
}

test('application list has direct secondary links and no top tabs or Advanced menu', async () => {
  const { element, router, button } = await openPage('/client-settings/applications')
  expect(element.textContent).not.toContain('1 delivery rules')
  expect(element.textContent).not.toContain('Existing delivery expressions are retained')
  expect(element.querySelector('nav')).toBeNull()
  expect(element.querySelector('details')).toBeNull()
  const link = (text: string) => [...element.querySelectorAll('a')].find(item => item.textContent?.trim() === text)!
  expect(link('Saved configurations').getAttribute('href')).toBe('/client-settings/configurations')
  expect(link('Application matching order').getAttribute('href')).toBe('/client-settings/rules')
  await act(async () => link('Saved configurations').click())
  expect(router.state.location.pathname).toBe('/client-settings/configurations')
  expect(button('Save')).toBeUndefined()
  await act(async () => link('Applications').click())
  await act(async () => link('Application matching order').click())
  expect(router.state.location.pathname).toBe('/client-settings/rules')
  expect(button('Save')).toBeUndefined()
})

test('editor uses a single heading and guards both contextual configuration and matching-order links', async () => {
  const { element, router, button } = await openPage('/client-settings/applications/happ')
  expect([...element.querySelectorAll('h1')].map(item => item.textContent)).toEqual(['Happ'])
  expect(element.querySelector('nav')).toBeNull()
  const libraryLink = [...element.querySelectorAll('a')].find(item => item.textContent === 'Saved configurations')!
  expect(libraryLink.closest('details')?.querySelector('summary')?.textContent).toBe('Configuration options')
  expect(element.textContent).not.toContain('Application matching order')
  const textarea = element.querySelector('textarea')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(browser.HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, 'pending.example')
    textarea.dispatchEvent(new browser.Event('input', { bubbles: true }))
  })
  let confirmations = 0
  Object.assign(browser, {
    confirm: () => {
      confirmations++
      return false
    },
  })
  await act(async () => libraryLink.click())
  expect(confirmations).toBe(1)
  expect(router.state.location.pathname).toBe('/client-settings/applications/happ')
  await act(async () => button('Subscription delivery').click())
  const matchingLink = [...element.querySelectorAll('a')].find(item => item.textContent === 'Application matching order')!
  await act(async () => matchingLink.click())
  expect(confirmations).toBe(2)
  expect(router.state.location.pathname).toBe('/client-settings/applications/happ')
  expect(textarea.value).toBe('pending.example')
  await act(async () => button('Cancel').click())
  await act(async () => matchingLink.click())
  expect(router.state.location.pathname).toBe('/client-settings/rules')
  expect(saves).toHaveLength(0)
})

test('editing a default lazily creates an isolated copy and preserves native fields', async () => {
  activeSnapshot.templates[0] = { ...activeSnapshot.templates[0], is_default: true, is_system: true, content: '{"Name":"Happ","DirectSites":[],"GlobalProxy":"true","custom":{"preserve":true}}' }
  const { element, button } = await openPage('/client-settings/applications/happ')
  expect(button('Save')).toBeUndefined()
  const textarea = element.querySelector('textarea')!
  expect(textarea.closest('fieldset')?.getAttribute('disabled')).toBeNull()
  await act(async () => {
    Object.getOwnPropertyDescriptor(browser.HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, 'private.example')
    textarea.dispatchEvent(new browser.Event('input', { bubbles: true }))
  })
  await act(async () => button('Apply').click())
  await act(async () => button('Save').click())
  expect(saves).toHaveLength(1)
  expect(saves[0].template?.id).toBeUndefined()
  expect(saves[0].template?.is_default).toBe(false)
  expect(saves[0].bind_rule_indices).toEqual([0])
  expect(JSON.parse(saves[0].template!.content)).toMatchObject({ DirectSites: ['private.example'], custom: { preserve: true } })
  expect(activeSnapshot.templates[0].content).toContain('"DirectSites":[]')
})

test('secondary copy action copies pending edits and cancellation restores the assigned document', async () => {
  const { element, button } = await openPage('/client-settings/applications/happ')
  const copy = button('Make a separate copy')
  expect(copy.closest('details')).not.toBeNull()
  await act(async () => copy.click())
  expect(button('Save')).toBeDefined()
  await act(async () => button('Cancel').click())
  expect(button('Save')).toBeUndefined()
  expect(saves).toHaveLength(0)
  const textarea = element.querySelector('textarea')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(browser.HTMLTextAreaElement.prototype, 'value')!.set!.call(textarea, 'copy.example')
    textarea.dispatchEvent(new browser.Event('input', { bubbles: true }))
  })
  expect(copy.disabled).toBe(true)
  await act(async () => button('Apply').click())
  await act(async () => button('Make a separate copy').click())
  await act(async () => button('Save').click())
  expect(saves[0].template?.id).toBeUndefined()
  expect(JSON.parse(saves[0].template!.content).DirectSites).toEqual(['copy.example'])
})

test('delivery-only edits are immediately available and reverting the expression clears the draft guard', async () => {
  const { element, button } = await openPage('/client-settings/applications/happ')
  await act(async () => button('Subscription delivery').click())
  expect(button('Save')).toBeUndefined()
  const label = [...element.querySelectorAll('label')].find(item => item.textContent?.includes('User-Agent expression'))!
  const input = label.querySelector('input')!
  const setter = Object.getOwnPropertyDescriptor(browser.HTMLInputElement.prototype, 'value')!.set!
  const setExpression = async (value: string) =>
    act(async () => {
      setter.call(input, value)
      input.dispatchEvent(new browser.Event('input', { bubbles: true }))
    })
  await setExpression('^Happ/2')
  expect(button('Save').disabled).toBe(false)
  await setExpression('^Happ')
  expect(button('Save')).toBeUndefined()
  await setExpression('^Happ/3')
  await act(async () => button('Save').click())
  expect(saves[0].template).toBeUndefined()
  expect(saves[0].rules[0].pattern).toBe('^Happ/3')
  expect(saves[0].rules[0].happ_routing?.template_id).toBe(2)
})

test('section controls stay above delivery fields and app context removes duplicate assignment controls', async () => {
  const { element, router, button } = await openPage('/client-settings/applications/happ')
  const sectionControls = button('Routing').parentElement!.parentElement!
  expect(sectionControls.parentElement!.firstElementChild).toBe(sectionControls)
  await act(async () => button('Subscription delivery').click())
  expect(button('Routing').parentElement!.parentElement).toBe(sectionControls)
  expect(sectionControls.parentElement!.firstElementChild).toBe(sectionControls)
  expect(button('Subscription delivery').getAttribute('aria-pressed')).toBe('true')
  const labels = [...element.querySelectorAll('label')].map(item => item.querySelector('span')?.textContent ?? item.firstChild?.textContent?.trim())
  expect(labels.filter(text => text === 'Configuration')).toHaveLength(1)
  expect(labels).toContain('Response format')
  expect(labels).not.toContain('Application')
  expect(element.textContent).not.toContain('Use an existing configuration')
  expect(element.textContent).not.toContain('The application label organizes rules')
  expect(element.textContent).toContain('Configuration mode')
  await act(async () => router.navigate('/client-settings/rules'))
  expect([...element.querySelectorAll('label span')].some(item => item.textContent === 'Application')).toBe(true)
  expect(element.textContent).toContain('The application label organizes rules')
  expect(button('Save')).toBeUndefined()
})

test('single-mode applications omit the mode selector and retain response and configuration choices', async () => {
  activeSnapshot.templates.push({ id: 4, name: 'Xray separate', template_type: 'xray_subscription', content: '{"outbounds":[]}', is_default: false, is_system: false })
  activeSnapshot.subscription.rules.push({ pattern: '^Xray', target: 'xray', ui_application: 'xray', template_id: 4 })
  const { element, button } = await openPage('/client-settings/applications/xray')
  await act(async () => button('Subscription delivery').click())
  expect(element.textContent).not.toContain('Configuration mode')
  expect(element.textContent).not.toContain('Use an existing configuration')
  const labels = [...element.querySelectorAll('label span')].map(item => item.textContent)
  expect(labels).toContain('Configuration')
  expect(labels).toContain('Response format')
  expect(button('Save')).toBeUndefined()
})

test('User-Agent defaults remain editable as code in the configuration library', async () => {
  const { element, button } = await openPage('/client-settings/configurations/3')
  expect(button('Routing')).toBeUndefined()
  expect(button('Save')).toBeUndefined()
  const code = element.querySelector<import('happy-dom').HTMLTextAreaElement>('[data-testid="source-code"]')!
  expect(code.value).toBe('{"list":["Mozilla/5.0"]}')
  const defaults = element.querySelector<import('happy-dom').HTMLInputElement>('input[type="checkbox"]')!
  expect(defaults.checked).toBe(true)
  await act(async () => {
    Object.getOwnPropertyDescriptor(browser.HTMLTextAreaElement.prototype, 'value')!.set!.call(code, '{"list":["Mozilla/5.0","ExampleClient/1.0"]}')
    code.dispatchEvent(new browser.Event('input', { bubbles: true }))
  })
  await act(async () => button('Save').click())
  expect(saves[0].template).toMatchObject({ id: 3, template_type: 'user_agent', is_default: true })
  expect(JSON.parse(saves[0].template!.content).list).toContain('ExampleClient/1.0')
})

import { afterEach, expect, test } from 'bun:test'
import { Window } from 'happy-dom'
import type { NativeFormat, NativeSection } from '../forms/native-configuration'

const browser = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window: browser,
  document: browser.document,
  navigator: browser.navigator,
  HTMLElement: browser.HTMLElement,
  HTMLInputElement: browser.HTMLInputElement,
  HTMLTextAreaElement: browser.HTMLTextAreaElement,
  Event: browser.Event,
  IS_REACT_ACT_ENVIRONMENT: true,
})
const { createElement, act } = await import('react')
const { createRoot } = await import('react-dom/client')
const { NativeConfigurationEditor } = await import('./native-configuration-editor')
const { default: i18n } = await import('i18next')
await i18n.init({ lng: 'en', resources: {} })
let root: ReturnType<typeof createRoot> | null = null
afterEach(async () => {
  await act(async () => root?.unmount())
  browser.document.body.innerHTML = ''
  root = null
})

test('typing a routing draft retains the focused textarea and only Apply serializes', async () => {
  const element = browser.document.createElement('div')
  browser.document.body.append(element)
  const writes: string[] = [],
    validity: boolean[] = [],
    dirty: boolean[] = []
  root = createRoot(element as unknown as HTMLElement)
  await act(async () =>
    root!.render(
      createElement(NativeConfigurationEditor, {
        format: 'xray',
        section: 'routing',
        content: '{"custom":{"preserved":true},"routing":{"rules":[]}}',
        onChange: value => writes.push(value),
        onValidityChange: value => validity.push(value),
        onDirtyChange: value => dirty.push(value),
      }),
    ),
  )
  const textarea = element.querySelector('textarea')!
  textarea.focus()
  const setter = Object.getOwnPropertyDescriptor(browser.HTMLTextAreaElement.prototype, 'value')!.set!
  for (const value of ['e', 'ex', 'example.com'])
    await act(async () => {
      setter.call(textarea, value)
      textarea.dispatchEvent(new browser.Event('input', { bubbles: true }))
    })
  expect(element.querySelector('textarea')).toBe(textarea)
  expect(browser.document.activeElement).toBe(textarea)
  expect(textarea.value).toBe('example.com')
  expect(writes).toHaveLength(0)
  expect(validity[validity.length - 1]).toBe(false)
  expect(dirty[dirty.length - 1]).toBe(true)
  const add = [...element.querySelectorAll('button')].find(button => button.textContent === 'Add')!
  expect(add.disabled).toBe(false)
  await act(async () => add.click())
  expect(writes).toHaveLength(1)
  expect(dirty[dirty.length - 1]).toBe(false)
  expect(JSON.parse(writes[0])).toEqual({ custom: { preserved: true }, routing: { rules: [{ type: 'field', domain: ['full:example.com'], outboundTag: 'proxy' }] } })
})

test('Happ Name remains separate and draft list input does not rewrite it', async () => {
  const element = browser.document.createElement('div')
  browser.document.body.append(element)
  const writes: string[] = []
  root = createRoot(element as unknown as HTMLElement)
  await act(async () =>
    root!.render(
      createElement(NativeConfigurationEditor, { format: 'happ', section: 'routing', content: '{"Name":"Keep name","DirectSites":[],"GlobalProxy":"true"}', onChange: value => writes.push(value) }),
    ),
  )
  const textarea = element.querySelector('textarea')!
  const setter = Object.getOwnPropertyDescriptor(browser.HTMLTextAreaElement.prototype, 'value')!.set!
  await act(async () => {
    setter.call(textarea, 'example.com\nsecond.example')
    textarea.dispatchEvent(new browser.Event('input', { bubbles: true }))
  })
  expect(writes).toHaveLength(0)
  const apply = [...element.querySelectorAll('button')].find(button => button.textContent === 'Apply')!
  await act(async () => apply.click())
  expect(JSON.parse(writes[0])).toEqual({ Name: 'Keep name', DirectSites: ['example.com', 'second.example'], GlobalProxy: 'true' })
})

async function mountNative(format: NativeFormat, section: NativeSection, content: string, failWrite = false) {
  const element = browser.document.createElement('div')
  browser.document.body.append(element)
  const writes: string[] = []
  root = createRoot(element as unknown as HTMLElement)
  await act(async () =>
    root!.render(
      createElement(NativeConfigurationEditor, {
        format,
        section,
        content,
        onChange: value => {
          if (failWrite) throw new Error('write rejected')
          writes.push(value)
        },
      }),
    ),
  )
  return { element, writes }
}
type TestElement = ReturnType<typeof browser.document.createElement>
async function typeValue(element: TestElement, value: string) {
  const prototype = element.tagName === 'TEXTAREA' ? browser.HTMLTextAreaElement.prototype : browser.HTMLInputElement.prototype
  await act(async () => {
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(element, value)
    element.dispatchEvent(new browser.Event('input', { bubbles: true }))
  })
}
function button(element: TestElement, text: string) {
  return [...element.querySelectorAll('button')].find(item => item.textContent === text)!
}

test('sing-box Block action and a real outbound named reject stay distinct in the DOM', async () => {
  const { element, writes } = await mountNative('sing_box', 'routing', '{"outbounds":[{"tag":"reject","type":"direct"}],"route":{"rules":[]}}')
  const select = element.querySelectorAll('select')[1]
  const options = [...select.querySelectorAll('option')]
  expect(options).toHaveLength(2)
  expect(new Set(options.map(option => option.value)).size).toBe(2)
  const block = options.find(option => option.textContent === 'Block')!
  await act(async () => {
    select.value = block.value
    select.dispatchEvent(new browser.Event('change', { bubbles: true }))
  })
  await typeValue(element.querySelector('textarea')!, 'blocked.example')
  await act(async () => button(element, 'Add').click())
  expect(JSON.parse(writes[0]).route.rules).toEqual([{ domain: ['blocked.example'], action: 'reject' }])
  await typeValue(element.querySelector('textarea')!, 'direct.example')
  await act(async () => button(element, 'Add').click())
  expect(JSON.parse(writes[1]).route.rules).toEqual([{ domain: ['direct.example'], outbound: 'reject' }])
})

test('an existing simple sing-box reject rule is visually editable as an action', async () => {
  const { element, writes } = await mountNative('sing_box', 'routing', '{"outbounds":[],"route":{"rules":[{"domain":["old.example"],"action":"reject"}]}}')
  await act(async () => button(element, 'Edit').click())
  await typeValue(element.querySelector('textarea')!, 'new.example')
  await act(async () => button(element, 'Apply').click())
  expect(JSON.parse(writes[0]).route.rules).toEqual([{ domain: ['new.example'], action: 'reject' }])
})

test('new Clash rule is inserted before MATCH, preserving the fallback source', async () => {
  const { element, writes } = await mountNative('clash', 'routing', 'proxy-groups:\n  - name: PROXY\n    type: select\n    proxies: [DIRECT]\nrules:\n  - MATCH,PROXY # fallback\n')
  await typeValue(element.querySelector('textarea')!, 'example.com')
  await act(async () => button(element, 'Add').click())
  expect(writes[0]).toContain('  - "DOMAIN,example.com,DIRECT"\n  - MATCH,PROXY # fallback\n')
})

test('referenced sing-box DNS servers cannot be removed or renamed visually', async () => {
  const content = JSON.stringify({
    dns: {
      servers: [
        { type: 'udp', tag: 'used', server: '1.1.1.1' },
        { type: 'udp', tag: 'unused', server: '8.8.8.8' },
      ],
      rules: [{ type: 'logical', rules: [{ server: 'used' }] }],
    },
  })
  const { element, writes } = await mountNative('sing_box', 'dns', content)
  const remove = [...element.querySelectorAll('button')].filter(item => item.textContent === 'Remove')
  expect(remove[0].disabled).toBe(true)
  expect(remove[1].disabled).toBe(false)
  expect(element.textContent).toContain('Update those references in code')
  await act(async () => remove[0].click())
  expect(writes).toHaveLength(0)
  await act(async () => button(element, 'Edit').click())
  const id = [...element.querySelectorAll('input')].find(input => input.value === 'used')!
  expect(id.disabled).toBe(true)
  const address = [...element.querySelectorAll('input')].find(input => input.value === '1.1.1.1')!
  await typeValue(address, '9.9.9.9')
  await act(async () => button(element, 'Apply').click())
  expect(JSON.parse(writes[0]).dns.servers[0]).toEqual({ type: 'udp', tag: 'used', server: '9.9.9.9' })
  expect(JSON.parse(writes[0]).dns.rules).toEqual(JSON.parse(content).dns.rules)
})

test('routing draft survives a failed write', async () => {
  const { element, writes } = await mountNative('xray', 'routing', '{"routing":{"rules":[]}}', true)
  await typeValue(element.querySelector('textarea')!, 'keep.example')
  await act(async () => button(element, 'Add').click())
  expect(writes).toHaveLength(0)
  expect(element.querySelector('textarea')!.value).toBe('keep.example')
  expect(element.textContent).toContain('Your source has not changed.')
})

test('DNS server draft survives a failed write', async () => {
  const { element, writes } = await mountNative('xray', 'dns', '{"dns":{"servers":[]}}', true)
  await typeValue(element.querySelector('input')!, '1.1.1.1')
  await act(async () => button(element, 'Add').click())
  expect(writes).toHaveLength(0)
  expect(element.querySelector('input')!.value).toBe('1.1.1.1')
  expect(element.textContent).toContain('Your source has not changed.')
})

import { describe, expect, it } from 'bun:test'
import en from '../../../../public/statics/locales/en.json'
import fa from '../../../../public/statics/locales/fa.json'
import ru from '../../../../public/statics/locales/ru.json'
import zh from '../../../../public/statics/locales/zh.json'
import hostModalSource from '../../hosts/dialogs/host-modal.tsx' with { type: 'text' }
import ruleSheetSource from '../../subscriptions/components/subscription-rule-advanced-sheet.tsx' with { type: 'text' }
import editorSource from './subscription-profile-editor.tsx' with { type: 'text' }

const LOCALES: Record<string, Record<string, unknown>> = { en, ru, fa, zh }

function at(translations: Record<string, unknown>, path: string[]): Record<string, string> {
  let node: unknown = translations
  for (const segment of path) {
    if (!node || typeof node !== 'object') return {}
    node = (node as Record<string, unknown>)[segment]
  }
  return (node ?? {}) as Record<string, string>
}

// Every t() call in these components passes a defaultValue, so a missing key is
// not a crash -- the operator silently reads English. That is how fa and zh ended
// up without a whole section, which no amount of manual clicking surfaces.
interface Surface {
  name: string
  source: string
  /** Matches a whole quoted key, capturing its name relative to `path`. */
  pattern: RegExp
  path: string[]
  /** Keys the regex cannot see, e.g. built by interpolation. */
  extra?: string[]
  /** Only where the locale object belongs entirely to this one component. */
  exhaustive?: boolean
  atLeast: number
}

const SURFACES: Surface[] = [
  {
    name: 'the profile editor',
    source: editorSource,
    pattern: /'clientTemplates\.profile\.([a-zA-Z0-9]+)'/g,
    path: ['clientTemplates', 'profile'],
    // `${field}` interpolates the three health-check duration inputs.
    extra: ['interval', 'tolerance', 'timeout'],
    // Raw JSON still accepts advanced fields whose translations predate the
    // intentionally narrow server-group form, so those strings may remain.
    exhaustive: false,
    atLeast: 20,
  },
  {
    name: "the host dialog's profile classification",
    source: hostModalSource,
    pattern: /'hostsDialog\.(profile[a-zA-Z0-9]*)'/g,
    // `hostsDialog` also holds keys from the rest of the dialog, some with
    // pre-existing gaps, so only the ones matched here are asserted.
    path: ['hostsDialog'],
    atLeast: 8,
  },
  {
    name: "the subscription rule's profile picker",
    source: ruleSheetSource,
    pattern: /'settings\.subscriptions\.rules\.(profile[a-zA-Z0-9]*)'/g,
    path: ['settings', 'subscriptions', 'rules'],
    atLeast: 4,
  },
]

function keysAskedFor(surface: Surface): string[] {
  const quoted = [...surface.source.matchAll(surface.pattern)].map(match => match[1])
  return [...new Set([...quoted, ...(surface.extra ?? [])])]
}

describe('subscription profile locales', () => {
  for (const surface of SURFACES) {
    describe(surface.name, () => {
      it('asks for a plausible number of keys', () => {
        // Guards the extraction itself: a refactor to computed keys would quietly
        // empty this list and make every assertion below pass for the wrong reason.
        expect(keysAskedFor(surface).length).toBeGreaterThanOrEqual(surface.atLeast)
      })

      for (const [locale, translations] of Object.entries(LOCALES)) {
        it(`is translated into ${locale}`, () => {
          const strings = at(translations, surface.path)
          const missing = keysAskedFor(surface).filter(key => strings[key] === undefined)
          expect(missing).toEqual([])
        })
      }

      if (surface.exhaustive) {
        it('carries no key the component stopped asking for', () => {
          // A stale key is not harmful, but it does send the next translator to
          // work on strings nobody reads.
          const asked = new Set(keysAskedFor(surface))
          for (const [locale, translations] of Object.entries(LOCALES)) {
            const stale = Object.keys(at(translations, surface.path)).filter(key => !asked.has(key))
            expect({ locale, stale }).toEqual({ locale, stale: [] })
          }
        })
      }
    })
  }
})

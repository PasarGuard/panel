import type { TFunction } from 'i18next'

type HtmlTranslationOptions = Record<string, unknown> & { defaultValue?: string; interpolation?: Record<string, unknown> }

/**
 * Translates a string that is rendered with dangerouslySetInnerHTML (it may hold markup such as <b>).
 * i18n runs with escapeValue: false, so the interpolated values (names that other admins can set)
 * are escaped here; otherwise a name like `<img onerror=...>` would run in the viewer's session.
 */
export function translateHtml(t: TFunction, key: string, options: HtmlTranslationOptions = {}): string {
  return t(key, { ...options, interpolation: { ...options.interpolation, escapeValue: true } })
}

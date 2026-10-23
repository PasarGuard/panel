import { zodResolver } from '@hookform/resolvers/zod'
import type { TFunction } from 'i18next'
import type { Resolver } from 'react-hook-form'
import type { ClientProfileCreate, ClientProfileResponse, ClientProfileSettings, ClientProfileTemplateType } from '@/service/api'
import { builtInVariableKeys } from '@/features/subscriptions/components/subscription-settings-schema'
import { z } from 'zod'

// Same token rule as the backend (`_HTTP_HEADER_NAME_PATTERN` in app/models/client_profile.py)
const HTTP_HEADER_NAME_PATTERN = /^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/
const CUSTOM_VARIABLE_KEY_PATTERN = /^[A-Z][A-Z0-9_]*$/

export const CLIENT_PROFILE_TEMPLATE_TYPES = ['xray_subscription', 'singbox_subscription', 'clash_subscription'] as const satisfies readonly ClientProfileTemplateType[]

/** Select value for "use the default template of this type" (the key is left out of `templates`). */
export const DEFAULT_TEMPLATE_VALUE = 'default'

export type RandomizeOrderMode = 'inherit' | 'on' | 'off'

const keyValueRowSchema = z.object({ key: z.string(), value: z.string() })

export const clientProfileFormSchema = z
  .object({
    name: z.string().trim().min(1, 'validation.required').max(64),
    note: z.string().max(500),
    templates: z.object({
      xray_subscription: z.string(),
      singbox_subscription: z.string(),
      clash_subscription: z.string(),
    }),
    profile_title: z.string().max(256),
    support_url: z.string().max(512),
    announce: z.string().max(128),
    announce_url: z.string().max(512),
    update_interval: z.string().regex(/^\s*(\d*)\s*$/, 'clientProfiles.validation.wholeNumber'),
    randomize_order: z.enum(['inherit', 'on', 'off']),
    response_headers: z.array(keyValueRowSchema),
    remove_response_headers: z.array(z.string()),
    custom_variables: z.array(keyValueRowSchema),
  })
  .superRefine((values, ctx) => {
    const interval = values.update_interval.trim()
    if (interval && Number(interval) < 1) {
      ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'clientProfiles.validation.wholeNumber', path: ['update_interval'] })
    }

    const seenHeaders = new Set<string>()
    values.response_headers.forEach((row, index) => {
      const key = row.key.trim()
      if (!key && !row.value.trim()) return
      if (!HTTP_HEADER_NAME_PATTERN.test(key)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'clientProfiles.validation.headerName', path: ['response_headers', index, 'key'] })
        return
      }
      if (seenHeaders.has(key.toLowerCase())) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'clientProfiles.validation.duplicateHeader', path: ['response_headers', index, 'key'] })
      }
      seenHeaders.add(key.toLowerCase())
      if (/[\r\n\0]/.test(row.value)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'clientProfiles.validation.headerValue', path: ['response_headers', index, 'value'] })
      }
    })

    values.remove_response_headers.forEach((name, index) => {
      if (!HTTP_HEADER_NAME_PATTERN.test(name.trim())) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'clientProfiles.validation.headerName', path: ['remove_response_headers', index] })
      }
    })

    const seenVariables = new Set<string>()
    values.custom_variables.forEach((variable, index) => {
      const key = variable.key.trim()
      if (!key && !variable.value.trim()) return
      const path = ['custom_variables', index, 'key']
      if (!CUSTOM_VARIABLE_KEY_PATTERN.test(key) || key.length > 64) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'clientProfiles.validation.variableKey', path })
      } else if ((builtInVariableKeys as readonly string[]).includes(key)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'clientProfiles.validation.variableBuiltin', path })
      } else if (seenVariables.has(key)) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'clientProfiles.validation.variableDuplicate', path })
      }
      seenVariables.add(key)
      if (variable.value.length > 512) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, message: 'clientProfiles.validation.variableValue', path: ['custom_variables', index, 'value'] })
      }
    })
  })

export type ClientProfileFormValues = z.infer<typeof clientProfileFormSchema>

const translateErrorMessages = (node: unknown, t: TFunction): void => {
  if (!node || typeof node !== 'object') return
  const record = node as Record<string, unknown>
  if (typeof record.message === 'string' && (record.message.startsWith('clientProfiles.') || record.message.startsWith('validation.'))) {
    record.message = t(record.message, { field: t('name', { defaultValue: 'Name' }) })
  }
  for (const [key, value] of Object.entries(record)) {
    if (key !== 'ref') translateErrorMessages(value, t)
  }
}

/** zodResolver whose i18n-key messages are translated (FormMessage prints messages as is). */
export function createClientProfileFormResolver(t: TFunction): Resolver<ClientProfileFormValues> {
  const base = zodResolver(clientProfileFormSchema)
  return async (values, context, options) => {
    const result = await base(values, context, options)
    if (result.errors) translateErrorMessages(result.errors, t)
    return result as Awaited<ReturnType<Resolver<ClientProfileFormValues>>>
  }
}

export const clientProfileFormDefaultValues: ClientProfileFormValues = {
  name: '',
  note: '',
  templates: {
    xray_subscription: DEFAULT_TEMPLATE_VALUE,
    singbox_subscription: DEFAULT_TEMPLATE_VALUE,
    clash_subscription: DEFAULT_TEMPLATE_VALUE,
  },
  profile_title: '',
  support_url: '',
  announce: '',
  announce_url: '',
  update_interval: '',
  randomize_order: 'inherit',
  response_headers: [],
  remove_response_headers: [],
  custom_variables: [],
}

const textOrNull = (value: string) => (value.trim() ? value.trim() : null)

const randomizeToApi = (mode: RandomizeOrderMode): boolean | null => (mode === 'on' ? true : mode === 'off' ? false : null)

const randomizeFromApi = (value: boolean | null | undefined): RandomizeOrderMode => (value === true ? 'on' : value === false ? 'off' : 'inherit')

/** API profile -> form values. Missing/null settings become empty inputs (= inherit). */
export const clientProfileToFormValues = (profile?: Pick<ClientProfileResponse, 'name' | 'note' | 'templates' | 'settings'> | null): ClientProfileFormValues => {
  if (!profile) return structuredClone(clientProfileFormDefaultValues)
  const templates = profile.templates ?? {}
  const settings: ClientProfileSettings = profile.settings ?? {}

  return {
    name: profile.name ?? '',
    note: profile.note ?? '',
    templates: {
      xray_subscription: templates.xray_subscription != null ? String(templates.xray_subscription) : DEFAULT_TEMPLATE_VALUE,
      singbox_subscription: templates.singbox_subscription != null ? String(templates.singbox_subscription) : DEFAULT_TEMPLATE_VALUE,
      clash_subscription: templates.clash_subscription != null ? String(templates.clash_subscription) : DEFAULT_TEMPLATE_VALUE,
    },
    profile_title: settings.profile_title ?? '',
    support_url: settings.support_url ?? '',
    announce: settings.announce ?? '',
    announce_url: settings.announce_url ?? '',
    update_interval: settings.update_interval != null ? String(settings.update_interval) : '',
    randomize_order: randomizeFromApi(settings.randomize_order),
    response_headers: Object.entries(settings.response_headers ?? {}).map(([key, value]) => ({ key, value: value ?? '' })),
    remove_response_headers: [...(settings.remove_response_headers ?? [])],
    custom_variables: (settings.custom_variables ?? []).map(variable => ({ key: variable.key ?? '', value: variable.value ?? '' })),
  }
}

/** Form values -> create/modify payload. Empty inputs are sent as null (= inherit), blank rows are dropped. */
export const clientProfileFormToPayload = (values: ClientProfileFormValues): ClientProfileCreate => {
  const templates: NonNullable<ClientProfileCreate['templates']> = {}
  for (const type of CLIENT_PROFILE_TEMPLATE_TYPES) {
    const raw = values.templates[type]
    const id = Number(raw)
    if (raw && raw !== DEFAULT_TEMPLATE_VALUE && Number.isInteger(id) && id > 0) {
      templates[type] = id
    }
  }

  const responseHeaders: Record<string, string> = {}
  for (const row of values.response_headers) {
    const key = row.key.trim()
    if (!key) continue
    responseHeaders[key] = row.value
  }

  const removeHeaders: string[] = []
  const seenRemoved = new Set<string>()
  for (const name of values.remove_response_headers) {
    const trimmed = name.trim()
    if (!trimmed || seenRemoved.has(trimmed.toLowerCase())) continue
    seenRemoved.add(trimmed.toLowerCase())
    removeHeaders.push(trimmed)
  }

  const interval = values.update_interval.trim()

  return {
    name: values.name.trim(),
    note: textOrNull(values.note),
    templates,
    settings: {
      profile_title: textOrNull(values.profile_title),
      support_url: textOrNull(values.support_url),
      announce: textOrNull(values.announce),
      announce_url: textOrNull(values.announce_url),
      update_interval: interval ? Number(interval) : null,
      randomize_order: randomizeToApi(values.randomize_order),
      response_headers: responseHeaders,
      remove_response_headers: removeHeaders,
      custom_variables: values.custom_variables.filter(variable => variable.key.trim() || variable.value.trim()).map(variable => ({ key: variable.key.trim(), value: variable.value })),
    },
  }
}

/**
 * Profile ids to call `DELETE /client_profile/{id}/users` on so that every selected user ends up without a profile.
 * Users we have loaded tell us their profile; if some selected users are not loaded (other page), we cannot know
 * theirs and fall back to every known profile.
 */
export const profileIdsToDetach = (selectedUserIds: readonly number[], loadedUsers: ReadonlyArray<{ id: number; client_profile_id?: number | null }>, allProfileIds: readonly number[]): number[] => {
  const loadedById = new Map(loadedUsers.map(user => [user.id, user]))
  const hasUnknown = selectedUserIds.some(id => !loadedById.has(id))
  if (hasUnknown) return [...new Set(allProfileIds)]
  const ids = new Set<number>()
  for (const id of selectedUserIds) {
    const profileId = loadedById.get(id)?.client_profile_id
    if (profileId != null) ids.add(profileId)
  }
  return [...ids]
}

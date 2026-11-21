import { z } from 'zod'

export const coreBackendTypes = ['xray', 'wg', 'mtproto', 'singbox'] as const
export type CoreBackendType = (typeof coreBackendTypes)[number]

export const coreConfigFormSchema = z.object({
  name: z.string().trim().min(1, 'Core name is required'),
  type: z.enum(coreBackendTypes).optional(),
  config: z.string().min(1, 'Configuration is required'),
  fallback_id: z.array(z.string()).optional(),
  excluded_inbound_ids: z.array(z.string()).optional(),
  public_key: z.string().optional(),
  private_key: z.string().optional(),
  restart_nodes: z.boolean().optional(),
  note: z.string().max(500, 'Note must be 500 characters or fewer').optional(),
})

export type CoreConfigFormValues = z.infer<typeof coreConfigFormSchema>

export const coreConfigFormDefaultValues: Partial<CoreConfigFormValues> = {
  name: '',
  type: 'xray',
  config: JSON.stringify({}, null, 2),
  fallback_id: [],
  excluded_inbound_ids: [],
  restart_nodes: true,
  note: '',
}

// Compare configs by content, not by JSON formatting; unparsable text compares as typed
const normalizeConfig = (config?: string) => {
  try {
    return JSON.stringify(JSON.parse(config || '{}'))
  } catch {
    return config ?? ''
  }
}

const sameTags = (a?: string[], b?: string[]) => {
  const left = [...(a ?? [])].sort()
  const right = [...(b ?? [])].sort()
  return left.length === right.length && left.every((tag, i) => tag === right[i])
}

/** Only the panel-only note differs from the saved core, so there is nothing to sync to nodes. */
export function isNoteOnlyCoreEdit(saved: Partial<CoreConfigFormValues> | undefined, current: Partial<CoreConfigFormValues>): boolean {
  if (!saved) return false
  if ((saved.note ?? '').trim() === (current.note ?? '').trim()) return false
  return (
    (saved.name ?? '').trim() === (current.name ?? '').trim() &&
    (saved.type ?? 'xray') === (current.type ?? 'xray') &&
    normalizeConfig(saved.config) === normalizeConfig(current.config) &&
    sameTags(saved.fallback_id, current.fallback_id) &&
    sameTags(saved.excluded_inbound_ids, current.excluded_inbound_ids)
  )
}

/**
 * Turn a plugin's JSON Schema (object with properties) into simple form fields.
 * Supported: string, number, integer, boolean, enum, array of strings. Anything else is edited as JSON.
 */

export type JsonSchema = {
  type?: string | string[]
  title?: string
  description?: string
  enum?: unknown[]
  default?: unknown
  minimum?: number
  maximum?: number
  items?: JsonSchema
  properties?: Record<string, JsonSchema>
  required?: string[]
}

export type PluginFieldKind = 'string' | 'number' | 'integer' | 'boolean' | 'enum' | 'string-array' | 'json'

export interface PluginField {
  name: string
  kind: PluginFieldKind
  label: string
  description?: string
  required: boolean
  options?: string[]
  minimum?: number
  maximum?: number
}

/** Form state: strings for text-like inputs, booleans for switches. */
export type PluginFormValues = Record<string, string | boolean>

const mainType = (schema: JsonSchema): string | undefined => {
  if (Array.isArray(schema.type)) return schema.type.find(type => type !== 'null')
  return schema.type
}

export function fieldKind(schema: JsonSchema): PluginFieldKind {
  if (Array.isArray(schema.enum) && schema.enum.length > 0 && schema.enum.every(value => typeof value === 'string')) return 'enum'
  const type = mainType(schema)
  if (type === 'string' || type === 'number' || type === 'integer' || type === 'boolean') return type
  if (type === 'array' && schema.items && mainType(schema.items) === 'string' && !schema.items.enum) return 'string-array'
  return 'json'
}

export function schemaFields(schema: JsonSchema | null | undefined): PluginField[] {
  const properties = schema?.properties ?? {}
  const required = new Set(schema?.required ?? [])
  return Object.entries(properties).map(([name, property]) => ({
    name,
    kind: fieldKind(property ?? {}),
    label: property?.title || name,
    description: property?.description,
    required: required.has(name),
    options: Array.isArray(property?.enum) ? property.enum.map(String) : undefined,
    minimum: property?.minimum,
    maximum: property?.maximum,
  }))
}

export function toFormValues(fields: PluginField[], settings: Record<string, unknown>): PluginFormValues {
  const values: PluginFormValues = {}
  for (const field of fields) {
    const value = settings[field.name]
    switch (field.kind) {
      case 'boolean':
        values[field.name] = value === true
        break
      case 'string-array':
        values[field.name] = Array.isArray(value) ? value.map(String).join('\n') : ''
        break
      case 'json':
        values[field.name] = value === undefined ? '' : JSON.stringify(value, null, 2)
        break
      default:
        values[field.name] = value === undefined || value === null ? '' : String(value)
    }
  }
  return values
}

/**
 * Build the PUT body. Keys the form does not know (no schema property) are kept from `current`.
 * Returns field errors ('json' | 'number') for values that cannot be converted; the server validates the rest.
 */
export function fromFormValues(fields: PluginField[], values: PluginFormValues, current: Record<string, unknown> = {}): { data: Record<string, unknown>; errors: Record<string, 'json' | 'number'> } {
  const data: Record<string, unknown> = { ...current }
  const errors: Record<string, 'json' | 'number'> = {}
  for (const field of fields) {
    const raw = values[field.name]
    switch (field.kind) {
      case 'boolean':
        data[field.name] = raw === true
        break
      case 'number':
      case 'integer': {
        const text = String(raw ?? '').trim()
        if (text === '') {
          delete data[field.name]
          break
        }
        const parsed = Number(text)
        if (!Number.isFinite(parsed) || (field.kind === 'integer' && !Number.isInteger(parsed))) errors[field.name] = 'number'
        else data[field.name] = parsed
        break
      }
      case 'string-array':
        data[field.name] = String(raw ?? '')
          .split('\n')
          .map(item => item.trim())
          .filter(Boolean)
        break
      case 'json': {
        const text = String(raw ?? '').trim()
        if (text === '') {
          delete data[field.name]
          break
        }
        try {
          data[field.name] = JSON.parse(text)
        } catch {
          errors[field.name] = 'json'
        }
        break
      }
      default:
        data[field.name] = String(raw ?? '')
    }
  }
  return { data, errors }
}

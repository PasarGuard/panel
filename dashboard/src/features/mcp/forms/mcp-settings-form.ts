import { z } from 'zod'
import type { MCPSettingsResponse } from '@/service/api'

export const mcpSettingsSchema = z.object({
  enable: z.boolean().default(false),
  oauth: z.boolean().default(true),
  read_only: z.boolean().default(false),
  disabled_tools: z.array(z.string()).default([]),
})

export type McpSettingsFormInput = z.input<typeof mcpSettingsSchema>
export type McpSettingsFormValues = z.output<typeof mcpSettingsSchema>

export const mcpSettingsDefaultValues: McpSettingsFormValues = {
  enable: false,
  oauth: true,
  read_only: false,
  disabled_tools: [],
}

export const toMcpSettingsFormValues = (settings?: MCPSettingsResponse | null): McpSettingsFormValues => ({
  enable: settings?.enable ?? false,
  oauth: settings?.oauth ?? true,
  read_only: settings?.read_only ?? false,
  disabled_tools: settings?.disabled_tools ?? [],
})

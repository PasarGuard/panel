import { z } from 'zod'

export const coreConfigFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  config: z.string().min(1, 'Configuration is required'),
  fallback_id: z.array(z.string()).optional(),
  excluded_inbound_ids: z.array(z.string()).optional(),
  public_key: z.string().optional(),
  private_key: z.string().optional(),
  restart_nodes: z.boolean().optional(),
})

export type CoreConfigFormValues = z.infer<typeof coreConfigFormSchema>

export const coreConfigFormDefaultValues: Partial<CoreConfigFormValues> = {
  name: '',
  config: JSON.stringify({}, null, 2),
  fallback_id: [],
  excluded_inbound_ids: [],
  restart_nodes: true,
}

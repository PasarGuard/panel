import { DataLimitResetStrategy, NodeConnectionType } from '@/service/api'
import { z } from 'zod'

export const nodeFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  address: z.string().min(1, 'Address is required'),
  port: z.number().min(1, 'Port is required'),
  api_port: z.number().min(1).optional().nullable(),
  usage_coefficient: z.number().optional(),
  connection_type: z.enum([NodeConnectionType.grpc, NodeConnectionType.rest]),
  server_ca: z.string().min(1, 'Server CA is required'),
  keep_alive: z.number().min(0, 'Keep alive must be 0 or greater'),
  keep_alive_unit: z.enum(['seconds', 'minutes', 'hours']).default('seconds'),
  api_key: z.string().min(1, 'API key is required'),
  core_config_id: z.number().min(1, 'Core configuration is required'),
  data_limit: z.number().min(0).optional().nullable(),
  data_limit_reset_strategy: z.nativeEnum(DataLimitResetStrategy).optional().nullable(),
  reset_time: z.union([z.null(), z.undefined(), z.number().min(-1)]),
  default_timeout: z.number().min(3, 'Default timeout must be 3 or greater').max(60, 'Default timeout must be 60 or lower').optional(),
  internal_timeout: z.number().min(3, 'Internal timeout must be 3 or greater').max(60, 'Internal timeout must be 60 or lower').optional(),
})

export type NodeFormValues = z.input<typeof nodeFormSchema>

export const nodeFormDefaultValues: Partial<NodeFormValues> = {
  name: '',
  address: '',
  port: 62050,
  usage_coefficient: 1,
  connection_type: NodeConnectionType.grpc,
  server_ca: '',
  keep_alive: 20000,
  keep_alive_unit: 'seconds',
  api_key: '',
}

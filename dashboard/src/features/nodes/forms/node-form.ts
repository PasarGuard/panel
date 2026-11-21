import { DataLimitResetStrategy, NodeConnectionType } from '@/service/api'
import { z } from 'zod'

export const inferNodeVerification = (node: { server_ca?: string; certificate_sha256?: string | null }) =>
  node.certificate_sha256 ? ('fingerprint' as const) : node.server_ca?.trim() ? ('pem' as const) : ('trusted' as const)

export const nodeVerificationPayload = (values: Pick<NodeFormValues, 'verification' | 'server_ca' | 'certificate_sha256'>) => ({
  server_ca: values.verification === 'pem' ? values.server_ca.trim() : '',
  certificate_sha256: values.verification === 'fingerprint' ? values.certificate_sha256?.replace(/:/g, '').toLowerCase() : null,
})

export const nodeFormSchema = z
  .object({
    name: z.string().min(1, 'Name is required'),
    address: z.string().min(1, 'Address is required'),
    port: z.number().min(1, 'Port is required'),
    api_port: z.number().min(1).optional().nullable(),
    usage_coefficient: z.number().min(0, 'Usage ratio cannot be negative').optional(),
    connection_type: z.enum([NodeConnectionType.grpc, NodeConnectionType.rest]),
    verification: z.enum(['trusted', 'fingerprint', 'pem']),
    server_ca: z.string(),
    certificate_sha256: z.string().nullable().optional(),
    keep_alive: z.number().min(0, 'Keep alive must be 0 or greater'),
    keep_alive_unit: z.enum(['seconds', 'minutes', 'hours']).default('seconds'),
    api_key: z.string().min(1, 'API key is required'),
    core_config_id: z.number().min(1, 'Core configuration is required'),
    data_limit: z.number().min(0).optional().nullable(),
    data_limit_reset_strategy: z.nativeEnum(DataLimitResetStrategy).optional().nullable(),
    reset_time: z.union([z.null(), z.undefined(), z.number().min(-1)]),
    default_timeout: z.number().min(3, 'Default timeout must be 3 or greater').optional(),
    internal_timeout: z.number().min(3, 'Internal timeout must be 3 or greater').max(60, 'Internal timeout must be 60 or lower').optional(),
    proxy_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
    country_code: z.string().length(2).nullable().optional(),
    note: z.string().max(500, 'Note must be 500 characters or fewer').optional(),
  })
  .superRefine((values, ctx) => {
    if (values.verification === 'pem' && !values.server_ca.trim()) {
      ctx.addIssue({ code: 'custom', path: ['server_ca'], message: 'PEM certificate is required' })
    }
    if (values.verification === 'fingerprint' && !/^(?:[a-f\d]{64}|[a-f\d]{2}(?::[a-f\d]{2}){31})$/i.test(values.certificate_sha256 ?? '')) {
      ctx.addIssue({ code: 'custom', path: ['certificate_sha256'], message: 'Enter 64 hexadecimal characters or 32 colon-separated byte pairs' })
    }
  })

export type NodeFormValues = z.input<typeof nodeFormSchema>

export const nodeFormDefaultValues: Partial<NodeFormValues> = {
  name: '',
  address: '',
  port: 62050,
  usage_coefficient: 1,
  connection_type: NodeConnectionType.grpc,
  server_ca: '',
  certificate_sha256: null,
  verification: 'trusted',
  keep_alive: 20000,
  keep_alive_unit: 'seconds',
  api_key: '',
  proxy_url: '',
  country_code: null,
  note: '',
}

import { ClientTemplateType } from '@/service/api'
import { z } from 'zod'

export const clientTemplateFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(64),
  template_type: z.enum([
    ClientTemplateType.clash_subscription,
    ClientTemplateType.xray_subscription,
    ClientTemplateType.singbox_subscription,
    ClientTemplateType.user_agent,
    ClientTemplateType.grpc_user_agent,
  ]),
  content: z.string().min(1, 'Content is required'),
  is_default: z.boolean().optional(),
})

export type ClientTemplateFormValues = z.infer<typeof clientTemplateFormSchema>

export const clientTemplateFormDefaultValues: Partial<ClientTemplateFormValues> = {
  name: '',
  template_type: ClientTemplateType.clash_subscription,
  content: '',
  is_default: false,
}

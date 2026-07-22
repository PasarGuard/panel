import { NodeStatus } from '@/service/api'
import { z } from 'zod'

export const nodeAdvanceSearchFormSchema = z.object({
  status: z.array(z.nativeEnum(NodeStatus)).optional(),
  core_id: z.number().nullable().optional(),
})

export type NodeAdvanceSearchFormValue = z.infer<typeof nodeAdvanceSearchFormSchema>

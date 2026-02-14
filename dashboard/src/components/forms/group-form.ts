import { z } from 'zod'

export const groupFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  inbound_tags: z.array(z.string()),
  is_disabled: z.boolean().optional(),
})

export type GroupFormValues = z.infer<typeof groupFormSchema>

export const groupFormDefaultValues: Partial<GroupFormValues> = {
  name: '',
  inbound_tags: [],
  is_disabled: false,
}

import type { RoutingBalancer } from '@pasarguard/xray-config-kit'
import type { TFunction } from 'i18next'
import { z } from 'zod'

export type BalancerCommitInput = {
  tag: string
  selector: string[]
}

export function createBalancerCommitSchema(t: TFunction) {
  const tagLabel = t('coreEditor.field.tag', { defaultValue: 'Tag' })
  const selectorLabel = t('coreEditor.balancer.selector', { defaultValue: 'Selector (outbounds)' })

  const required = (fieldLabel: string) =>
    t('validation.required', { field: fieldLabel, defaultValue: `${fieldLabel} is required` })

  return z.object({
    tag: z.string().trim().min(1, required(tagLabel)),
    selector: z
      .array(z.string().trim().min(1))
      .min(
        1,
        t('coreEditor.balancer.validation.selectorMinOne', {
          defaultValue: `${selectorLabel}: choose at least one outbound tag (required by Xray).`,
        }),
      ),
  })
}

export function parseBalancerCommitInput(balancer: RoutingBalancer): BalancerCommitInput {
  const tag = String(balancer.tag ?? '').trim()
  const selector = (balancer.selector ?? [])
    .map(s => String(s).trim())
    .filter(s => s.length > 0)
  return { tag, selector }
}

export function validateBalancerForCommit(t: TFunction, balancer: RoutingBalancer) {
  return createBalancerCommitSchema(t).safeParse(parseBalancerCommitInput(balancer))
}

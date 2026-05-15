import type { Issue, RoutingRule } from '@pasarguard/xray-config-kit'
import { validateRoutingRuleDraft } from '@pasarguard/xray-config-kit'
import type { TFunction } from 'i18next'
import { z } from 'zod'
import { isValidXrayPortList } from '@/features/core-editor/kit/xray-port-list-validation'

export function createRoutingRuleDialogFormSchema(t: TFunction) {
  const portMessage = t('coreEditor.routing.validation.portRange', {
    defaultValue: 'Port must be a port number or list like 443, 1000-2000,444.',
  })
  const portList = z
    .string()
    .optional()
    .refine(value => value == null || value.trim() === '' || isValidXrayPortList(value), {
      message: portMessage,
    })

  return z
    .object({
      outboundTag: z.string().optional(),
      balancerTag: z.string().optional(),
      port: portList,
      sourcePort: portList,
      localPort: portList,
      vlessRoute: portList,
    })
    .passthrough()
    .superRefine((data, ctx) => {
      const outbound = typeof data.outboundTag === 'string' ? data.outboundTag.trim() : ''
      const balancer = typeof data.balancerTag === 'string' ? data.balancerTag.trim() : ''
      if (outbound || balancer) return
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['outboundTag'],
        message: t('coreEditor.routing.validation.requiresOutboundOrBalancer', {
          defaultValue: 'Set an outbound tag or a balancer tag so the rule knows where to send traffic.',
        }),
      })
    })
}

export function collectRoutingRuleDialogFormErrors(values: Record<string, string>, t: TFunction): Array<{ name: string; message: string }> {
  const parsed = createRoutingRuleDialogFormSchema(t).safeParse(values)
  if (parsed.success) return []
  return parsed.error.issues
    .map(issue => ({
      name: String(issue.path[0] ?? ''),
      message: issue.message,
    }))
    .filter(issue => issue.name !== '')
}

/**
 * Validates a routing rule before add / dialog done.
 * Combines xray-config-kit profile validation with editor semantics (target + tag references).
 */
export function collectRoutingRuleDialogIssues(
  rule: RoutingRule,
  ctx: {
    readonly outboundTags: readonly string[]
    readonly balancerTags: readonly string[]
    readonly t: TFunction
  },
): Issue[] {
  const issues: Issue[] = [...validateRoutingRuleDraft(rule)]

  const outbound = String(rule.outboundTag ?? '').trim()
  const balancer = String(rule.balancerTag ?? '').trim()

  if (!outbound && !balancer) {
    const dup = issues.some(
      i =>
        i.severity === 'error' &&
        (i.path === '/outboundTag' || i.path === '/balancerTag' || /outboundTag|balancerTag/i.test(i.path)),
    )
    if (!dup) {
      issues.push({
        code: 'routing.target.required',
        severity: 'error',
        category: 'semantic',
        path: '/outboundTag',
        message: ctx.t('coreEditor.routing.validation.requiresOutboundOrBalancer', {
          defaultValue: 'Set an outbound tag or a balancer tag so the rule knows where to send traffic.',
        }),
      })
    }
  }

  if (outbound && ctx.outboundTags.length > 0 && !ctx.outboundTags.includes(outbound)) {
    issues.push({
      code: 'routing.outbound.unknown',
      severity: 'error',
      category: 'semantic',
      path: '/outboundTag',
      message: ctx.t('coreEditor.routing.validation.unknownOutboundTag', {
        defaultValue: 'Outbound tag "{{tag}}" is not defined on this profile.',
        tag: outbound,
      }),
    })
  }

  if (balancer && ctx.balancerTags.length > 0 && !ctx.balancerTags.includes(balancer)) {
    issues.push({
      code: 'routing.balancer.unknown',
      severity: 'error',
      category: 'semantic',
      path: '/balancerTag',
      message: ctx.t('coreEditor.routing.validation.unknownBalancerTag', {
        defaultValue: 'Balancer tag "{{tag}}" is not defined under routing.balancers.',
        tag: balancer,
      }),
    })
  }

  return issues
}

export function routingRuleDialogHasBlockingErrors(issues: readonly Issue[]): boolean {
  return issues.some(i => i.severity === 'error')
}

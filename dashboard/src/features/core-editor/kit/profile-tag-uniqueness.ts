import type { Profile, RoutingRule } from '@pasarguard/xray-config-kit'
import type { TFunction } from 'i18next'

/** Which list entry is being edited so its current tag is not counted as a conflict with itself. */
export type ProfileTagIgnore = {
  owner: 'inbound' | 'outbound' | 'balancer' | 'routingRule'
  index: number
}

function normTag(raw: unknown): string {
  return String(raw ?? '').trim()
}

function routingRuleTag(rule: RoutingRule): string {
  return normTag((rule as Record<string, unknown>).tag)
}

/**
 * True if `candidateRaw` (trimmed) is already used as a tag on another inbound, outbound,
 * routing balancer, or routing rule `tag` (Xray expects these names not to collide).
 */
export function profileTagHasDuplicateUsage(
  profile: Profile,
  candidateRaw: string,
  ignore?: ProfileTagIgnore,
): boolean {
  const c = normTag(candidateRaw)
  if (c === '') return false

  const inbounds = profile.inbounds ?? []
  for (let i = 0; i < inbounds.length; i++) {
    if (ignore?.owner === 'inbound' && ignore.index === i) continue
    if (normTag(inbounds[i]?.tag) === c) return true
  }

  const outbounds = profile.outbounds ?? []
  for (let i = 0; i < outbounds.length; i++) {
    if (ignore?.owner === 'outbound' && ignore.index === i) continue
    if (normTag(outbounds[i]?.tag) === c) return true
  }

  const balancers = profile.routing?.balancers ?? []
  for (let i = 0; i < balancers.length; i++) {
    if (ignore?.owner === 'balancer' && ignore.index === i) continue
    if (normTag(balancers[i]?.tag) === c) return true
  }

  const rules = profile.routing?.rules ?? []
  for (let i = 0; i < rules.length; i++) {
    if (ignore?.owner === 'routingRule' && ignore.index === i) continue
    const r = rules[i]
    if (r && routingRuleTag(r) === c) return true
  }

  return false
}

export function profileDuplicateTagMessage(t: TFunction, tagValue: string): string {
  const tag = tagValue.trim()
  return t('coreEditor.validation.duplicateTagProfile', {
    tag,
    defaultValue: `Tag "${tag}" is already used by another inbound, outbound, routing balancer, or routing rule.`,
  })
}

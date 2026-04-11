import { ClientTemplateType, type ConfigFormat } from '@/service/api'

/** Mirrors backend `client_template_type_for_sub_rule_target`. */
export function clientTemplateTypeForRuleTarget(target: ConfigFormat): ClientTemplateType | null {
  switch (target) {
    case 'clash':
    case 'clash_meta':
      return ClientTemplateType.clash_subscription
    case 'sing_box':
      return ClientTemplateType.singbox_subscription
    case 'xray':
      return ClientTemplateType.xray_subscription
    case 'links':
    case 'links_base64':
      return ClientTemplateType.user_agent
    case 'outline':
    case 'wireguard':
    case 'block':
      return null
    default:
      return null
  }
}

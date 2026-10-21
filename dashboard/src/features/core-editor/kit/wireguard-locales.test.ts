import { defineLocaleKeySuite } from './locale-key-scan'

defineLocaleKeySuite('WireGuard', /^coreEditor\.(inbound|outbound)\.wireguard\./, ['coreEditor.inbound.wireguard.validation.secretKeyInvalid', 'coreEditor.outbound.wireguard.dnsNotList'])

import { defineLocaleKeySuite } from './locale-key-scan.test-support'

defineLocaleKeySuite('WireGuard', /^coreEditor\.(inbound|outbound)\.wireguard\./, ['coreEditor.inbound.wireguard.validation.secretKeyInvalid', 'coreEditor.outbound.wireguard.dnsNotList'])

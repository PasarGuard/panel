import { Cat, CircleOff, Code, GlobeLock, ListTree } from 'lucide-react'
import { WireguardIcon, XrayIcon, SingboxIcon, MihomoIcon } from '@/components/icons/format-icons'

export const configFormatOptions = [
  { value: 'links', label: 'settings.subscriptions.configFormats.links', icon: ListTree },
  { value: 'links_base64', label: 'settings.subscriptions.configFormats.links_base64', icon: Code },
  { value: 'xray', label: 'settings.subscriptions.configFormats.xray', icon: XrayIcon },
  { value: 'wireguard', label: 'settings.subscriptions.configFormats.wireguard', icon: WireguardIcon },
  { value: 'sing_box', label: 'settings.subscriptions.configFormats.sing_box', icon: SingboxIcon },
  { value: 'clash', label: 'settings.subscriptions.configFormats.clash', icon: Cat },
  { value: 'clash_meta', label: 'settings.subscriptions.configFormats.clash_meta', icon: MihomoIcon },
  { value: 'outline', label: 'settings.subscriptions.configFormats.outline', icon: GlobeLock },
  { value: 'block', label: 'settings.subscriptions.configFormats.block', icon: CircleOff },
]

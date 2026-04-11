import type { SubscriptionPlatform } from '@/components/subscriptions/subscription-settings-schema'

export interface DefaultCatalogApp {
  name: string
  logo?: string
  description?: string
  faDescription?: string
  ruDescription?: string
  zhDescription?: string
  configLink?: string
  downloadLink: string
}

export interface DefaultOperatingSystem {
  name: string
  apps: DefaultCatalogApp[]
}

const defaultApplicationsData: { operatingSystems: DefaultOperatingSystem[] } = {
  operatingSystems: [
    {
      name: 'iOS',
      apps: [
        {
          name: 'Streisand',
          logo: 'https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/1e/29/e0/1e29e04f-273b-9186-5f12-9bbe48c0fce2/AppIcon-0-0-1x_U007epad-0-0-0-1-0-85-220.png/460x0w.webp',
          description:
            'Flexible proxy client with rule-based setup, multiple protocols, and custom DNS. Supports VLESS(Reality), VMess, Trojan, Shadowsocks, Socks, SSH, Hysteria(V2), TUIC, Wireguard.',
          faDescription:
            'کلاینت پراکسی انعطاف‌پذیر با قوانین، پشتیبانی از پروتکل‌های متعدد و DNS سفارشی. پشتیبانی از VLESS(Reality)، VMess، Trojan، Shadowsocks، Socks، SSH، Hysteria(V2)، TUIC، WireGuard.',
          ruDescription:
            'Гибкий прокси‑клиент с правилами, поддержкой множества протоколов и кастомным DNS. Поддерживаются VLESS(Reality), VMess, Trojan, Shadowsocks, Socks, SSH, Hysteria(V2), TUIC, Wireguard.',
          zhDescription: '灵活的代理客户端，支持基于规则的配置、多种协议以及自定义 DNS。支持 VLESS(Reality)、VMess、Trojan、Shadowsocks、Socks、SSH、Hysteria(V2)、TUIC、Wireguard。',
          configLink: 'streisand://import/{url}',
          downloadLink: 'https://apps.apple.com/us/app/streisand/id6450534064',
        },
        {
          name: 'SingBox',
          logo: 'https://sing-box.sagernet.org/assets/icon.svg',
          description: 'A client that provides a platform for routing traffic securely.',
          faDescription: 'Sing-box یک کلاینت برای مسیریابی امن ترافیک فراهم می‌کند.',
          ruDescription: 'Клиент, обеспечивающий безопасную маршрутизацию трафика.',
          zhDescription: '提供安全流量路由的平台客户端。',
          configLink: 'sing-box://import-remote-profile?url={url}',
          downloadLink: 'https://apps.apple.com/us/app/sing-box-vt/id6673731168',
        },
        {
          name: 'Shadowrocket',
          logo: 'https://shadowlaunch.com/static/icon.png',
          description: 'A rule-based proxy utility client for iOS.',
          faDescription: 'Shadowrocket یک ابزار پروکسی قانون‌محور برای iOS است.',
          ruDescription: 'Прокси‑клиент для iOS с маршрутизацией по правилам.',
          zhDescription: '基于规则的 iOS 代理工具客户端。',
          downloadLink: 'https://apps.apple.com/us/app/shadowrocket/id932747118',
        },
      ],
    },
    {
      name: 'Android',
      apps: [
        {
          name: 'V2rayNG',
          logo: 'https://raw.githubusercontent.com/2dust/v2rayNG/refs/heads/master/V2rayNG/app/src/main/ic_launcher-web.png',
          description: 'A V2Ray client for Android devices.',
          faDescription: 'V2rayNG یک کلاینت V2Ray برای دستگاه‌های اندرویدی است.',
          ruDescription: 'Клиент V2Ray для устройств Android.',
          zhDescription: '适用于 Android 设备的 V2Ray 客户端。',
          configLink: 'v2rayng://install-config?url={url}',
          downloadLink: 'https://github.com/2dust/v2rayNG/releases/latest',
        },
        {
          name: 'SingBox',
          logo: 'https://sing-box.sagernet.org/assets/icon.svg',
          description: 'A client that provides a platform for routing traffic securely.',
          faDescription: 'Sing-box یک کلاینت برای مسیریابی امن ترافیک فراهم می‌کند.',
          ruDescription: 'Клиент, обеспечивающий безопасную маршрутизацию трафика.',
          zhDescription: '提供安全流量路由的平台客户端。',
          configLink: 'sing-box://import-remote-profile?url={url}',
          downloadLink: 'https://play.google.com/store/apps/details?id=io.nekohasekai.sfa&hl=en',
        },
      ],
    },
    {
      name: 'Windows',
      apps: [
        {
          name: 'V2rayN',
          logo: 'https://raw.githubusercontent.com/2dust/v2rayN/refs/heads/master/v2rayN/v2rayN.Desktop/v2rayN.png',
          description: 'A Windows V2Ray client with GUI support.',
          faDescription: 'v2rayN یک کلاینت V2Ray برای ویندوز با پشتیبانی از رابط کاربری است.',
          ruDescription: 'V2Ray клиент для Windows с графическим интерфейсом.',
          zhDescription: '带有图形界面的 Windows V2Ray 客户端。',
          downloadLink: 'https://github.com/2dust/v2rayN/releases/latest',
        },
        {
          name: 'FlClash',
          logo: 'https://raw.githubusercontent.com/chen08209/FlClash/refs/heads/main/assets/images/icon.png',
          description: 'A cross-platform GUI client for clash core.',
          faDescription: 'Flclash یک کلاینت GUI چندسکویی برای clash core است.',
          ruDescription: 'Кроссплатформенный GUI-клиент для clash core.',
          zhDescription: '跨平台 clash core 图形界面客户端。',
          downloadLink: 'https://github.com/chen08209/FlClash/releases/latest',
        },
      ],
    },
    {
      name: 'Linux',
      apps: [
        {
          name: 'FlClash',
          logo: 'https://raw.githubusercontent.com/chen08209/FlClash/refs/heads/main/assets/images/icon.png',
          description: 'A cross-platform GUI client for clash core.',
          faDescription: 'Flclash یک کلاینت GUI چندسکویی برای clash core است.',
          ruDescription: 'Кроссплатформенный GUI-клиент для clash core.',
          zhDescription: '跨平台 clash core 图形界面客户端。',
          downloadLink: 'https://github.com/chen08209/FlClash/releases/latest',
        },
        {
          name: 'SingBox',
          logo: 'https://sing-box.sagernet.org/assets/icon.svg',
          description: 'A client that provides a platform for routing traffic securely.',
          faDescription: 'Sing-box یک کلاینت برای مسیریابی امن ترافیک فراهم می‌کند.',
          ruDescription: 'Клиент, обеспечивающий безопасную маршрутизацию трафика.',
          zhDescription: '提供安全流量路由的平台客户端。',
          configLink: 'sing-box://import-remote-profile?url={url}',
          downloadLink: 'https://github.com/SagerNet/sing-box/releases/latest',
        },
      ],
    },
  ],
}

function mapOsNameToPlatform(engName: string): SubscriptionPlatform {
  switch (engName.toLowerCase()) {
    case 'android':
      return 'android'
    case 'ios':
      return 'ios'
    case 'windows':
      return 'windows'
    case 'linux':
      return 'linux'
    case 'macos':
      return 'macos'
    default:
      return 'android'
  }
}

export function buildDefaultApplications() {
  const apps: {
    name: string
    icon_url?: string
    import_url?: string
    description?: Record<string, string>
    recommended?: boolean
    platform: 'android' | 'ios' | 'windows' | 'macos' | 'linux' | 'appletv' | 'androidtv'
    download_links: { name: string; url: string; language: 'fa' | 'en' | 'ru' | 'zh' }[]
  }[] = []

  const recommendedSet = new Set(['v2rayn', 'streisand', 'v2rayng', 'flclash'])

  const platformRecommendedChosen: Record<string, boolean> = {}
  for (const os of defaultApplicationsData.operatingSystems) {
    const platform = mapOsNameToPlatform(os.name)
    for (const app of os.apps) {
      const nameLower = String(app.name || '').toLowerCase()
      const candidateRecommended = recommendedSet.has(nameLower)
      const finalRecommended = candidateRecommended && !platformRecommendedChosen[platform]
      if (finalRecommended) platformRecommendedChosen[platform] = true
      apps.push({
        name: app.name,
        icon_url: app.logo || '',
        import_url: app.configLink || '',
        description: {
          en: app.description || '',
          fa: app.faDescription || app.description || '',
          ru: app.ruDescription || app.description || '',
          zh: app.zhDescription || app.description || '',
        },
        recommended: finalRecommended,
        platform,
        download_links: [
          { name: 'Download', url: app.downloadLink, language: 'en' },
          { name: 'دانلود', url: app.downloadLink, language: 'fa' },
          { name: 'Скачать', url: app.downloadLink, language: 'ru' },
          { name: '下载', url: app.downloadLink, language: 'zh' },
        ],
      })
    }
  }

  return apps
}

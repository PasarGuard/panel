import { SortableApplication } from '@/components/apps/sortable-application'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { VariablesList, VariablesPopover } from '@/components/ui/variables-popover'
import { type SubRule as ApiSubRule } from '@/service/api'
import { closestCenter, DndContext, DragEndEvent, KeyboardSensor, PointerSensor, useSensor, useSensors } from '@dnd-kit/core'
import { rectSortingStrategy, SortableContext, sortableKeyboardCoordinates, useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  ArrowUpWideNarrow, Cat, CircleOff,
  Clock, Code, ExternalLink, FileCode2,
  FileText, Globe, GlobeLock, GripVertical,
  HelpCircle, Info, Link, ListTree, Megaphone, Plus,
  RotateCcw, Settings, Shuffle, Trash2, User
} from 'lucide-react'
import { WireguardIcon, XrayIcon, SingboxIcon, MihomoIcon } from '@/components/icons/format-icons'
import { useEffect, useState } from 'react'
import { FieldErrors, useFieldArray, useForm, UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { z } from 'zod'
import useDirDetection from '@/hooks/use-dir-detection'
import { useIsMobile } from '@/hooks/use-mobile'
import { useSettingsContext } from './_dashboard.settings'

// Enhanced validation schema for subscription settings
const subscriptionSchema = z.object({
  url_prefix: z.string().optional(),
  update_interval: z.number().min(1, 'Update interval must be at least 1 hour').max(168, 'Update interval cannot exceed 168 hours (1 week)').optional(),
  support_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
  profile_title: z.string().optional(),
  announce: z.string().max(128, 'Announcement must be 128 characters or less').optional(),
  announce_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
  allow_browser_config: z.boolean().optional(),
  disable_sub_template: z.boolean().optional(),
  randomize_order: z.boolean().optional(),
  rules: z.array(
    z.object({
      pattern: z.string().min(1, 'Pattern is required'),
      target: z.enum(['links', 'links_base64', 'xray', 'wireguard', 'sing_box', 'clash', 'clash_meta', 'outline', 'block']),
      response_headers: z.record(z.string()).optional(),
    }),
  ),
  applications: z
    .array(
      z.object({
        name: z.string().min(1, 'Application name is required').max(32, 'Application name must be 32 characters or less'),
        icon_url: z.string().url('Please enter a valid URL').optional().or(z.literal('')),
        import_url: z
          .string()
          .refine(
            url => {
              if (!url || url === '') return true
              return url.includes('{url}')
            },
            {
              message: 'Import URL must contain {url} placeholder for URL replacement',
            },
          )
          .optional()
          .or(z.literal('')),
        description: z.record(z.string()).optional(),
        recommended: z.boolean().optional(),
        platform: z.enum(['android', 'ios', 'windows', 'macos', 'linux', 'appletv', 'androidtv']),
        download_links: z
          .array(
            z.object({
              name: z.string().min(1, 'Download link name is required').max(64, 'Download link name must be 64 characters or less'),
              url: z.string().url('Please enter a valid URL'),
              language: z.enum(['fa', 'en', 'ru', 'zh']),
            }),
          )
          .min(1, 'At least one download link is required'),
      }),
    )
    .optional(),
  manual_sub_request: z
    .object({
      links: z.boolean().optional(),
      links_base64: z.boolean().optional(),
      xray: z.boolean().optional(),
      wireguard: z.boolean().optional(),
      sing_box: z.boolean().optional(),
      clash: z.boolean().optional(),
      clash_meta: z.boolean().optional(),
      outline: z.boolean().optional(),
    })
    .optional(),
})

type SubscriptionFormData = z.infer<typeof subscriptionSchema>
type SubscriptionRuleFormData = SubscriptionFormData['rules'][number]
type SubscriptionApplicationFormData = NonNullable<SubscriptionFormData['applications']>[number]
type SubscriptionPlatform = SubscriptionApplicationFormData['platform']
type SubscriptionLanguage = NonNullable<SubscriptionApplicationFormData['download_links']>[number]['language']

interface DefaultCatalogApp {
  name: string
  logo?: string
  description?: string
  faDescription?: string
  ruDescription?: string
  zhDescription?: string
  configLink?: string
  downloadLink: string
}

interface DefaultOperatingSystem {
  name: string
  apps: DefaultCatalogApp[]
}

const configFormatOptions = [
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

// Default Applications Dataset (mapped from provided data)
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

const mapOsNameToPlatform = (engName: string): SubscriptionPlatform => {
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

const buildDefaultApplications = () => {
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

// Default subscription rules
const defaultSubscriptionRules: SubscriptionRuleFormData[] = [
  {
    pattern: '^([Cc]lash[\\-\\.]?[Vv]erge|[Cc]lash[\\-\\.]?[Mm]eta|[Ff][Ll][Cc]lash|[Mm]ihomo)',
    target: 'clash_meta',
  },
  {
    pattern: '^([Cc]lash|[Ss]tash)',
    target: 'clash',
  },
  {
    pattern: '^(SFA|SFI|SFM|SFT|[Kk]aring|[Hh]iddify[Nn]ext)|.*[Ss]ing[\\-b]?ox.*',
    target: 'sing_box',
  },
  {
    pattern: '^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)',
    target: 'outline',
  },
  {
    pattern: '^([Vv]2rayNG|[Vv]2rayN|[Ss]treisand|[Hh]app|[Kk]tor\\-client)',
    target: 'xray',
  },
  {
    pattern: '.*',
    target: 'links_base64',
  },
]

// Sortable Rule Component
interface SortableRuleProps {
  rule: SubscriptionRuleFormData
  index: number
  onRemove: (index: number) => void
  form: UseFormReturn<SubscriptionFormData>
  id: string
}

function SortableRule({ index, onRemove, form, id }: SortableRuleProps) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const isMobile = useIsMobile()
  const isRtl = dir === 'rtl'
  const infoPopoverSide = isMobile ? 'bottom' : dir === 'rtl' ? 'left' : 'right'
  const infoPopoverAlign = isMobile ? 'center' : 'start'
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const [isHeadersOpen, setIsHeadersOpen] = useState(false)
  const responseHeaders = (form.watch(`rules.${index}.response_headers`) || {}) as Record<string, string>
  const responseHeaderEntries = Object.entries(responseHeaders)
  const responseHeaderCount = responseHeaderEntries.length
  const responseHeaderPreview =
    responseHeaderCount > 0
      ? responseHeaderEntries
          .slice(0, 2)
          .map(([headerKey]) => headerKey)
          .join(', ')
      : t('settings.subscriptions.rules.responseHeadersDescription')

  const addResponseHeader = () => {
    const nextKey = `x-header-${Object.keys(responseHeaders).length + 1}`
    form.setValue(
      `rules.${index}.response_headers`,
      {
        ...responseHeaders,
        [nextKey]: '',
      },
      { shouldDirty: true },
    )
  }

  const updateResponseHeaderName = (currentKey: string, nextKey: string) => {
    const updatedHeaders = { ...responseHeaders }
    const currentValue = updatedHeaders[currentKey] ?? ''
    delete updatedHeaders[currentKey]
    updatedHeaders[nextKey] = currentValue
    form.setValue(`rules.${index}.response_headers`, updatedHeaders, { shouldDirty: true })
  }

  const updateResponseHeaderValue = (headerKey: string, value: string) => {
    form.setValue(
      `rules.${index}.response_headers`,
      {
        ...responseHeaders,
        [headerKey]: value,
      },
      { shouldDirty: true },
    )
  }

  const removeResponseHeader = (headerKey: string) => {
    const updatedHeaders = { ...responseHeaders }
    delete updatedHeaders[headerKey]
    form.setValue(`rules.${index}.response_headers`, updatedHeaders, { shouldDirty: true })
  }

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    zIndex: isDragging ? 2 : 1,
    opacity: isDragging ? 0.8 : 1,
  }
  const cursor = isDragging ? 'grabbing' : 'grab'

  return (
    <>
      <div ref={setNodeRef} style={style} className="cursor-default">
        <div className={`group relative h-full rounded-md border bg-card p-3 transition-colors hover:bg-accent/20 sm:p-4 ${isRtl ? 'pl-14' : 'pr-14'}`}>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={e => {
              e.preventDefault()
              e.stopPropagation()
              onRemove(index)
            }}
            className={`absolute top-3 h-8 w-8 shrink-0 p-0 text-destructive opacity-70 transition-opacity hover:bg-destructive/10 hover:text-destructive hover:opacity-100 ${isRtl ? 'left-3' : 'right-3'
              }`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>

          <div className="flex items-start gap-3">
            <button
              type="button"
              style={{ cursor: cursor }}
              className="shrink-0 touch-none opacity-50 transition-opacity group-hover:opacity-100"
              {...attributes}
              {...listeners}
            >
              <GripVertical className="h-5 w-5" />
              <span className="sr-only">Drag to reorder</span>
            </button>

            <div className="min-w-0 flex-1 space-y-3">
              <div className="grid gap-3">
                <FormField
                  control={form.control}
                  name={`rules.${index}.pattern`}
                  render={({ field }) => (
                    <FormItem className="space-y-1">
                      <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.rules.pattern')}</FormLabel>
                      <FormControl>
                        <Input
                          placeholder={t('settings.subscriptions.rules.patternPlaceholder')}
                          {...field}
                          className="h-7 border-muted bg-background/60 font-mono text-xs text-foreground/90 focus:bg-background"
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name={`rules.${index}.target`}
                  render={({ field }) => (
                    <FormItem className="space-y-1">
                      <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.rules.target')}</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger className="h-7 border-muted bg-background/60 text-xs focus:bg-background">
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent className="scrollbar-thin z-[50]">
                          {configFormatOptions.map(option => (
                            <SelectItem key={option.value} value={option.value}>
                              <div className="flex items-center gap-1.5">
                                <option.icon className="h-4 w-4" />
                                <span className="text-xs">{t(option.label)}</span>
                              </div>
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="rounded-md border border-dashed border-muted p-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-foreground">{t('settings.subscriptions.rules.responseHeaders')}</p>
                    <p className="truncate text-[11px] text-muted-foreground">{responseHeaderPreview}</p>
                  </div>
                  <Button type="button" variant="outline" size="sm" className="h-7 shrink-0 px-2 text-xs" onClick={() => setIsHeadersOpen(true)}>
                    {responseHeaderCount === 0 ? t('settings.subscriptions.rules.addHeader') : t('settings.subscriptions.rules.responseHeaders')}
                  </Button>
                </div>
              </div>
            </div>
          </div>

          {isDragging && <div className="pointer-events-none absolute inset-0 rounded-md border border-primary/20 bg-primary/5" />}
        </div>
      </div>

      <Dialog open={isHeadersOpen} onOpenChange={setIsHeadersOpen}>
        <DialogContent className="max-w-2xl" onOpenAutoFocus={e => e.preventDefault()}>
          <DialogHeader>
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <DialogTitle>{t('settings.subscriptions.rules.responseHeaders')}</DialogTitle>
                <DialogDescription>{t('settings.subscriptions.rules.responseHeadersDescription')}</DialogDescription>
              </div>
              <Popover>
                <PopoverTrigger asChild>
                  <Button type="button" variant="ghost" size="icon" className="mt-0.5 h-4 w-4 shrink-0 p-0 hover:bg-transparent">
                    <Info className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[min(90vw,20rem)] p-3 sm:w-80" side={infoPopoverSide} align={infoPopoverAlign} sideOffset={5}>
                  <div className="space-y-1.5">
                    <h4 className="mb-2 text-[11px] font-medium">{t('hostsDialog.variables.title')}</h4>
                    <div className="max-h-[60vh] space-y-1 overflow-y-auto pr-1">
                      <VariablesList includeProfileTitle={true} includeFormat={true} />
                    </div>
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="flex justify-end">
              <Button type="button" variant="outline" size="sm" onClick={addResponseHeader}>
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                {t('settings.subscriptions.rules.addHeader')}
              </Button>
            </div>

            <div className="max-h-[60dvh] space-y-3 overflow-y-auto">
              {responseHeaderCount > 0 ? (
                responseHeaderEntries.map(([headerKey, headerValue]) => (
                  <div key={`${id}-${headerKey}`} className="space-y-2 rounded-lg border bg-card/50 p-3">
                    <div className="flex items-start gap-2">
                      <Input
                        value={headerKey}
                        onChange={e => updateResponseHeaderName(headerKey, e.target.value)}
                        placeholder={t('settings.subscriptions.rules.headerName')}
                        className="font-mono text-xs"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 shrink-0 text-destructive hover:bg-destructive/10"
                        onClick={() => removeResponseHeader(headerKey)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                    <Textarea
                      value={headerValue}
                      onChange={e => updateResponseHeaderValue(headerKey, e.target.value)}
                      placeholder={t('settings.subscriptions.rules.headerValue')}
                      className="min-h-[60px] resize-none font-mono text-xs"
                      rows={2}
                    />
                  </div>
                ))
              ) : (
                <div className="rounded-lg border border-dashed border-border/70 px-4 py-8 text-center">
                  <p className="text-sm font-medium text-foreground">{t('settings.subscriptions.rules.responseHeaders')}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{t('settings.subscriptions.rules.responseHeadersDescription')}</p>
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setIsHeadersOpen(false)}>
              {t('close', { defaultValue: 'Close' })}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export default function SubscriptionSettings() {
  const { t } = useTranslation()
  const { settings, isLoading, error, updateSettings, isSaving } = useSettingsContext()
  const [isAddAppOpen, setIsAddAppOpen] = useState(false)
  const [newAppName, setNewAppName] = useState('')
  const [newAppPlatform, setNewAppPlatform] = useState<'android' | 'ios' | 'windows' | 'macos' | 'linux' | 'appletv' | 'androidtv'>('android')
  const [newAppImportUrl, setNewAppImportUrl] = useState('')
  const [newAppIconUrl, setNewAppIconUrl] = useState('')
  const [newAppIconBroken, setNewAppIconBroken] = useState(false)
  const [newAppRecommended, setNewAppRecommended] = useState(false)
  const [newLinkName, setNewLinkName] = useState('')
  const [newLinkUrl, setNewLinkUrl] = useState('')
  const [newLinkLang, setNewLinkLang] = useState<SubscriptionLanguage>('en')
  const [newDescLang, setNewDescLang] = useState<SubscriptionLanguage>('en')
  const [newAppDescription, setNewAppDescription] = useState<Record<SubscriptionLanguage, string>>({
    fa: '',
    en: '',
    ru: '',
    zh: '',
  })

  const isValidIconUrl = (url: string): boolean => {
    if (!url || url.trim() === '') return false

    try {
      const urlObj = new URL(url)
      // Only allow HTTP and HTTPS protocols (prevents javascript:, data: XSS)
      if (urlObj.protocol !== 'http:' && urlObj.protocol !== 'https:') {
        return false
      }
      // Ensure the URL is not a potential XSS vector
      // Disallow URLs with javascript: or data: anywhere in the string
      const normalizedUrl = url.toLowerCase().trim()
      if (normalizedUrl.includes('javascript:') || normalizedUrl.includes('data:')) {
        return false
      }
      return true
    } catch {
      return false
    }
  }

  useEffect(() => {
    // reset icon error state when URL changes
    setNewAppIconBroken(false)
  }, [newAppIconUrl])

  const form = useForm<SubscriptionFormData>({
    resolver: zodResolver(subscriptionSchema),
    defaultValues: {
      url_prefix: '',
      update_interval: 24,
      support_url: '',
      profile_title: '',
      announce: '',
      announce_url: '',
      allow_browser_config: true,
      disable_sub_template: false,
      randomize_order: false,
      rules: [],
      applications: [],
      manual_sub_request: {
        links: true,
        links_base64: true,
        xray: true,
        wireguard: true,
        sing_box: true,
        clash: true,
        clash_meta: true,
        outline: true,
      },
    },
  })

  const {
    fields: ruleFields,
    append: appendRule,
    remove: removeRule,
    move: moveRule,
  } = useFieldArray({
    control: form.control,
    name: 'rules',
  })

  const {
    fields: applicationFields,
    append: appendApplication,
    remove: removeApplication,
    move: moveApplication,
  } = useFieldArray({
    control: form.control,
    name: 'applications',
  })

  // Drag and drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  )

  // Handle drag end for rules and applications reordering
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event

    if (over && active.id !== over.id) {
      // Check if it's a rule
      const ruleOldIndex = ruleFields.findIndex(field => field.id === active.id)
      const ruleNewIndex = ruleFields.findIndex(field => field.id === over.id)

      if (ruleOldIndex !== -1 && ruleNewIndex !== -1) {
        moveRule(ruleOldIndex, ruleNewIndex)
        return
      }

      // Check if it's an application
      const appOldIndex = applicationFields.findIndex(field => field.id === active.id)
      const appNewIndex = applicationFields.findIndex(field => field.id === over.id)

      if (appOldIndex !== -1 && appNewIndex !== -1) {
        // Restrict sorting to within the same platform ("parent").
        const apps = (form.getValues('applications') || []) as SubscriptionApplicationFormData[]
        const oldPlatform = apps?.[appOldIndex]?.platform
        const newPlatform = apps?.[appNewIndex]?.platform
        if (oldPlatform && newPlatform && oldPlatform === newPlatform) {
          moveApplication(appOldIndex, appNewIndex)
        } else {
          // Do nothing if platforms differ to keep items sortable only inside their parent
        }
        return
      }
    }
  }

  // Update form when settings are loaded
  useEffect(() => {
    if (settings?.subscription) {
      const subscriptionData = settings.subscription
      form.reset({
        url_prefix: subscriptionData.url_prefix || '',
        update_interval: subscriptionData.update_interval || 24,
        support_url: subscriptionData.support_url || '',
        profile_title: subscriptionData.profile_title || '',
        announce: subscriptionData.announce || '',
        announce_url: subscriptionData.announce_url || '',
        allow_browser_config: subscriptionData.allow_browser_config ?? true,
        disable_sub_template: subscriptionData.disable_sub_template ?? false,
        randomize_order: subscriptionData.randomize_order ?? false,
        rules:
          subscriptionData.rules?.map((rule: ApiSubRule) => ({
            pattern: rule.pattern,
            target: rule.target,
            response_headers: Object.fromEntries(
              Object.entries(rule.response_headers || {}).map(([key, value]) => [key, typeof value === 'string' ? value : JSON.stringify(value)]),
            ),
          })) || [],
        applications: subscriptionData.applications || [],
        manual_sub_request: {
          links: subscriptionData.manual_sub_request?.links ?? true,
          links_base64: subscriptionData.manual_sub_request?.links_base64 ?? true,
          xray: subscriptionData.manual_sub_request?.xray ?? true,
          wireguard: subscriptionData.manual_sub_request?.wireguard ?? true,
          sing_box: subscriptionData.manual_sub_request?.sing_box ?? true,
          clash: subscriptionData.manual_sub_request?.clash ?? true,
          clash_meta: subscriptionData.manual_sub_request?.clash_meta ?? true,
          outline: subscriptionData.manual_sub_request?.outline ?? true,
        },
      })
    }
  }, [settings, form])

  const onSubmit = async (data: SubscriptionFormData) => {
    try {
      const processedRules = (data.rules || []).map(rule => ({
        pattern: rule.pattern.trim(),
        target: rule.target,
        response_headers: Object.fromEntries(
          Object.entries(rule.response_headers || {})
            .map(([key, value]) => [key.trim(), value.trim()] as const)
            .filter(([key, value]) => key && value),
        ),
      }))

      // Process applications data to ensure proper format
      // Normalize recommended: allow only one per platform
      const rawApps = (data.applications || [])
        .map(app => ({
          name: app.name?.trim() || '',
          icon_url: app.icon_url?.trim() || undefined,
          import_url: app.import_url?.trim() || undefined,
          description: app.description || {},
          recommended: app.recommended || false,
          platform: app.platform,
          download_links: (app.download_links || [])
            .map(link => ({
              name: link.name?.trim() || '',
              url: link.url?.trim() || '',
              language: link.language,
            }))
            .filter(link => link.name && link.url), // Filter out empty links
        }))
        .filter(app => app.name)

      const platformHasRecommended: Record<string, boolean> = {}
      const processedApplications = rawApps.map(app => {
        if (app.recommended) {
          if (platformHasRecommended[app.platform]) {
            return { ...app, recommended: false }
          }
          platformHasRecommended[app.platform] = true
        }
        return app
      })

      // Filter out empty values and prepare the payload
      const filteredData = {
        subscription: {
          ...data,
          // Convert empty strings to undefined
          url_prefix: data.url_prefix?.trim() || undefined,
          support_url: data.support_url?.trim() || undefined,
          profile_title: data.profile_title?.trim() || undefined,
          announce: data.announce?.trim() || undefined,
          announce_url: data.announce_url?.trim() || undefined,
          rules: processedRules,
          // Include processed applications
          applications: processedApplications,
        },
      }

      await updateSettings(filteredData)
    } catch {
      // Error handling is done in the parent context
    }
  }

  const onInvalid = (errors: FieldErrors<SubscriptionFormData>) => {
    // Specific: if any application name is missing, show translated required message
    const appsErrors = errors?.applications
    if (Array.isArray(appsErrors)) {
      for (let i = 0; i < appsErrors.length; i++) {
        const appErr = appsErrors[i]
        if (appErr?.name) {
          toast.error(t('validation.required', { field: t('settings.subscriptions.applications.name') }))
          return
        }
        // Download links array-level error
        if (appErr?.download_links?.message) {
          toast.error(t('settings.subscriptions.applications.downloadLinksRequired', { defaultValue: 'At least one download link is required' }))
          return
        }
        // Per-link field errors
        if (Array.isArray(appErr?.download_links)) {
          for (let j = 0; j < appErr.download_links.length; j++) {
            const linkErr = appErr.download_links[j]
            if (linkErr?.name) {
              toast.error(t('validation.required', { field: t('settings.subscriptions.applications.downloadLinkName', { defaultValue: 'Download link name' }) }))
              return
            }
            if (linkErr?.url) {
              toast.error(t('validation.url', { defaultValue: 'Please enter a valid URL' }))
              return
            }
          }
        }
      }
    }

    // Try to extract the first human-friendly message from nested errors
    const extractFirstMessage = (errObj: unknown): string | undefined => {
      if (!errObj) return undefined
      if (Array.isArray(errObj)) {
        for (const item of errObj) {
          const msg = extractFirstMessage(item)
          if (msg) return msg
        }
      } else if (typeof errObj === 'object' && errObj !== null) {
        const errorRecord = errObj as Record<string, unknown>
        if (typeof errorRecord.message === 'string') return errorRecord.message
        for (const key of Object.keys(errorRecord)) {
          const msg = extractFirstMessage(errorRecord[key])
          if (msg) return msg
        }
      }
      return undefined
    }

    const firstMessage = extractFirstMessage(errors)
    toast.error(firstMessage || t('validation.formHasErrors', { defaultValue: 'Please fix the form errors before submitting' }))
  }

  const handleCancel = () => {
    if (settings?.subscription) {
      const subscriptionData = settings.subscription
      form.reset({
        url_prefix: subscriptionData.url_prefix || '',
        update_interval: subscriptionData.update_interval || 24,
        support_url: subscriptionData.support_url || '',
        profile_title: subscriptionData.profile_title || '',
        announce: subscriptionData.announce || '',
        announce_url: subscriptionData.announce_url || '',
        allow_browser_config: subscriptionData.allow_browser_config ?? true,
        disable_sub_template: subscriptionData.disable_sub_template ?? false,
        randomize_order: subscriptionData.randomize_order ?? false,
        rules:
          subscriptionData.rules?.map((rule: ApiSubRule) => ({
            pattern: rule.pattern,
            target: rule.target,
            response_headers: Object.fromEntries(
              Object.entries(rule.response_headers || {}).map(([key, value]) => [key, typeof value === 'string' ? value : JSON.stringify(value)]),
            ),
          })) || [],
        applications: subscriptionData.applications || [],
        manual_sub_request: {
          links: subscriptionData.manual_sub_request?.links ?? true,
          links_base64: subscriptionData.manual_sub_request?.links_base64 ?? true,
          xray: subscriptionData.manual_sub_request?.xray ?? true,
          wireguard: subscriptionData.manual_sub_request?.wireguard ?? true,
          sing_box: subscriptionData.manual_sub_request?.sing_box ?? true,
          clash: subscriptionData.manual_sub_request?.clash ?? true,
          clash_meta: subscriptionData.manual_sub_request?.clash_meta ?? true,
          outline: subscriptionData.manual_sub_request?.outline ?? true,
        },
      })
      toast.success(t('settings.subscriptions.cancelSuccess'))
    }
  }

  const handleResetToDefault = () => {
    form.setValue('rules', defaultSubscriptionRules)
    toast.success(t('settings.subscriptions.resetToDefaultSuccess', { defaultValue: 'Reset to default settings' }))
  }

  const handleLoadOrResetApplications = () => {
    const defaults = buildDefaultApplications()
    form.setValue('applications', defaults)
    toast.success(
      applicationFields.length === 0
        ? t('settings.subscriptions.applications.loadedDefaults', { defaultValue: 'Defaults loaded' })
        : t('settings.subscriptions.applications.resetToDefaultSuccess', { defaultValue: 'Applications reset to defaults' }),
    )
  }

  const addRule = () => {
    appendRule({ pattern: '', target: 'links', response_headers: {} })
  }

  const addApplication = () => {
    // Check if there's already an empty application (name is empty)
    const hasEmptyApplication = applicationFields.some(field => !field.name || field.name.trim() === '')

    if (hasEmptyApplication) {
      toast.error(
        t('settings.subscriptions.applications.duplicateApplication', {
          defaultValue: 'Please fill in the existing application before adding a new one',
        }),
      )
      return
    }
    // Open modal instead of directly appending
    setNewAppName('')
    setNewAppPlatform('android')
    setNewAppImportUrl('')
    setNewAppIconUrl('')
    setIsAddAppOpen(true)
  }

  const handleConfirmCreateApplication = () => {
    if (!newAppName.trim()) {
      toast.error(t('validation.required', { field: t('settings.subscriptions.applications.name') }))
      return
    }
    const links =
      newLinkName.trim() && newLinkUrl.trim()
        ? [{ name: newLinkName.trim(), url: newLinkUrl.trim(), language: newLinkLang }]
        : [{ name: t('settings.subscriptions.applications.addDownloadLink'), url: '', language: 'en' as const }]
    appendApplication({
      name: newAppName.trim(),
      icon_url: newAppIconUrl.trim(),
      import_url: newAppImportUrl.trim(),
      description: newAppDescription,
      recommended: newAppRecommended,
      platform: newAppPlatform,
      download_links: links,
    })
    setIsAddAppOpen(false)
  }

  if (isLoading) {
    return (
      <div className="w-full p-4 sm:py-6 lg:py-8">
        <div className="space-y-6 sm:space-y-8 lg:space-y-10">
          {/* General Settings Skeleton */}
          <div className="space-y-4 sm:space-y-6">
            <div className="space-y-2">
              <div className="h-6 w-48 animate-pulse rounded bg-muted"></div>
              <div className="h-4 w-96 animate-pulse rounded bg-muted"></div>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="space-y-2">
                  <div className="h-4 w-24 animate-pulse rounded bg-muted"></div>
                  <div className="h-10 animate-pulse rounded bg-muted"></div>
                  <div className="h-3 w-64 animate-pulse rounded bg-muted"></div>
                </div>
              ))}
            </div>
            <div className="h-16 animate-pulse rounded bg-muted"></div>
          </div>

          {/* Rules Section Skeleton */}
          <div className="space-y-4 sm:space-y-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
              <div className="space-y-1">
                <div className="h-6 w-32 animate-pulse rounded bg-muted"></div>
                <div className="h-4 w-80 animate-pulse rounded bg-muted"></div>
              </div>
              <div className="h-9 w-24 animate-pulse rounded bg-muted"></div>
            </div>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {[...Array(2)].map((_, i) => (
                <div key={i} className="rounded-md border bg-card p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="h-4 w-4 animate-pulse rounded bg-muted"></div>
                    <div className="h-6 w-6 animate-pulse rounded bg-muted"></div>
                  </div>
                  <div className="space-y-2">
                    <div className="space-y-1">
                      <div className="h-3 w-16 animate-pulse rounded bg-muted"></div>
                      <div className="h-8 animate-pulse rounded bg-muted"></div>
                    </div>
                    <div className="space-y-1">
                      <div className="h-3 w-12 animate-pulse rounded bg-muted"></div>
                      <div className="h-8 animate-pulse rounded bg-muted"></div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Formats Section Skeleton */}
          <div className="space-y-4 sm:space-y-6">
            <div className="space-y-1">
              <div className="h-6 w-40 animate-pulse rounded bg-muted"></div>
              <div className="h-4 w-72 animate-pulse rounded bg-muted"></div>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3 lg:gap-6">
              {[...Array(7)].map((_, i) => (
                <div key={i} className="h-16 animate-pulse rounded bg-muted"></div>
              ))}
            </div>
          </div>

          {/* Action Buttons Skeleton */}
          <div className="flex flex-col gap-3 pt-4 sm:flex-row sm:gap-4 sm:pt-6">
            <div className="flex-1"></div>
            <div className="flex flex-col gap-3 sm:shrink-0 sm:flex-row sm:gap-4">
              <div className="h-10 w-24 animate-pulse rounded bg-muted"></div>
              <div className="h-10 w-20 animate-pulse rounded bg-muted"></div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex min-h-[400px] items-center justify-center p-4 sm:py-6 lg:py-8">
        <div className="space-y-3 text-center">
          <div className="text-lg text-red-500">⚠️</div>
          <p className="text-sm text-red-500">Error loading settings</p>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit, onInvalid)} className="space-y-6 p-4 sm:space-y-8 sm:py-6 lg:space-y-10 lg:py-8">
          {/* General Settings */}
          <div className="space-y-3">
            <div className="space-y-2">
              <h3 className="text-base font-semibold sm:text-lg">{t('settings.subscriptions.general.title')}</h3>
              <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.description')}</p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:gap-4 lg:grid-cols-2">
              <FormField
                control={form.control}
                name="url_prefix"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                      <Link className="h-4 w-4 shrink-0" />
                      {t('settings.subscriptions.general.urlPrefix')}
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="https://example.com" {...field} className="font-mono text-xs sm:text-sm" />
                    </FormControl>
                    <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.urlPrefixDescription')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="update_interval"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                      <Clock className="h-4 w-4" />
                      {t('settings.subscriptions.general.updateInterval')}
                    </FormLabel>
                    <FormControl>
                      <div className="relative">
                        <Input type="number" min="1" max="168" {...field} onChange={e => field.onChange(parseInt(e.target.value) || 24)} className="pr-16 text-xs sm:text-sm" />
                        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-3">
                          <span className="text-xs text-muted-foreground sm:text-sm">hours</span>
                        </div>
                      </div>
                    </FormControl>
                    <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.updateIntervalDescription')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="support_url"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                      <HelpCircle className="h-4 w-4" />
                      {t('settings.subscriptions.general.supportUrl')}
                    </FormLabel>
                    <FormControl>
                      <Input type="url" placeholder={t('settings.subscriptions.general.supportUrlPlaceholder')} {...field} className="font-mono text-xs sm:text-sm" />
                    </FormControl>
                    <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.supportUrlDescription')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="profile_title"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <div className="flex items-center gap-1.5">
                      <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                        <User className="h-4 w-4" />
                        {t('settings.subscriptions.general.profileTitle')}
                      </FormLabel>
                      <VariablesPopover includeProfileTitle={true} />
                    </div>
                    <FormControl>
                      <Input placeholder={t('settings.subscriptions.general.profileTitlePlaceholder')} {...field} className="text-xs sm:text-sm" />
                    </FormControl>
                    <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.profileTitleDescription')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="announce"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                      <Megaphone className="h-4 w-4" />
                      {t('settings.subscriptions.general.announce')}
                    </FormLabel>
                    <FormControl>
                      <Textarea
                        maxLength={128}
                        placeholder={t('settings.subscriptions.general.announcePlaceholder')}
                        rows={3}
                        className="resize-none text-xs sm:text-sm"
                        {...field}
                      />
                    </FormControl>
                    <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.announceDescription')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="announce_url"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-2 text-xs font-medium sm:text-sm">
                      <ExternalLink className="h-4 w-4" />
                      {t('settings.subscriptions.general.announceUrl')}
                    </FormLabel>
                    <FormControl>
                      <Input type="url" placeholder={t('settings.subscriptions.general.announceUrlPlaceholder')} {...field} className="font-mono text-xs sm:text-sm" />
                    </FormControl>
                    <FormDescription className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.general.announceUrlDescription')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="allow_browser_config"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4 lg:col-span-2">
                    <div className="flex-1 space-y-0.5 pr-4">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <Globe className="h-4 w-4 shrink-0" />
                        <span className="break-words">{t('settings.subscriptions.general.allowBrowserConfig')}</span>
                      </FormLabel>
                      <FormDescription className="text-xs leading-relaxed text-muted-foreground sm:leading-normal">
                        {t('settings.subscriptions.general.allowBrowserConfigDescription')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} className="shrink-0" />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="disable_sub_template"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4 lg:col-span-2">
                    <div className="flex-1 space-y-0.5 pr-4">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <FileCode2 className="h-4 w-4 shrink-0" />
                        <span className="break-words">{t('settings.subscriptions.general.disableSubTemplate')}</span>
                      </FormLabel>
                      <FormDescription className="text-xs leading-relaxed text-muted-foreground sm:leading-normal">
                        {t('settings.subscriptions.general.disableSubTemplateDescription')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} className="shrink-0" />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="randomize_order"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4 lg:col-span-2">
                    <div className="flex-1 space-y-0.5 pr-4">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <Shuffle className="h-4 w-4 shrink-0" />
                        <span className="break-words">{t('settings.subscriptions.general.randomizeOrder')}</span>
                      </FormLabel>
                      <FormDescription className="text-xs leading-relaxed text-muted-foreground sm:leading-normal">
                        {t('settings.subscriptions.general.randomizeOrderDescription')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} className="shrink-0" />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>
          </div>

          <Separator className="my-3" />

          {/* Subscription Rules with Drag & Drop */}
          <div className="space-y-3">
            <div className="rounded-lg border bg-card p-3 shadow-sm sm:p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
                <div className="space-y-1 min-w-0 flex-1">
                  <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold sm:text-lg">
                    <ArrowUpWideNarrow className="h-5 w-5 text-primary shrink-0" />
                    {t('settings.subscriptions.rules.title')}
                    {ruleFields.length > 0 && (
                      <Badge variant="secondary" className="ml-2 shrink-0">
                        {ruleFields.length}
                      </Badge>
                    )}
                  </h3>
                  <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.rules.description')}</p>
                </div>
                <div className="flex flex-col gap-2 sm:flex-row sm:gap-2 w-full sm:w-auto">
                  <Button type="button" variant="outline" size="sm" onClick={handleResetToDefault} className="flex items-center justify-center gap-2 w-full sm:w-auto" disabled={isSaving}>
                    <RotateCcw className="h-4 w-4" />
                    <span className="hidden sm:inline">{t('settings.subscriptions.resetToDefault', { defaultValue: 'Reset to Default' })}</span>
                    <span className="sm:hidden">{t('settings.subscriptions.resetToDefault', { defaultValue: 'Reset' })}</span>
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={addRule} className="flex shrink-0 items-center justify-center gap-2 w-full sm:w-auto">
                    <Plus className="h-4 w-4" />
                    {t('settings.subscriptions.rules.addRule')}
                  </Button>
                </div>
              </div>
            </div>

            {ruleFields.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">
                <FileText className="mx-auto mb-3 h-8 w-8 opacity-30" />
                <p className="mb-1 text-xs font-medium sm:text-sm">{t('settings.subscriptions.rules.noRules')}</p>
              </div>
            ) : (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={ruleFields.map(field => field.id)} strategy={rectSortingStrategy}>
                  <div className="scrollbar-thin grid max-h-[500px] touch-pan-y grid-cols-1 gap-3 overflow-y-auto py-1 sm:gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {ruleFields.map((field, index) => (
                      <SortableRule key={field.id} id={field.id} rule={field} index={index} onRemove={removeRule} form={form} />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            )}
          </div>

          <Separator className="my-3" />

          {/* Applications with Drag & Drop */}
          <div className="space-y-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
              <div className="space-y-1 min-w-0 flex-1">
                <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold sm:text-lg">
                  {t('settings.subscriptions.applications.title')}
                  {applicationFields.length > 0 && (
                    <Badge variant="secondary" className="ml-2 shrink-0">
                      {applicationFields.length}
                    </Badge>
                  )}
                </h3>
                <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.applications.description')}</p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-2 w-full sm:w-auto">
                <Button type="button" variant="outline" size="sm" onClick={handleLoadOrResetApplications} className="flex shrink-0 items-center justify-center gap-2 w-full sm:w-auto">
                  <RotateCcw className="h-4 w-4" />
                  <span className="hidden sm:inline">
                    {applicationFields.length === 0
                      ? t('settings.subscriptions.applications.loadDefaults', { defaultValue: 'Load defaults' })
                      : t('settings.subscriptions.applications.resetToDefault', { defaultValue: 'Reset to default' })}
                  </span>
                  <span className="sm:hidden">
                    {applicationFields.length === 0
                      ? t('settings.subscriptions.applications.loadDefaults', { defaultValue: 'Load' })
                      : t('settings.subscriptions.applications.resetToDefault', { defaultValue: 'Reset' })}
                  </span>
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={addApplication} className="flex shrink-0 items-center justify-center gap-2 w-full sm:w-auto">
                  <Plus className="h-4 w-4" />
                  <span className="hidden sm:inline">{t('settings.subscriptions.applications.addApplication')}</span>
                  <span className="sm:hidden">{t('settings.subscriptions.applications.addApplication', { defaultValue: 'Add' })}</span>
                </Button>
              </div>
            </div>

            {applicationFields.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">
                <Settings className="mx-auto mb-3 h-8 w-8 opacity-30" />
                <p className="mb-1 text-xs font-medium sm:text-sm">{t('settings.subscriptions.applications.noApplications')}</p>
                <p className="text-xs">{t('settings.subscriptions.applications.noApplicationsDescription')}</p>
              </div>
            ) : (
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                {/* Group items by platform and render separate SortableContexts to isolate drag-and-drop containers */}
                {(['ios', 'android', 'windows', 'macos', 'linux', 'appletv', 'androidtv'] as const).map(platformKey => {
                  const currentApplications = (form.getValues('applications') || []) as SubscriptionApplicationFormData[]
                  const indices = applicationFields.map((f, idx) => ({ id: f.id, idx })).filter(({ idx }) => currentApplications[idx]?.platform === platformKey)
                  if (indices.length === 0) return null
                  return (
                    <SortableContext key={platformKey} items={indices.map(i => i.id)} strategy={rectSortingStrategy}>
                      <div className="mb-2 mt-2 flex items-center gap-2 px-1 sm:px-0">
                        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground shrink-0">{t(`settings.subscriptions.applications.platforms.${platformKey}`)}</span>
                        <div className="hidden h-px flex-1 bg-border sm:block" />
                      </div>
                      <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2">
                        {indices.map(({ id, idx }) => (
                          <SortableApplication key={id} id={id} application={applicationFields[idx]} index={idx} onRemove={removeApplication} form={form} />
                        ))}
                      </div>
                    </SortableContext>
                  )
                })}
              </DndContext>
            )}
          </div>

          <Separator className="my-3" />

          {/* Manual Subscription Formats */}
          <div className="space-y-3">
            <div className="space-y-1">
              <h3 className="flex items-center gap-2 text-base font-semibold sm:text-lg">{t('settings.subscriptions.formats.title')}</h3>
              <p className="text-xs text-muted-foreground sm:text-sm">{t('settings.subscriptions.formats.description')}</p>
            </div>

            {/* Mobile: 1 column, Tablet: 2 columns, Desktop: 3 columns */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3 lg:gap-6">
              <FormField
                control={form.control}
                name="manual_sub_request.links"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <ListTree className="h-4 w-4" />
                        {t('settings.subscriptions.formats.links')}
                      </FormLabel>
                      <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.linksDescription')}</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="manual_sub_request.links_base64"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <Code className="h-4 w-4" />
                        {t('settings.subscriptions.formats.linksBase64')}
                      </FormLabel>
                      <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.linksBase64Description')}</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="manual_sub_request.xray"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <XrayIcon className="h-4 w-4" />
                        {t('settings.subscriptions.formats.xray')}
                      </FormLabel>
                      <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.xrayDescription')}</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="manual_sub_request.wireguard"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <WireguardIcon className="h-4 w-4" />
                        {t('settings.subscriptions.formats.wireguard')}
                      </FormLabel>
                      <FormDescription className="text-xs text-muted-foreground">
                        {t('settings.subscriptions.formats.wireguardDescription')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="manual_sub_request.sing_box"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <SingboxIcon className="h-4 w-4" />
                        {t('settings.subscriptions.formats.singBox')}
                      </FormLabel>
                      <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.singBoxDescription')}</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="manual_sub_request.clash"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <Cat className="h-4 w-4" />
                        {t('settings.subscriptions.formats.clash')}
                      </FormLabel>
                      <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.clashDescription')}</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="manual_sub_request.clash_meta"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <MihomoIcon className="h-4 w-4" />
                        {t('settings.subscriptions.formats.clashMeta')}
                      </FormLabel>
                      <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.clashMetaDescription')}</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="manual_sub_request.outline"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3 transition-colors hover:bg-accent/50 sm:p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="flex cursor-pointer items-center gap-2 text-xs font-medium sm:text-sm">
                        <GlobeLock className="h-4 w-4" />
                        {t('settings.subscriptions.formats.outline')}
                      </FormLabel>
                      <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.formats.outlineDescription')}</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-col gap-2 pt-3 sm:flex-row sm:gap-3 sm:pt-4">
            <div className="flex-1"></div>
            <div className="flex flex-col gap-2 sm:shrink-0 sm:flex-row sm:gap-3">
              <Button type="button" variant="outline" onClick={handleCancel} className="w-full min-w-[100px] sm:w-auto" disabled={isSaving}>
                {t('cancel')}
              </Button>
              <Button type="submit" disabled={isSaving} isLoading={isSaving} loadingText={t('saving')} className="w-full min-w-[100px] sm:w-auto">
                {t('save')}
              </Button>
            </div>
          </div>
        </form>
        {/* Create Application Modal */}
        <Dialog open={isAddAppOpen} onOpenChange={setIsAddAppOpen}>
          <DialogContent className="h-full max-w-full sm:h-auto sm:max-w-[520px] sm:max-h-[90vh]" onOpenAutoFocus={e => e.preventDefault()}>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Plus className="h-5 w-5" />
                <span>{t('settings.subscriptions.applications.addApplication')}</span>
              </DialogTitle>
            </DialogHeader>
            <div className="-mr-4 max-h-[80dvh] overflow-y-auto px-2 pr-4 sm:max-h-[75dvh]">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.name')}</FormLabel>
                  <Input value={newAppName} onChange={e => setNewAppName(e.target.value)} placeholder={t('settings.subscriptions.applications.namePlaceholder')} className="h-8 text-xs" />
                </div>
                <div className="space-y-1">
                  <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.platform')}</FormLabel>
                  <Select value={newAppPlatform} onValueChange={(v: SubscriptionPlatform) => setNewAppPlatform(v)}>
                    <FormControl>
                      <SelectTrigger className="h-8 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent className="scrollbar-thin z-[50]">
                      {(['android', 'ios', 'windows', 'macos', 'linux', 'appletv', 'androidtv'] as const).map(p => (
                        <SelectItem key={p} value={p}>
                          <span className="text-xs">{t(`settings.subscriptions.applications.platforms.${p}`)}</span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.iconUrl', { defaultValue: 'Icon URL' })}</FormLabel>
                  <div className="flex items-center gap-2">
                    <Input
                      value={newAppIconUrl}
                      onChange={e => setNewAppIconUrl(e.target.value)}
                      placeholder={t('settings.subscriptions.applications.iconUrlPlaceholder', { defaultValue: 'https://...' })}
                      className="h-8 font-mono text-xs"
                      dir="ltr"
                    />
                    {/* live preview */}
                    {newAppIconUrl && !newAppIconBroken && isValidIconUrl(newAppIconUrl) ? (
                      <img src={newAppIconUrl} alt="icon" className="h-6 w-6 rounded-sm object-cover" onError={() => setNewAppIconBroken(true)} />
                    ) : (
                      <div className="inline-flex h-6 w-6 items-center justify-center rounded-sm bg-muted text-muted-foreground/80">
                        <span className="text-[10px]">🖼️</span>
                      </div>
                    )}
                  </div>
                  <FormDescription className="text-xs text-muted-foreground">
                    {t('settings.subscriptions.applications.iconUrlDescription', { defaultValue: 'Optional. Shown next to app name.' })}
                  </FormDescription>
                </div>
                <div className="space-y-1 sm:col-span-2">
                  <div className="flex items-center gap-1.5">
                    <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.importUrl')}</FormLabel>
                    <VariablesPopover includeProfileTitle={true} />
                  </div>
                  <Input
                    value={newAppImportUrl}
                    onChange={e => setNewAppImportUrl(e.target.value)}
                    placeholder={t('settings.subscriptions.applications.importUrlPlaceholder')}
                    className="h-8 font-mono text-xs"
                    dir="ltr"
                  />
                  <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.applications.importUrlDescription')}</FormDescription>
                </div>

                {/* Description (multilang) */}
                <div className="space-y-1 sm:col-span-2">
                  <FormLabel className="text-xs text-muted-foreground/80">{t('settings.subscriptions.applications.descriptionApp')}</FormLabel>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Select value={newDescLang} onValueChange={(v: SubscriptionLanguage) => setNewDescLang(v)}>
                      <FormControl>
                        <SelectTrigger className="h-8 w-full text-xs sm:w-32">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent className="scrollbar-thin z-[50]">
                        {(['en', 'fa', 'ru', 'zh'] as const).map(lang => (
                          <SelectItem key={lang} value={lang}>
                            <span className="text-xs">{lang.toUpperCase()}</span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Input
                      value={newAppDescription?.[newDescLang] || ''}
                      onChange={e => setNewAppDescription(prev => ({ ...(prev || {}), [newDescLang]: e.target.value }))}
                      placeholder={t('settings.subscriptions.applications.descriptionPlaceholder', { lang: newDescLang.toUpperCase() })}
                      className="h-8 flex-1 min-w-0 text-xs"
                    />
                  </div>
                </div>

                {/* Recommended toggle */}
                <div className="sm:col-span-2">
                  <div className="flex items-center justify-between space-y-0 rounded-lg border bg-card p-3">
                    <div className="space-y-0.5">
                      <FormLabel className="text-xs font-medium">{t('settings.subscriptions.applications.recommended')}</FormLabel>
                      <FormDescription className="text-xs text-muted-foreground">{t('settings.subscriptions.applications.recommendedDescription')}</FormDescription>
                    </div>
                    <Switch checked={newAppRecommended} onCheckedChange={setNewAppRecommended} />
                  </div>
                </div>

                {/* Initial Download Link */}
                <div className="space-y-1 sm:col-span-2">
                  <FormLabel className="text-xs font-medium text-muted-foreground/80">{t('settings.subscriptions.applications.downloadLinks')} (1)</FormLabel>
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Input
                      value={newLinkName}
                      onChange={e => setNewLinkName(e.target.value)}
                      placeholder={t('settings.subscriptions.applications.downloadLinkNamePlaceholder')}
                      className="h-8 flex-1 min-w-0 text-xs"
                    />
                    <Input
                      value={newLinkUrl}
                      onChange={e => setNewLinkUrl(e.target.value)}
                      placeholder={t('settings.subscriptions.applications.downloadLinkUrlPlaceholder')}
                      className="h-8 flex-1 min-w-0 font-mono text-xs"
                      dir="ltr"
                    />
                    <Select value={newLinkLang} onValueChange={(v: SubscriptionLanguage) => setNewLinkLang(v)}>
                      <FormControl>
                        <SelectTrigger className="h-8 w-full text-xs sm:w-28">
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent className="scrollbar-thin z-[50]">
                        {(['en', 'fa', 'ru', 'zh'] as const).map(l => (
                          <SelectItem key={l} value={l}>
                            <span className="text-xs">{l.toUpperCase()}</span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            </div>
            <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button type="button" variant="outline" onClick={() => setIsAddAppOpen(false)} disabled={isSaving} className="w-full sm:w-auto">
                {t('cancel')}
              </Button>
              <Button type="button" onClick={handleConfirmCreateApplication} disabled={isSaving} className="w-full sm:w-auto">
                {t('create')}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </Form>
    </div>
  )
}

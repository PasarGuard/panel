import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useGetUserSubUpdateList, UserSubscriptionUpdateSchema } from '@/service/api'
import { parseUserAgent, formatClientInfo } from '@/utils/userAgentParser'
import { dateUtils } from '@/utils/dateFormatter'
import { Monitor, Smartphone, Globe, HelpCircle, Users, Loader2, ChevronLeft, ChevronRight } from 'lucide-react'
import { FC, useState } from 'react'
import { useTranslation } from 'react-i18next'
import dayjs from '@/lib/dayjs'
import useDirDetection from '@/hooks/use-dir-detection'

interface UserSubscriptionClientsModalProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  username: string
}

// Function to format time ago
const formatTimeAgo = (timestamp: number, t: (key: string, options?: Record<string, unknown>) => string): string => {
  const currentTime = dayjs()
  const pastTime = dateUtils.toDayjs(timestamp)
  const diffInSeconds = currentTime.diff(pastTime, 'seconds')

  if (diffInSeconds <= 60) {
    return t('justNow', { defaultValue: 'Just now' })
  }

  // Use calendar-aware diff methods for accurate calculations
  // pastTime is always earlier than currentTime
  const years = Math.abs(currentTime.diff(pastTime, 'year'))
  const months = Math.abs(currentTime.diff(pastTime.add(years, 'year'), 'month'))
  const days = Math.abs(currentTime.diff(pastTime.add(years, 'year').add(months, 'month'), 'day'))
  const hours = Math.abs(currentTime.diff(pastTime.add(years, 'year').add(months, 'month').add(days, 'day'), 'hour'))
  const minutes = Math.abs(currentTime.diff(pastTime.add(years, 'year').add(months, 'month').add(days, 'day').add(hours, 'hour'), 'minute'))
  const seconds = Math.abs(currentTime.diff(pastTime.add(years, 'year').add(months, 'month').add(days, 'day').add(hours, 'hour').add(minutes, 'minute'), 'second'))

  let timeText = ''

  if (years > 0) {
    timeText = `${years} ${t(`time.${years !== 1 ? 'years' : 'year'}`)} ${t('time.ago')}`
  } else if (months > 0) {
    timeText = `${months} ${t(`time.${months !== 1 ? 'months' : 'month'}`)} ${t('time.ago')}`
  } else if (days > 0) {
    timeText = `${days} ${t(`time.${days !== 1 ? 'days' : 'day'}`)} ${t('time.ago')}`
  } else if (hours > 0) {
    timeText = `${hours} ${t(`time.${hours !== 1 ? 'hours' : 'hour'}`)} ${t('time.ago')}`
  } else if (minutes > 0) {
    timeText = `${minutes} ${t(`time.${minutes !== 1 ? 'mins' : 'min'}`)} ${t('time.ago')}`
  } else {
    timeText = `${seconds} ${t(`time.${seconds !== 1 ? 'seconds' : 'second'}`)} ${t('time.ago')}`
  }

  return timeText
}

// Get the appropriate icon for the client type
const getClientIcon = (iconType: string) => {
  switch (iconType) {
    case 'desktop':
      return Monitor
    case 'mobile':
      return Smartphone
    case 'browser':
      return Globe
    default:
      return HelpCircle
  }
}

// Get OS badge color
const getOSBadgeColor = (os: string) => {
  switch (os.toLowerCase()) {
    case 'windows':
      return 'bg-blue-500 hover:bg-blue-600'
    case 'macos':
      return 'bg-gray-500 hover:bg-gray-600'
    case 'android':
      return 'bg-green-500 hover:bg-green-600'
    case 'ios':
      return 'bg-purple-500 hover:bg-purple-600'
    case 'linux':
      return 'bg-orange-500 hover:bg-orange-600'
    case 'ubuntu':
      return 'bg-orange-600 hover:bg-orange-700'
    case 'debian':
      return 'bg-red-500 hover:bg-red-600'
    case 'centos':
      return 'bg-purple-600 hover:bg-purple-700'
    case 'rhel':
      return 'bg-red-600 hover:bg-red-700'
    case 'fedora':
      return 'bg-blue-600 hover:bg-blue-700'
    case 'opensuse':
      return 'bg-green-600 hover:bg-green-700'
    case 'arch':
      return 'bg-blue-700 hover:bg-blue-800'
    case 'manjaro':
      return 'bg-emerald-600 hover:bg-emerald-700'
    case 'gentoo':
      return 'bg-purple-700 hover:bg-purple-800'
    case 'slackware':
      return 'bg-blue-800 hover:bg-blue-900'
    case 'chrome os':
      return 'bg-yellow-600 hover:bg-yellow-700'
    case 'freebsd':
      return 'bg-red-700 hover:bg-red-800'
    case 'openbsd':
      return 'bg-orange-700 hover:bg-orange-800'
    case 'netbsd':
      return 'bg-yellow-700 hover:bg-yellow-800'
    case 'solaris':
      return 'bg-orange-800 hover:bg-orange-900'
    case 'hp-ux':
      return 'bg-gray-600 hover:bg-gray-700'
    case 'aix':
      return 'bg-indigo-600 hover:bg-indigo-700'
    default:
      return 'bg-gray-400 hover:bg-gray-500'
  }
}

// Improved OS detection from user agent and client info
const detectOS = (userAgent: string, clientInfo?: { name: string; isKnownClient: boolean }): string => {
  const ua = userAgent.toLowerCase()

  // PRIORITY 1: User agent string analysis (most reliable)
  // Check specific distributions first (most specific to least specific)
  if (ua.includes('ubuntu')) return 'Ubuntu'
  if (ua.includes('debian')) return 'Debian'
  if (ua.includes('centos')) return 'CentOS'
  if (ua.includes('rhel') || ua.includes('red hat')) return 'RHEL'
  if (ua.includes('fedora')) return 'Fedora'
  if (ua.includes('opensuse') || ua.includes('suse')) return 'openSUSE'
  if (ua.includes('arch')) return 'Arch'
  if (ua.includes('manjaro')) return 'Manjaro'
  if (ua.includes('gentoo')) return 'Gentoo'
  if (ua.includes('slackware')) return 'Slackware'

  // iOS detection (comprehensive)
  if (
    ua.includes('iphone') ||
    ua.includes('ipad') ||
    ua.includes('ipod') ||
    ua.includes('ios') ||
    ua.includes('darwin') ||
    ua.includes('cfnetwork') ||
    (ua.includes('mobile safari') && (ua.includes('version/') || ua.includes('cpu iphone os')))
  )
    return 'iOS'

  // Android detection
  if (ua.includes('android')) return 'Android'

  // Windows detection (comprehensive)
  if (ua.includes('windows nt') || ua.includes('windows phone') || ua.includes('win32') || ua.includes('win64') || (ua.includes('windows') && !ua.includes('windows phone'))) return 'Windows'

  // macOS detection (comprehensive)
  if (ua.includes('mac os x') || ua.includes('macos') || ua.includes('macintosh') || ua.includes('mac_powerpc') || ua.includes('macintel')) return 'macOS'

  // Chrome OS detection
  if (ua.includes('cros') || ua.includes('chromebook')) return 'Chrome OS'

  // BSD variants
  if (ua.includes('freebsd')) return 'FreeBSD'
  if (ua.includes('openbsd')) return 'OpenBSD'
  if (ua.includes('netbsd')) return 'NetBSD'

  // Generic Linux (must be last among Linux variants)
  if (ua.includes('linux') && !ua.includes('android')) return 'Linux'

  // Other platforms
  if (ua.includes('solaris') || ua.includes('sunos')) return 'Solaris'
  if (ua.includes('hp-ux') || ua.includes('hpu')) return 'HP-UX'
  if (ua.includes('aix')) return 'AIX'

  // PRIORITY 2: Client app knowledge (fallback when UA doesn't give clear OS)
  if (clientInfo?.isKnownClient) {
    const clientName = clientInfo.name.toLowerCase()

    // Android-only clients
    if (['v2rayng', 'pharos', 'napsternetv', 'oneclick', 'matsuri', 'sagernet', 'nekobox', 'foxray', 'xraypb'].includes(clientName)) {
      return 'Android'
    }

    // iOS-only clients
    if (['shadowrocket', 'quantumult', 'surge'].includes(clientName)) {
      return 'iOS'
    }

    // Windows-only clients
    if (clientName === 'v2rayn') {
      return 'Windows'
    }

    // Linux-only clients
    if (clientName === 'streisand') {
      return 'Linux'
    }

    // Cross-platform clients - use as last resort
    if (clientName === 'v2box' || ['hiddify', 'fairvpn'].includes(clientName)) {
      // Default assumptions for cross-platform apps when UA doesn't specify
      return 'Android' // Most common platform for these apps
    }
  }

  return 'Unknown'
}

// Improved version detection from user agent
const detectVersion = (userAgent: string): string => {
  const ua = userAgent

  // Try to find version patterns
  const patterns = [/(?:v|version|ver)\s*(\d+\.\d+\.\d+)/i, /(\d+\.\d+\.\d+)/, /(?:v|version|ver)\s*(\d+\.\d+)/i, /(\d+\.\d+)/, /(?:v|version|ver)\s*(\d+)/i, /(\d+)/]

  for (const pattern of patterns) {
    const match = ua.match(pattern)
    if (match && match[1]) {
      // For iOS CFNetwork, extract the app version (first number)
      if (ua.includes('cfnetwork')) {
        const appVersionMatch = ua.match(/^([^\/]+)\/(\d+)/i)
        if (appVersionMatch && appVersionMatch[2]) {
          return appVersionMatch[2]
        }
      }
      return match[1]
    }
  }

  // Special handling for CFNetwork format
  if (ua.includes('cfnetwork')) {
    const appVersionMatch = ua.match(/^([^\/]+)\/(\d+)/i)
    if (appVersionMatch && appVersionMatch[2]) {
      return appVersionMatch[2]
    }
  }

  return 'Unknown'
}

export const UserSubscriptionClientsModal: FC<UserSubscriptionClientsModalProps> = ({ isOpen, onOpenChange, username }) => {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [currentPage, setCurrentPage] = useState(0)
  const itemsPerPage = 20

  const {
    data: subUpdateList,
    isLoading,
    error,
  } = useGetUserSubUpdateList(
    username,
    { offset: currentPage * itemsPerPage, limit: itemsPerPage },
    {
      query: {
        enabled: isOpen && !!username,
      },
    },
  )

  const renderClientCard = (update: UserSubscriptionUpdateSchema, index: number) => {
    const clientInfo = parseUserAgent(update.user_agent)
    const formattedClient = formatClientInfo(clientInfo)
    const ClientIcon = getClientIcon(clientInfo.iconType)

    // Convert created_at to timestamp if it's a string
    let timestamp: number | null = null
    if (update.created_at) {
      if (typeof update.created_at === 'string') {
        // Use dateUtils to properly convert ISO string to timestamp
        timestamp = dateUtils.toDayjs(update.created_at).unix()
      } else if (typeof update.created_at === 'number') {
        timestamp = update.created_at
      }
    }

    const timeAgo = timestamp ? formatTimeAgo(timestamp, t) : null

    // Extract version and OS from user agent
    const version = detectVersion(update.user_agent)
    const os = detectOS(update.user_agent, clientInfo)

    return (
      <div key={index} className="rounded-lg border bg-card p-4 transition-colors hover:bg-accent/50" dir={dir}>
        <div className={`mb-3 flex items-start justify-between ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
          <div className={`flex items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
            <ClientIcon className="h-5 w-5 flex-shrink-0 text-muted-foreground" />
            <span className="text-sm font-medium" dir="ltr">
              {formattedClient}
            </span>
          </div>
          <span dir={dir} className="whitespace-nowrap text-xs text-muted-foreground">
            {timeAgo || t('subscriptionClients.unknown', { defaultValue: 'Unknown' })}
          </span>
        </div>

        <div className="flex gap-2">
          <Badge variant="secondary" className="bg-orange-500 text-xs text-white hover:bg-orange-600">
            v{version}
          </Badge>
          <Badge variant="secondary" className={`text-xs text-white ${getOSBadgeColor(os)}`}>
            {os}
          </Badge>
        </div>

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <p className="mt-2 cursor-help truncate text-xs text-muted-foreground" dir="ltr">
                {update.user_agent}
              </p>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-xs">
              <p className="break-all text-xs" dir="ltr">
                {update.user_agent}
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    )
  }

  // Pagination handlers
  const totalPages = subUpdateList ? Math.ceil(subUpdateList.count / itemsPerPage) : 0
  const hasNextPage = currentPage < totalPages - 1
  const hasPrevPage = currentPage > 0

  const handleNextPage = () => {
    if (hasNextPage) {
      setCurrentPage(prev => prev + 1)
    }
  }

  const handlePrevPage = () => {
    if (hasPrevPage) {
      setCurrentPage(prev => prev - 1)
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[95vh] max-w-4xl flex-col sm:max-h-[600px]" dir={dir}>
        <DialogHeader>
          <DialogTitle className={`flex items-center gap-2`}>
            <Users className="h-5 w-5 flex-shrink-0" />
            <span>{t('subscriptionClients.title', { defaultValue: 'Subscription Clients' })}</span>
            <Badge variant="outline" dir="ltr" className="flex-shrink-0">
              {username}
            </Badge>
          </DialogTitle>
        </DialogHeader>

        {/* Content Area */}
        <div className="min-h-0 flex-1 overflow-hidden">
          {isLoading && (
            <div className={`flex items-center justify-center py-8 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
              <Loader2 className="h-6 w-6 flex-shrink-0 animate-spin" />
              <span className={`${dir === 'rtl' ? 'mr-2' : 'ml-2'}`}>{t('loading', { defaultValue: 'Loading...' })}</span>
            </div>
          )}

          {error && <div className="py-8 text-center text-destructive">{t('subscriptionClients.error', { defaultValue: 'Failed to load subscription clients' })}</div>}

          {!isLoading && !error && subUpdateList && (
            <>
              <div className={`flex items-center justify-between py-4 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                <span className="text-sm text-muted-foreground">
                  {t('subscriptionClients.total', {
                    defaultValue: 'Total: {{count}} clients',
                    count: subUpdateList.count,
                  })}
                </span>
                <div className={`flex items-center gap-2 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
                  {totalPages > 1 && (
                    <span className="text-xs text-muted-foreground" dir="ltr">
                      {currentPage + 1} / {totalPages}
                    </span>
                  )}
                </div>
              </div>

              <div className="max-h-[300px] overflow-y-auto sm:max-h-[400px]">
                {subUpdateList.updates && subUpdateList.updates.length > 0 ? (
                  <div className="grid grid-cols-1 gap-4 p-1 sm:grid-cols-2 lg:grid-cols-3">{subUpdateList.updates.map((update, index) => renderClientCard(update, index))}</div>
                ) : (
                  <div className="flex items-center justify-center py-8 text-muted-foreground">
                    <div className="text-center">
                      <Users className="mx-auto mb-2 h-12 w-12 opacity-50" />
                      <p className="text-sm">
                        {t('subscriptionClients.noClients', {
                          defaultValue: 'No subscription clients found',
                        })}
                      </p>
                      <p className="mt-1 text-xs">
                        {t('subscriptionClients.noClientsDesc', {
                          defaultValue: 'This user has not accessed their subscription yet',
                        })}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className={`flex items-center justify-between border-t py-3 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
            <Button variant="outline" size="sm" onClick={handlePrevPage} disabled={!hasPrevPage || isLoading} className={`flex items-center gap-1 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
              <ChevronLeft className="h-4 w-4" />
              {t('previous', { defaultValue: 'Previous' })}
            </Button>

            <span className="text-sm text-muted-foreground" dir="ltr">
              {currentPage + 1} / {totalPages}
            </span>

            <Button variant="outline" size="sm" onClick={handleNextPage} disabled={!hasNextPage || isLoading} className={`flex items-center gap-1 ${dir === 'rtl' ? 'flex-row-reverse' : 'flex-row'}`}>
              {t('next', { defaultValue: 'Next' })}
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        <div className={`flex ${dir === 'rtl' ? 'justify-start' : 'justify-end'}`}>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('close', { defaultValue: 'Close' })}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

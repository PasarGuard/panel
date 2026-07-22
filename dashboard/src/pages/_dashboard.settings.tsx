import PageHeader from '@/components/layout/page-header'
import { useAdmin } from '@/hooks/use-admin'
import { cn } from '@/lib/utils'
import { getGetGeneralSettingsQueryKey, getGetSettingsQueryKey, useGetSettings, useModifySettings } from '@/service/api'
import { useQueryClient } from '@tanstack/react-query'
import { Bell, Database, Fingerprint, ListTodo, LucideIcon, Palette, Send, Settings as SettingsIcon, Webhook } from 'lucide-react'
import { createContext, useCallback, useContext, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Outlet, useLocation, useNavigate } from 'react-router'
import { toast } from 'sonner'
import { hasPermission } from '@/utils/rbac'

interface Tab {
  id: string
  label: string
  icon: LucideIcon
  url: string
}

// Create context for settings
interface SettingsContextType {
  settings: any
  isLoading: boolean
  error: any
  updateSettings: (data: any) => Promise<void>
  isSaving: boolean
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined)

export const useSettingsContext = () => {
  const context = useContext(SettingsContext)
  if (!context) {
    throw new Error('useSettingsContext must be used within SettingsProvider')
  }
  return context!
}

const allTabs: Tab[] = [
  { id: 'general', label: 'settings.general.title', icon: SettingsIcon, url: '/settings/general' },
  { id: 'notifications', label: 'settings.notifications.title', icon: Bell, url: '/settings/notifications' },
  { id: 'subscriptions', label: 'settings.subscriptions.title', icon: ListTodo, url: '/settings/subscriptions' },
  { id: 'hwid', label: 'settings.hwid.title', icon: Fingerprint, url: '/settings/hwid' },
  { id: 'telegram', label: 'settings.telegram.title', icon: Send, url: '/settings/telegram' },
  { id: 'webhook', label: 'settings.webhook.title', icon: Webhook, url: '/settings/webhook' },
  { id: 'cleanup', label: 'settings.cleanup.title', icon: Database, url: '/settings/cleanup' },
  { id: 'theme', label: 'theme.title', icon: Palette, url: '/settings/theme' },
]

export default function Settings() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const { admin } = useAdmin()
  const canUpdateSettings = hasPermission(admin, 'settings', 'update')
  const canReadSettings = hasPermission(admin, 'settings', 'read') && canUpdateSettings
  const canReadGeneral = hasPermission(admin, 'settings', 'read_general') && canUpdateSettings
  const tabs = allTabs.filter(tab => {
    if (tab.id === 'theme') return true
    if (tab.id === 'general') return canReadGeneral
    return canReadSettings
  })

  // Derive activeTab from current location instead of state
  const currentTab = tabs.find(tab => location.pathname === tab.url)
  const activeTab = currentTab?.id || (canReadGeneral ? 'general' : 'theme')

  const queryClient = useQueryClient()

  // Only fetch settings for sudo admins (non-sudo admins only need theme settings which are client-side)
  const {
    data: settings,
    isLoading,
    error,
  } = useGetSettings({
    query: {
      enabled: canReadSettings,
    },
  })
  const { mutateAsync: modifySettingsAsync, isPending: isSaving } = useModifySettings({
    mutation: {
      onSuccess: updatedSettings => {
        toast.success(t(`settings.${activeTab}.saveSuccess`))
        queryClient.setQueryData(getGetSettingsQueryKey(), updatedSettings)
        if (updatedSettings?.general) {
          queryClient.setQueryData(getGetGeneralSettingsQueryKey(), updatedSettings.general)
        }
        // Invalidate settings query to refresh with new data from API response
        queryClient.invalidateQueries({ queryKey: ['/api/settings'] })
        queryClient.invalidateQueries({ queryKey: ['/api/settings/general'] })
      },
      onError: (error: any) => {
        // Extract validation errors from FetchError
        let errorMessage = t(`settings.${activeTab}.saveFailed`)

        // Helper function to extract nested error messages
        const extractErrorMessages = (obj: any, prefix = ''): string[] => {
          const messages: string[] = []

          if (typeof obj === 'string') {
            messages.push(prefix ? `${prefix}: ${obj}` : obj)
          } else if (Array.isArray(obj)) {
            obj.forEach((item, index) => {
              messages.push(...extractErrorMessages(item, `${prefix}[${index}]`))
            })
          } else if (obj && typeof obj === 'object') {
            Object.entries(obj).forEach(([key, value]) => {
              const newPrefix = prefix ? `${prefix}.${key}` : key
              messages.push(...extractErrorMessages(value, newPrefix))
            })
          }

          return messages
        }

        // For FetchError from ofetch/nuxt
        if (error?.data?.detail) {
          const detail = error.data.detail
          const extractedMessages = extractErrorMessages(detail)
          if (extractedMessages.length > 0) {
            errorMessage = extractedMessages.join(', ')
          }
        }
        // Fallback for other error structures
        else if (error?.response?.data?.detail) {
          const detail = error.response.data.detail
          const extractedMessages = extractErrorMessages(detail)
          if (extractedMessages.length > 0) {
            errorMessage = extractedMessages.join(', ')
          }
        }
        // Fallback to error message
        else if (error?.message) {
          errorMessage = error.message
        }

        toast.error(t(`settings.${activeTab}.saveFailed`), {
          description: errorMessage,
        })
      },
    },
  })

  // Wrapper function to filter data based on active tab (only for sudo admins)
  const handleUpdateSettings = useCallback(
    async (data: any) => {
      if (!canReadSettings && !canReadGeneral) return

      let filteredData: any = {}

      // Only include data relevant to the active tab
      switch (activeTab) {
        case 'notifications':
          if (data.data) {
            // If data is already wrapped, use it as is
            filteredData = data
          } else {
            // Wrap notification data in the expected format
            filteredData = {
              data: {
                notification_enable: data.notification_enable,
                notification_settings: data.notification_settings,
              },
            }
          }
          break
        case 'subscriptions':
          if (data.subscription) {
            // Wrap subscription data in the expected format
            filteredData = {
              data: {
                subscription: data.subscription,
              },
            }
          } else {
            // If data is already wrapped, use it as is
            filteredData = data
          }
          break
        case 'hwid':
          filteredData = data.hwid ? { data: { hwid: data.hwid } } : data
          break
        case 'telegram':
          // Add telegram specific filtering if needed
          filteredData = { data: data }
          break
        case 'webhook':
          // Add webhook specific filtering if needed
          filteredData = { data: data }
          break
        case 'cleanup':
          // Add cleanup specific filtering if needed
          filteredData = { data: data }
          break
        case 'theme':
          // Theme settings are client-side only, no API call needed
          return
        default:
          filteredData = { data: data }
      }

      await modifySettingsAsync(filteredData)
    },
    [canReadSettings, canReadGeneral, activeTab, modifySettingsAsync],
  )

  // Memoize context value to ensure stability during HMR
  const settingsContextValue: SettingsContextType = useMemo(
    () => ({
      settings: canReadSettings ? settings || {} : {},
      isLoading: canReadSettings ? isLoading : false,
      error: canReadSettings ? error : null,
      updateSettings: canReadSettings || canReadGeneral ? handleUpdateSettings : async () => {},
      isSaving: canReadSettings || canReadGeneral ? isSaving : false,
    }),
    [canReadSettings, canReadGeneral, settings, isLoading, error, isSaving, handleUpdateSettings],
  )

  // Always render the provider to ensure context is available for child routes
  // This prevents issues during HMR when components might render before parent is ready
  return (
    <SettingsContext.Provider value={settingsContextValue}>
      <div className="flex w-full flex-col items-start gap-0">
        <PageHeader title={t(`settings.${activeTab}.title`)} description="manageSettings" />

        <div className="relative w-full">
          <div className="flex">
            <div className="w-full">
              <div className="scrollbar-hide flex overflow-x-auto border-b px-4 lg:flex-wrap">
                {tabs.map(tab => {
                  const isActive = activeTab === tab.id
                  return (
                    <button
                      key={tab.id}
                      onClick={() => navigate(tab.url)}
                      className={cn(
                        'relative flex-shrink-0 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
                        isActive ? 'border-primary text-foreground border-b-2' : 'text-muted-foreground hover:text-foreground',
                      )}
                    >
                      <div className="flex items-center gap-1.5">
                        <tab.icon className="h-4 w-4" />
                        <span>{t(tab.label)}</span>
                      </div>
                    </button>
                  )
                })}
              </div>
              <div>
                <Outlet />
              </div>
            </div>
          </div>
        </div>
      </div>
    </SettingsContext.Provider>
  )
}

import { SidebarTrigger } from '@/components/ui/sidebar'
import { useVersionCheck } from '@/hooks/use-version-check'
import { getSystemStats } from '@/service/api'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'

export function SidebarTriggerWithBadge() {
  const [currentVersion, setCurrentVersion] = useState<string | null>(null)
  const { hasUpdate, isLoading } = useVersionCheck(currentVersion)

  useEffect(() => {
    const fetchVersion = async () => {
      try {
        const data = await getSystemStats()
        if (data?.version) {
          setCurrentVersion(data.version)
        }
      } catch (error) {
        console.error('Failed to fetch version:', error)
      }
    }
    fetchVersion()
  }, [])

  // Show badge when there's an update available
  // The badge is especially important when sidebar is closed/collapsed, but we show it always for visibility
  const showBadge = !isLoading && hasUpdate

  return (
    <div className="relative inline-block">
      <SidebarTrigger />
      {showBadge && (
        <span
          className={cn(
            'absolute -top-1 -right-1 h-3 w-3 rounded-full',
            'bg-amber-500 dark:bg-amber-400',
            'border-2 border-background'
          )}
          aria-label="Update available"
        />
      )}
    </div>
  )
}


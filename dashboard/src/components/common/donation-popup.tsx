import { Heart, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { getAuthToken } from '@/utils/authStorage'

const DONATION_STORAGE_KEY = 'donation_popup_data'
const FIRST_SHOW_DELAY = 10 * 60 * 1000 // 10 minutes in milliseconds
const SUBSEQUENT_SHOW_DELAY = 5000 // 5 seconds for subsequent shows
const SECRET_SALT = 'pasarguard_donation_v1' // Simple salt for checksum

interface DonationData {
  lastShown: string | null
  nextShowTime: string
  showCount: number
  checksum: string
}

// Calculate delay in days based on show count (progressive delays)
const getDelayDays = (showCount: number): number => {
  switch (showCount) {
    case 0:
      return 3 // First show: 3 days
    case 1:
      return 7 // Second show: 7 days
    case 2:
      return 14 // Third show: 14 days
    default:
      return 30 // Fourth show and beyond: 30 days (1 month)
  }
}

// Simple hash function for tamper detection
const generateChecksum = (lastShown: string | null, nextShowTime: string, showCount: number): string => {
  const data = `${lastShown || 'null'}_${nextShowTime}_${showCount}_${SECRET_SALT}`
  let hash = 0
  for (let i = 0; i < data.length; i++) {
    const char = data.charCodeAt(i)
    hash = (hash << 5) - hash + char
    hash = hash & hash // Convert to 32-bit integer
  }
  return Math.abs(hash).toString(36)
}

// Validate data integrity and reasonableness
const validateData = (data: DonationData): boolean => {
  // Check checksum
  const expectedChecksum = generateChecksum(data.lastShown, data.nextShowTime, data.showCount ?? 0)
  if (data.checksum !== expectedChecksum) {
    console.warn('Donation popup: Data tampering detected (checksum mismatch)')
    return false
  }

  // Validate showCount is a non-negative integer
  if (typeof data.showCount !== 'number' || data.showCount < 0 || !Number.isInteger(data.showCount)) {
    console.warn('Donation popup: Invalid showCount')
    return false
  }

  // Validate timestamps are valid dates
  const nextShowTimestamp = new Date(data.nextShowTime).getTime()
  if (isNaN(nextShowTimestamp)) {
    console.warn('Donation popup: Invalid nextShowTime format')
    return false
  }

  if (data.lastShown) {
    const lastShownTimestamp = new Date(data.lastShown).getTime()
    if (isNaN(lastShownTimestamp)) {
      console.warn('Donation popup: Invalid lastShown format')
      return false
    }

    // Validate relationship: nextShowTime should be after lastShown
    if (nextShowTimestamp < lastShownTimestamp) {
      console.warn('Donation popup: nextShowTime is before lastShown')
      return false
    }

    // Validate: nextShowTime should match expected delay based on showCount
    const expectedDelayDays = getDelayDays(data.showCount)
    const maxExpectedNext = lastShownTimestamp + (expectedDelayDays + 1) * 24 * 60 * 60 * 1000 // +1 day buffer
    if (nextShowTimestamp > maxExpectedNext) {
      console.warn('Donation popup: nextShowTime too far in future')
      return false
    }
  }

  // Validate: nextShowTime shouldn't be more than 1 year in the past or future from now
  const now = Date.now()
  const oneYearAgo = now - 365 * 24 * 60 * 60 * 1000
  const oneYearLater = now + 365 * 24 * 60 * 60 * 1000

  if (nextShowTimestamp < oneYearAgo || nextShowTimestamp > oneYearLater) {
    console.warn('Donation popup: nextShowTime outside reasonable range')
    return false
  }

  return true
}

// localStorage helper functions
const setStorageData = (data: Omit<DonationData, 'checksum'>) => {
  const checksum = generateChecksum(data.lastShown, data.nextShowTime, data.showCount ?? 0)
  const fullData: DonationData = { ...data, checksum }
  localStorage.setItem(DONATION_STORAGE_KEY, JSON.stringify(fullData))
}

const getStorageData = (): DonationData | null => {
  const stored = localStorage.getItem(DONATION_STORAGE_KEY)
  if (!stored) return null
  try {
    const data = JSON.parse(stored) as Partial<DonationData>
    // Handle backward compatibility: if showCount is missing, default to 0
    const fullData: DonationData = {
      ...data,
      showCount: data.showCount ?? 0,
    } as DonationData
    // Validate data integrity
    if (!validateData(fullData)) {
      // Tampering detected, clear invalid data
      localStorage.removeItem(DONATION_STORAGE_KEY)
      return null
    }
    return fullData
  } catch {
    return null
  }
}

export default function DonationPopup() {
  const { t } = useTranslation()
  const [isVisible, setIsVisible] = useState(false)
  const [isAnimating, setIsAnimating] = useState(false)

  const showPopup = useCallback(() => {
    const now = Date.now()
    const data = getStorageData()
    const currentShowCount = data?.showCount ?? 0
    
    // Calculate next delay based on current show count
    const delayDays = getDelayDays(currentShowCount)
    const nextShowTime = new Date(now + delayDays * 24 * 60 * 60 * 1000).toISOString()
    
    // Update storage: increment showCount and set nextShowTime based on progressive delay
    setStorageData({
      lastShown: new Date(now).toISOString(),
      nextShowTime,
      showCount: currentShowCount + 1,
    })

    // Make visible immediately
    setIsVisible(true)

    // Start animation after a frame for smooth CSS transition
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setIsAnimating(true)
      })
    })
  }, [])

  useEffect(() => {
    // Don't show popup if user is not authenticated
    if (!getAuthToken()) {
      return
    }

    const checkShouldShow = () => {
      const data = getStorageData()
      const now = Date.now()

      if (!data) {
        // First time - schedule for initial delay and store it with showCount 0
        const nextShowTime = new Date(now + FIRST_SHOW_DELAY).toISOString()
        setStorageData({ lastShown: null, nextShowTime, showCount: 0 })
        setTimeout(() => showPopup(), FIRST_SHOW_DELAY)
        return
      }

      // Check if it's time to show based on stored nextShowTime
      const nextShowTimestamp = new Date(data.nextShowTime).getTime()
      const timeUntilShow = nextShowTimestamp - now

      if (timeUntilShow <= 0) {
        // Time has passed, show immediately (after small delay for UX)
        setTimeout(() => showPopup(), SUBSEQUENT_SHOW_DELAY)
      } else {
        // Schedule for the remaining time
        setTimeout(() => showPopup(), timeUntilShow)
      }
    }

    checkShouldShow()
  }, [showPopup])

  // Don't render popup if user is not authenticated
  if (!getAuthToken()) {
    return null
  }

  const handleClose = () => {
    setIsAnimating(false)
    setTimeout(() => setIsVisible(false), 500)
  }

  const handleDonate = () => {
    window.open('https://donate.pasarguard.org/', '_blank', 'noopener,noreferrer')
    handleClose()
  }

  const handleGitHub = () => {
    window.open('https://github.com/PasarGuard', '_blank', 'noopener,noreferrer')
    handleClose()
  }

  if (!isVisible) return null

  return (
    <div className="pointer-events-none fixed inset-0 z-[100] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className={cn(
          'pointer-events-auto absolute inset-0 bg-black/40 backdrop-blur-sm',
          'will-change-opacity transition-opacity duration-700 ease-in-out',
          isAnimating ? 'opacity-100' : 'opacity-0',
        )}
        onClick={handleClose}
      />

      {/* Popup */}
      <div
        className={cn(
          'pointer-events-auto relative w-full max-w-md',
          'transform transition-all duration-700 ease-out will-change-transform',
          isAnimating ? 'translate-y-0 scale-100 opacity-100' : '-translate-y-8 scale-95 opacity-0',
        )}
      >
        <div className="relative overflow-hidden rounded-2xl border-2 border-primary/20 bg-gradient-to-br from-card via-card to-card/95 shadow-2xl">
          {/* Animated gradient background */}
          <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-transparent to-primary/10" />
          <div className="absolute inset-0 bg-gradient-to-tr from-primary/0 via-primary/5 to-primary/0" />

          {/* Close button */}
          <button onClick={handleClose} className="absolute right-4 top-4 z-10 rounded-full bg-background/80 p-2 transition-all duration-200 hover:scale-110 hover:bg-background" aria-label="Close">
            <X className="h-4 w-4" />
          </button>

          {/* Content */}
          <div className="relative p-8">
            {/* Heart icon with enhanced animation */}
            <div className="mb-6 flex justify-center">
              <div className="relative">
                <div className="absolute inset-0 rounded-full bg-primary/30 blur-xl" />
                <div className="absolute -inset-2 animate-ping rounded-full bg-primary/20" style={{ animationDuration: '2s' }} />
                <div className="relative rounded-full border border-primary/20 bg-gradient-to-br from-primary/20 to-primary/10 p-4 backdrop-blur-sm">
                  <Heart className="h-10 w-10 fill-primary text-primary" />
                </div>
              </div>
            </div>

            {/* Title */}
            <h3 className="mb-3 bg-gradient-to-r from-primary via-primary to-primary/80 bg-clip-text text-center text-2xl font-bold text-transparent">
              {t('donation.title', { defaultValue: 'Support PasarGuard' })}
            </h3>

            {/* Message */}
            <p className="mb-6 px-2 text-center text-sm leading-relaxed text-muted-foreground">
              {t('donation.message', {
                defaultValue: 'Your support helps us improve PasarGuard and build better features for everyone!',
              })}
            </p>

            {/* Action buttons */}
            <div className="flex flex-col gap-3">
              <Button
                onClick={handleDonate}
                size="lg"
                className="w-full bg-gradient-to-r from-primary to-primary/90 font-semibold text-primary-foreground shadow-lg transition-all duration-300 hover:scale-[1.03] hover:from-primary/90 hover:to-primary hover:shadow-xl active:scale-[0.98]"
              >
                <Heart className="mr-2 h-5 w-5 fill-current" />
                {t('donation.donate', { defaultValue: 'Donate Now' })}
              </Button>

              <Button
                onClick={handleGitHub}
                variant="outline"
                size="lg"
                className="w-full border-primary/30 transition-all duration-300 hover:scale-[1.03] hover:border-primary/50 hover:bg-primary/5 active:scale-[0.98]"
              >
                <svg className="mr-2 h-5 w-5" fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
                {t('donation.starOnGitHub', { defaultValue: 'Star on GitHub' })}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

import { Progress } from '@/components/ui/progress'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { useAllGoals } from '@/hooks/use-goal'
import { Target, TrendingUp, Heart, Star, Github } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { useEffect, useState, useRef } from 'react'
import { useSidebar } from '@/components/ui/sidebar'

export function GoalProgress() {
  const { data: goalsData, isLoading, isError } = useAllGoals()
  const { t } = useTranslation()
  const { state, isMobile } = useSidebar()
  const [currentGoalIndex, setCurrentGoalIndex] = useState(0)
  const [isAnimating, setIsAnimating] = useState(false)

  // Gesture refs
  const startX = useRef<number | null>(null)
  const startY = useRef<number | null>(null)
  const endX = useRef<number | null>(null)
  const endY = useRef<number | null>(null)
  const minSwipeDistance = 50

  const pendingGoals = goalsData?.next_pending || []

  useEffect(() => {
    if (pendingGoals.length <= 1) return

    const interval = setInterval(() => {
      setIsAnimating(true)
      setTimeout(() => {
        setCurrentGoalIndex(prev => (prev + 1) % pendingGoals.length)
        setIsAnimating(false)
      }, 150)
    }, 8000)

    return () => clearInterval(interval)
  }, [pendingGoals.length])

  const navigateToGoal = (direction: 'next' | 'prev') => {
    if (pendingGoals.length <= 1) return

    setIsAnimating(true)
    setTimeout(() => {
      setCurrentGoalIndex(prev => {
        if (direction === 'next') {
          return (prev + 1) % pendingGoals.length
        } else {
          return (prev - 1 + pendingGoals.length) % pendingGoals.length
        }
      })
      setIsAnimating(false)
    }, 150)
  }

  const handleStart = (clientX: number, clientY: number) => {
    startX.current = clientX
    startY.current = clientY
    endX.current = null
    endY.current = null
  }

  const handleMove = (clientX: number, clientY: number) => {
    endX.current = clientX
    endY.current = clientY
  }

  const handleEnd = () => {
    if (!startX.current || !endX.current || !startY.current || !endY.current) return

    const distanceX = startX.current - endX.current
    const distanceY = startY.current - endY.current
    const isLeftSwipe = distanceX > minSwipeDistance
    const isRightSwipe = distanceX < -minSwipeDistance
    const isVerticalSwipe = Math.abs(distanceY) > Math.abs(distanceX)

    // Only handle horizontal swipes/drags
    if (isVerticalSwipe) return

    if (isLeftSwipe) {
      navigateToGoal('next')
    } else if (isRightSwipe) {
      navigateToGoal('prev')
    }

    // Reset positions
    startX.current = null
    startY.current = null
    endX.current = null
    endY.current = null
  }

  // Touch event handlers
  const handleTouchStart = (e: React.TouchEvent) => {
    handleStart(e.touches[0].clientX, e.touches[0].clientY)
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    handleMove(e.touches[0].clientX, e.touches[0].clientY)
  }

  const handleTouchEnd = () => {
    handleEnd()
  }

  // Mouse event handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    handleStart(e.clientX, e.clientY)
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (startX.current !== null) {
      handleMove(e.clientX, e.clientY)
    }
  }

  const handleMouseUp = () => {
    handleEnd()
  }

  if (isLoading) {
    return (
      <div className="space-y-2 px-4 py-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-2 w-full" />
        <Skeleton className="h-3 w-32" />
      </div>
    )
  }

  if (isError || !goalsData || pendingGoals.length === 0) {
    return null
  }

  const currentGoal = pendingGoals[currentGoalIndex]
  const isGithubGoal = currentGoal.type === 'github_stars'
  const unitLabel = isGithubGoal ? t('goal.githubStarsUnit', { defaultValue: 'stars' }) : ''
  const goalTarget = currentGoal.price || 0
  const goalCurrent = currentGoal.paid_amount || 0
  const progress = Math.min(goalTarget > 0 ? (goalCurrent / goalTarget) * 100 : 0, 100)
  const remaining = Math.max(goalTarget - goalCurrent, 0)
  const formattedCurrent = isGithubGoal ? `${Math.round(goalCurrent).toLocaleString()} ${unitLabel}` : `$${goalCurrent.toLocaleString()}`
  const formattedTarget = isGithubGoal ? `${Math.round(goalTarget).toLocaleString()} ${unitLabel}` : `$${goalTarget.toLocaleString()}`
  const formattedRemaining = isGithubGoal ? `${Math.max(Math.round(remaining), 0).toLocaleString()} ${unitLabel}` : `$${remaining.toLocaleString()}`
  const progressLabel = isGithubGoal ? t('goal.githubProgress', { defaultValue: 'Star progress' }) : t('goal.progress', { defaultValue: 'Progress' })
  const remainingLabel = t('goal.remaining')
  const ctaLabel = isGithubGoal ? t('donation.starOnGitHub', { defaultValue: 'Star on GitHub' }) : t('goal.contribute')
  const ctaHref = isGithubGoal && currentGoal.repo_owner && currentGoal.repo_name ? `https://github.com/${currentGoal.repo_owner}/${currentGoal.repo_name}` : 'https://donate.pasarguard.org'
  const CtaIcon = isGithubGoal ? Star : Target
  const BadgeIcon = isGithubGoal ? Star : TrendingUp
  const badgeClasses = isGithubGoal ? 'bg-amber-500/20 text-amber-700 dark:text-amber-400' : 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-400'
  const repoInfoAvailable = Boolean(isGithubGoal && currentGoal.repo_owner && currentGoal.repo_name)
  const repoIdentifier = currentGoal.repo_owner && currentGoal.repo_name ? `${currentGoal.repo_owner}/${currentGoal.repo_name}` : 'owner/repo'
  const showRemaining = remaining > 0

  // Collapsed state (desktop only) - simple donate button with popover
  // On mobile, always use expanded UI since there's no collapsed sidebar concept
  if (state === 'collapsed' && !isMobile) {
    const SummaryIcon = isGithubGoal ? Star : Heart
    return (
      <div className="mx-2 mb-2">
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8 rounded-md">
              <SummaryIcon className="h-4 w-4 text-primary" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-80 p-4" side="right" align="start">
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <SummaryIcon className="h-4 w-4 text-primary" />
                <span className="text-sm font-semibold">{currentGoal.name}</span>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{progressLabel}</span>
                  <span className="font-medium">{progress.toFixed(0)}%</span>
                </div>
                <Progress value={progress} className="h-2" />
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-primary">{formattedCurrent}</span>
                  <span className="text-muted-foreground">
                    {t('goal.of')} {formattedTarget}
                  </span>
                </div>
              </div>

              <div className="min-h-[32px]">
                <div
                  className={cn('flex items-center justify-between rounded-md px-3 py-2 text-xs transition-opacity', showRemaining ? 'bg-muted/50 opacity-100' : 'opacity-0')}
                  aria-hidden={!showRemaining}
                >
                  <span className="text-muted-foreground">{remainingLabel}</span>
                  <span className="font-semibold">{formattedRemaining}</span>
                </div>
              </div>

              <Button asChild className="w-full">
                <a href={ctaHref} target="_blank" rel="noopener noreferrer" className="flex items-center justify-center gap-2">
                  <CtaIcon className="h-4 w-4" />
                  {ctaLabel}
                </a>
              </Button>
            </div>
          </PopoverContent>
        </Popover>
      </div>
    )
  }

  // Expanded state - full card
  return (
    <Card
      className="user-select-none mx-2 mb-2 cursor-grab select-none border-primary/20 bg-gradient-to-br from-primary/5 to-primary/10 active:cursor-grabbing dark:from-primary/10 dark:to-primary/20"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp} // Handle mouse leaving the element
    >
      <CardContent className="p-3">
        {/* Goal Content */}
        <div className={cn('space-y-2.5 transition-all duration-300 ease-in-out', isAnimating ? 'translate-y-2 transform opacity-0' : 'translate-y-0 transform opacity-100')}>
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="flex flex-col">
                <span className="text-xs font-medium text-muted-foreground">
                  {t('goal.currentGoal')} ({currentGoalIndex + 1}/{pendingGoals.length})
                </span>
                <span className="line-clamp-1 text-sm font-semibold leading-tight">{currentGoal.name}</span>
                <div className="mt-1 h-4">
                  <div className={cn('flex items-center gap-1 text-[11px] text-muted-foreground transition-opacity', repoInfoAvailable ? 'opacity-100' : 'opacity-0')} aria-hidden={!repoInfoAvailable}>
                    <Github className="h-3 w-3" aria-hidden />
                    <span className="truncate">{repoIdentifier}</span>
                  </div>
                </div>
              </div>
            </div>
            <div className={cn('flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', badgeClasses)}>
              <BadgeIcon className="h-3 w-3" />
              {progress.toFixed(0)}%
            </div>
          </div>

          {/* Progress Bar */}
          <div className="space-y-1">
            <Progress value={progress} className="h-2" />
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-primary">{formattedCurrent}</span>
              <span className="text-muted-foreground">
                {t('goal.of')} {formattedTarget}
              </span>
            </div>
          </div>

          {/* Details */}
          <div className="min-h-[38px]">{currentGoal.detail && <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{currentGoal.detail}</p>}</div>

          {/* Remaining */}
          <div className="min-h-[32px]">
            <div
              className={cn('flex items-center justify-between rounded-md px-2 py-1.5 text-xs transition-opacity', showRemaining ? 'bg-background/50 opacity-100' : 'opacity-0')}
              aria-hidden={!showRemaining}
            >
              <span className="font-medium text-muted-foreground">{remainingLabel}</span>
              <span className="font-semibold text-foreground">{formattedRemaining}</span>
            </div>
          </div>

          {/* CTA Button */}
          <a
            href={ctaHref}
            target="_blank"
            rel="noopener noreferrer"
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-all hover:bg-primary/90 hover:shadow-md"
          >
            <CtaIcon className="h-3.5 w-3.5" />
            {ctaLabel}
          </a>
        </div>
      </CardContent>
    </Card>
  )
}

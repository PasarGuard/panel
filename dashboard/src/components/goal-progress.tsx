import { Progress } from '@/components/ui/progress'
import { Card, CardContent } from '@/components/ui/card'
import { useCurrentGoal } from '@/hooks/use-goal'
import { Target, TrendingUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export function GoalProgress() {
  const { data: goal, isLoading, isError } = useCurrentGoal()
  const { t } = useTranslation()

  if (isLoading) {
    return (
      <div className="space-y-2 px-4 py-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-2 w-full" />
        <Skeleton className="h-3 w-32" />
      </div>
    )
  }

  if (isError || !goal) {
    return null
  }

  const progress = Math.min((goal.paid_amount / goal.price) * 100, 100)
  const remaining = Math.max(goal.price - goal.paid_amount, 0)

  return (
    <Card className="mx-2 mb-2 border-primary/20 bg-gradient-to-br from-primary/5 to-primary/10 dark:from-primary/10 dark:to-primary/20">
      <CardContent className="p-3">
        <div className="space-y-2.5">
          {/* Header */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/20">
                <Target className="h-4 w-4 text-primary" />
              </div>
              <div className="flex flex-col">
                <span className="text-xs font-medium text-muted-foreground">{t('goal.currentGoal')}</span>
                <span className="line-clamp-1 text-sm font-semibold leading-tight">{goal.name}</span>
              </div>
            </div>
            <div
              className={cn(
                'flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
                goal.status === 'completed' ? 'bg-green-500/20 text-green-700 dark:text-green-400' : 'bg-amber-500/20 text-amber-700 dark:text-amber-400'
              )}
            >
              <TrendingUp className="h-3 w-3" />
              {progress.toFixed(0)}%
            </div>
          </div>

          {/* Progress Bar */}
          <div className="space-y-1">
            <Progress value={progress} className="h-2" />
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-primary">
                ${goal.paid_amount.toLocaleString()}
              </span>
              <span className="text-muted-foreground">
                {t('goal.of')} ${goal.price.toLocaleString()}
              </span>
            </div>
          </div>

          {/* Details */}
          {goal.detail && (
            <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
              {goal.detail}
            </p>
          )}

          {/* Remaining */}
          {remaining > 0 && (
            <div className="flex items-center justify-between rounded-md bg-background/50 px-2 py-1.5">
              <span className="text-xs font-medium text-muted-foreground">
                {t('goal.remaining')}
              </span>
              <span className="text-xs font-semibold text-foreground">
                ${remaining.toLocaleString()}
              </span>
            </div>
          )}

          {/* CTA Button */}
          <a
            href="https://donate.pasarguard.org"
            target="_blank"
            rel="noopener noreferrer"
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-all hover:bg-primary/90 hover:shadow-md"
          >
            <Target className="h-3.5 w-3.5" />
            {t('goal.contribute')}
          </a>
        </div>
      </CardContent>
    </Card>
  )
}


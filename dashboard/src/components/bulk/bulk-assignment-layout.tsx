import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ArrowRight, LucideIcon } from 'lucide-react'
import { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface BulkAssignmentLayoutProps {
  sourceTitle: string
  sourceIcon: LucideIcon
  sourceDescription?: string
  sourceContent: ReactNode
  targetTitle: string
  targetIcon: LucideIcon
  targetDescription?: string
  targetContent: ReactNode
  className?: string
}

export function BulkAssignmentLayout({
  sourceTitle,
  sourceIcon: SourceIcon,
  sourceDescription,
  sourceContent,
  targetTitle,
  targetIcon: TargetIcon,
  targetDescription,
  targetContent,
  className,
}: BulkAssignmentLayoutProps) {
  return (
    <div className={cn('flex w-full flex-col gap-3 sm:gap-4 md:gap-5 lg:gap-6', className)}>
      {/* Source Section */}
      <Card className="bg-card transition-shadow hover:shadow-md">
        <CardHeader className="pb-2 sm:pb-3 md:pb-4">
          <CardTitle className="flex items-center gap-1.5 sm:gap-2 text-sm font-semibold sm:text-base md:text-lg">
            <SourceIcon className="h-3.5 w-3.5 sm:h-4 sm:w-4 md:h-5 md:w-5 shrink-0" />
            <span className="truncate">{sourceTitle}</span>
          </CardTitle>
          {sourceDescription && <p className="text-xs text-muted-foreground sm:text-sm mt-1">{sourceDescription}</p>}
        </CardHeader>
        <CardContent className="pt-0 px-3 sm:px-4 md:px-6">{sourceContent}</CardContent>
      </Card>

      {/* Arrow Connector */}
      <div className="flex items-center justify-center py-1 sm:py-2">
        <div className="flex items-center gap-1.5 sm:gap-2 rounded-full bg-primary/10 px-3 py-1.5 sm:px-4 sm:py-2 dark:bg-primary/20">
          <ArrowRight className="h-3.5 w-3.5 sm:h-4 sm:w-4 md:h-5 md:w-5 text-primary" />
          <span className="text-[10px] sm:text-xs md:text-sm font-medium text-primary">Assign To</span>
        </div>
      </div>

      {/* Target Section */}
      <Card className="bg-card transition-shadow hover:shadow-md">
        <CardHeader className="pb-2 sm:pb-3 md:pb-4">
          <CardTitle className="flex items-center gap-1.5 sm:gap-2 text-sm font-semibold sm:text-base md:text-lg">
            <TargetIcon className="h-3.5 w-3.5 sm:h-4 sm:w-4 md:h-5 md:w-5 shrink-0" />
            <span className="truncate">{targetTitle}</span>
          </CardTitle>
          {targetDescription && <p className="text-xs text-muted-foreground sm:text-sm mt-1">{targetDescription}</p>}
        </CardHeader>
        <CardContent className="pt-0 px-3 sm:px-4 md:px-6">{targetContent}</CardContent>
      </Card>
    </div>
  )
}


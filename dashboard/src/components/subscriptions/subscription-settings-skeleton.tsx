import { Skeleton } from '@/components/ui/skeleton'

export function SubscriptionSettingsSkeleton() {
  return (
    <div className="w-full p-4 sm:py-6 lg:py-8">
      <div className="space-y-6 sm:space-y-8 lg:space-y-10">
        <div className="space-y-4 sm:space-y-6">
          <div className="space-y-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-96" />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:gap-6 lg:grid-cols-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-10" />
                <Skeleton className="h-3 w-64" />
              </div>
            ))}
          </div>
          <Skeleton className="h-16" />
        </div>

        <div className="space-y-4 sm:space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
            <div className="space-y-1">
              <Skeleton className="h-6 w-32" />
              <Skeleton className="h-4 w-80" />
            </div>
            <Skeleton className="h-9 w-24" />
          </div>
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {[...Array(2)].map((_, i) => (
              <div key={i} className="rounded-md border bg-card p-3">
                <div className="mb-2 flex items-center justify-between">
                  <Skeleton className="h-4 w-4" />
                  <Skeleton className="h-6 w-6" />
                </div>
                <div className="space-y-2">
                  <div className="space-y-1">
                    <Skeleton className="h-3 w-16" />
                    <Skeleton className="h-8" />
                  </div>
                  <div className="space-y-1">
                    <Skeleton className="h-3 w-12" />
                    <Skeleton className="h-8" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-4 sm:space-y-6">
          <div className="space-y-1">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-72" />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3 lg:gap-6">
            {[...Array(7)].map((_, i) => (
              <Skeleton key={i} className="h-16" />
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-3 pt-4 sm:flex-row sm:gap-4 sm:pt-6">
          <div className="flex-1"></div>
          <div className="flex flex-col gap-3 sm:shrink-0 sm:flex-row sm:gap-4">
            <Skeleton className="h-10 w-24" />
            <Skeleton className="h-10 w-20" />
          </div>
        </div>
      </div>
    </div>
  )
}

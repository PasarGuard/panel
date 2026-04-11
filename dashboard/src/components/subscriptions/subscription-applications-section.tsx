import { SortableApplication } from '@/components/subscriptions/sortable-application'
import type { SubscriptionApplicationFormData, SubscriptionFormData } from '@/components/subscriptions/subscription-settings-schema'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { closestCenter, DndContext, DragEndEvent } from '@dnd-kit/core'
import { rectSortingStrategy, SortableContext } from '@dnd-kit/sortable'
import { Plus, RotateCcw, Settings } from 'lucide-react'
import type { ComponentProps } from 'react'
import type { FieldArrayWithId } from 'react-hook-form'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

const PLATFORM_KEYS = ['ios', 'android', 'windows', 'macos', 'linux', 'appletv', 'androidtv'] as const

type DndContextSensors = NonNullable<ComponentProps<typeof DndContext>['sensors']>

export interface SubscriptionApplicationsSectionProps {
  form: UseFormReturn<SubscriptionFormData>
  applicationFields: FieldArrayWithId<SubscriptionFormData, 'applications'>[]
  sensors: DndContextSensors
  onDragEnd: (event: DragEndEvent) => void
  onLoadOrReset: () => void
  onAddApplication: () => void
  onRemoveApplication: (index: number) => void
}

export function SubscriptionApplicationsSection({
  form,
  applicationFields,
  sensors,
  onDragEnd,
  onLoadOrReset,
  onAddApplication,
  onRemoveApplication,
}: SubscriptionApplicationsSectionProps) {
  const { t } = useTranslation()

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="min-w-0 flex-1 space-y-1">
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
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center sm:gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onLoadOrReset} className="flex w-full shrink-0 items-center justify-center gap-2 sm:w-auto">
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
          <Button type="button" variant="outline" size="sm" onClick={onAddApplication} className="flex w-full shrink-0 items-center justify-center gap-2 sm:w-auto">
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
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
          {PLATFORM_KEYS.map(platformKey => {
            const currentApplications = (form.getValues('applications') || []) as SubscriptionApplicationFormData[]
            const indices = applicationFields.map((f, idx) => ({ id: f.id, idx })).filter(({ idx }) => currentApplications[idx]?.platform === platformKey)
            if (indices.length === 0) return null
            return (
              <SortableContext key={platformKey} items={indices.map(i => i.id)} strategy={rectSortingStrategy}>
                <div className="mb-2 mt-2 flex items-center gap-2 px-1 sm:px-0">
                  <span className="shrink-0 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                    {t(`settings.subscriptions.applications.platforms.${platformKey}`)}
                  </span>
                  <div className="hidden h-px min-w-0 flex-1 bg-border sm:block" />
                </div>
                <div className="grid grid-cols-1 gap-3 sm:gap-4 md:grid-cols-2" dir="ltr">
                  {indices.map(({ id, idx }) => (
                    <SortableApplication key={id} id={id} index={idx} onRemove={onRemoveApplication} form={form} />
                  ))}
                </div>
              </SortableContext>
            )
          })}
        </DndContext>
      )}
    </div>
  )
}

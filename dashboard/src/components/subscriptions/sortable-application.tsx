import { SubscriptionApplicationSheet } from '@/components/subscriptions/subscription-application-sheet'
import type { SubscriptionFormData } from '@/components/subscriptions/subscription-settings-schema'
import { platformOptions, PlatformIcon } from '@/components/subscriptions/subscription-application-shared'
import { Button } from '@/components/ui/button'
import { FormField } from '@/components/ui/form'
import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { GripVertical, Pencil, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { UseFormReturn } from 'react-hook-form'
import { useTranslation } from 'react-i18next'

interface SortableApplicationProps {
  index: number
  onRemove: (index: number) => void
  form: UseFormReturn<SubscriptionFormData>
  id: string
}

export function SortableApplication({ index, onRemove, form, id }: SortableApplicationProps) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id })
  const [isSheetOpen, setIsSheetOpen] = useState(false)
  const [iconBroken, setIconBroken] = useState(false)

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
        <div className="group relative rounded-md border bg-card transition-colors hover:bg-accent/20" dir="ltr">
          <div className="flex items-center gap-2 p-3 sm:gap-3 sm:p-4">
            <button type="button" style={{ cursor: cursor }} className="touch-none shrink-0 opacity-50 transition-opacity group-hover:opacity-100" {...attributes} {...listeners}>
              <GripVertical className="h-4 w-4 sm:h-5 sm:w-5" />
              <span className="sr-only">Drag to reorder</span>
            </button>

            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 sm:gap-2 sm:flex-nowrap">
              {(() => {
                const iconUrl = form.watch(`applications.${index}.icon_url`)
                const name = (form.watch(`applications.${index}.name`) || '').trim()
                const initial = name ? name.charAt(0).toUpperCase() : ''
                const platform = form.watch(`applications.${index}.platform`) ?? ''
                if (iconUrl && !iconBroken) {
                  return (
                    <img
                      src={iconUrl}
                      alt={name || 'icon'}
                      className="h-4 w-4 shrink-0 rounded-sm object-cover sm:h-5 sm:w-5"
                      onError={() => setIconBroken(true)}
                    />
                  )
                }
                return (
                  <span aria-label="app-icon-fallback" className="inline-flex h-4 w-4 shrink-0 items-center justify-center overflow-hidden rounded-sm bg-muted text-muted-foreground/90 sm:h-5 sm:w-5">
                    {initial ? (
                      <span className="text-[10px] font-medium leading-none">{initial}</span>
                    ) : (
                      <span className="text-[10px] leading-none">
                        <PlatformIcon platform={platform} />
                      </span>
                    )}
                  </span>
                )
              })()}
              <FormField
                control={form.control}
                name={`applications.${index}.platform`}
                render={({ field }) => <span className="hidden text-xs text-muted-foreground sm:inline">{t(platformOptions.find(o => o.value === field.value)?.label || '')}</span>}
              />
              <FormField
                control={form.control}
                name={`applications.${index}.platform`}
                render={({ field }) => (
                  <span className="shrink-0 text-muted-foreground/80">
                    <PlatformIcon platform={field.value ?? ''} />
                  </span>
                )}
              />
              <FormField
                control={form.control}
                name={`applications.${index}.name`}
                render={({ field }) => (
                  <h4 className="flex min-w-0 items-center gap-1.5 truncate text-xs font-medium sm:text-sm">
                    {field.value || t('settings.subscriptions.applications.application', { defaultValue: 'Application' })}
                    {form.watch(`applications.${index}.recommended`) ? (
                      <span title={t('settings.subscriptions.applications.recommended')} className="inline-flex shrink-0 items-center text-amber-500/90">
                        <Star className="h-3 w-3 fill-amber-500/30 sm:h-3.5 sm:w-3.5" />
                      </span>
                    ) : null}
                  </h4>
                )}
              />
            </div>

            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0 sm:h-8 sm:w-8"
              onClick={() => setIsSheetOpen(true)}
              aria-label={t('settings.subscriptions.applications.editApplication')}
            >
              <Pencil className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </Button>

            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={e => {
                e.preventDefault()
                e.stopPropagation()
                onRemove(index)
              }}
              className="h-7 w-7 shrink-0 p-0 text-destructive opacity-70 transition-opacity hover:bg-destructive/10 hover:text-destructive hover:opacity-100 sm:h-8 sm:w-8"
            >
              <Trash2 className="h-3.5 w-3.5 sm:h-4 sm:w-4" />
            </Button>
          </div>

          {isDragging && <div className="pointer-events-none absolute inset-0 rounded-md border border-primary/20 bg-primary/5" />}
        </div>
      </div>

      <SubscriptionApplicationSheet
        variant="edit"
        form={form}
        applicationIndex={index}
        rowId={id}
        open={isSheetOpen}
        onOpenChange={setIsSheetOpen}
      />
    </>
  )
}

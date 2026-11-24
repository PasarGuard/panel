import { useEffect, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Columns3, GripVertical, LockKeyhole, Monitor, RotateCcw, Search, Smartphone } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import useDirDetection from '@/hooks/use-dir-detection'
import { cn } from '@/lib/utils'
import { UserTablePreview } from './user-table-preview'
import { defaultUserView, USER_FIELDS, type UserFieldId, type UserViewPreferences } from './user-view-preferences'

type Section = 'desktop' | 'mobileExpanded'

function SortableField({ id, label, checked, onToggle }: { id: UserFieldId; label: string; checked: boolean; onToggle: (checked: boolean) => void }) {
  const { t } = useTranslation()
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({ id, disabled: !checked })
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn('bg-background relative flex items-center gap-2 border-b px-3 py-2 last:border-0', isDragging && 'z-10 rounded-md shadow-lg')}
    >
      <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3 py-1 text-sm">
        <Checkbox checked={checked} onCheckedChange={value => onToggle(!!value)} />
        {label}
      </label>
      {checked && (
        <button
          ref={setActivatorNodeRef}
          type="button"
          className="text-muted-foreground flex h-8 w-8 cursor-grab touch-none items-center justify-center rounded-md outline-none focus-visible:ring-2 active:cursor-grabbing"
          {...attributes}
          {...listeners}
          aria-label={t('usersView.dragField', { field: label })}
        >
          <GripVertical className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}

export function CustomizeUserView({
  value,
  allowedFields,
  canShowCreator,
  onApply,
  onOpenChange,
  renderPreview,
}: {
  value: UserViewPreferences
  allowedFields: UserFieldId[]
  canShowCreator: boolean
  onApply: (value: UserViewPreferences) => void
  onOpenChange: (open: boolean) => void
  renderPreview: (view: UserViewPreferences, mobile: boolean) => ReactNode
}) {
  const { t } = useTranslation()
  const dir = useDirDetection()
  const [open, setOpen] = useState(false)
  useEffect(() => {
    onOpenChange(open)
  }, [open, onOpenChange])
  const [draft, setDraft] = useState(value)
  const [section, setSection] = useState<Section>('desktop')
  const [search, setSearch] = useState('')
  const mobile = section === 'mobileExpanded'
  const selected = draft[section].filter(id => allowedFields.includes(id))
  const ordered = [...selected, ...USER_FIELDS.map(field => field.id).filter(id => allowedFields.includes(id) && !selected.includes(id))]
  const visible = ordered.filter(id => t(`usersView.fields.${id}`).toLocaleLowerCase().includes(search.toLocaleLowerCase().trim()))
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))
  const updateFields = (fields: UserFieldId[]) => setDraft(prev => ({ ...prev, [section]: fields }))
  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return
    const from = draft[section].indexOf(active.id as UserFieldId)
    const to = draft[section].indexOf(over.id as UserFieldId)
    if (from >= 0 && to >= 0) updateFields(arrayMove(draft[section], from, to))
  }

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="h-9 gap-2 px-2.5"
        aria-label={t('usersView.customize')}
        title={t('usersView.customize')}
        onClick={() => {
          setDraft(value)
          setSearch('')
          setSection(window.matchMedia('(max-width: 767px)').matches ? 'mobileExpanded' : 'desktop')
          setOpen(true)
        }}
      >
        <Columns3 className="h-4 w-4" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          dir={dir}
          className="top-auto bottom-0 flex max-h-[92dvh] translate-y-0 flex-col rounded-t-2xl p-4 md:top-1/2 md:bottom-auto md:max-w-4xl md:-translate-y-1/2 md:rounded-xl md:p-6"
        >
          <DialogHeader>
            <DialogTitle>{t('usersView.customize')}</DialogTitle>
            <DialogDescription>{t('usersView.description')}</DialogDescription>
          </DialogHeader>
          <Tabs
            className="flex min-h-0 flex-1 flex-col gap-4"
            value={mobile ? 'mobile' : 'desktop'}
            onValueChange={value => {
              setSection(value === 'mobile' ? 'mobileExpanded' : 'desktop')
              setSearch('')
            }}
            dir={dir}
          >
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="desktop" className="gap-2">
                <Monitor className="h-4 w-4" />
                {t('usersView.desktop')}
              </TabsTrigger>
              <TabsTrigger value="mobile" className="gap-2">
                <Smartphone className="h-4 w-4" />
                {t('usersView.mobile')}
              </TabsTrigger>
            </TabsList>
            <TabsContent value={mobile ? 'mobile' : 'desktop'} className="m-0 min-h-0 space-y-4 overflow-y-auto px-0.5">
              <div className="space-y-2">
                <p className="text-muted-foreground text-xs">{t('usersView.preview')}</p>
                <UserTablePreview mobile={mobile} title={t('usersView.preview')}>
                  {renderPreview(draft, mobile)}
                </UserTablePreview>
              </div>
              <p className="text-muted-foreground text-xs">{t(mobile ? 'usersView.expandedHint' : 'usersView.columnsHint')}</p>
              <div className="bg-muted/30 text-muted-foreground flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5 text-xs">
                <span>{t(mobile ? 'usersView.fixedMobile' : 'usersView.fixedDesktop')}</span>
                <LockKeyhole className="h-3.5 w-3.5 shrink-0" />
              </div>
              {canShowCreator && (
                <label className="flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-3 text-sm">
                  <Checkbox checked={draft.showCreatedBy} onCheckedChange={checked => setDraft(prev => ({ ...prev, showCreatedBy: !!checked }))} />
                  {t('usersView.fields.creator')}
                </label>
              )}
              <div className="relative">
                <Search className="text-muted-foreground absolute start-3 top-2.5 h-4 w-4" />
                <Input value={search} onChange={event => setSearch(event.target.value)} placeholder={t('usersView.search')} aria-label={t('usersView.search')} className="ps-9" />
              </div>
              <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={visible.filter(id => selected.includes(id))} strategy={verticalListSortingStrategy}>
                  <div className="rounded-lg border">
                    {visible.length === 0 && <p className="text-muted-foreground p-4 text-center text-sm">{t('noResults')}</p>}
                    {visible.map(id => (
                      <SortableField
                        key={id}
                        id={id}
                        label={t(`usersView.fields.${id}`)}
                        checked={selected.includes(id)}
                        onToggle={checked => updateFields(checked ? [...draft[section], id] : draft[section].filter(field => field !== id))}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            </TabsContent>
          </Tabs>
          <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-4">
            <Button variant="ghost" size="sm" className="gap-2" onClick={() => setDraft(defaultUserView())}>
              <RotateCcw className="h-3.5 w-3.5" />
              {t('usersView.resetDefaults')}
            </Button>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setOpen(false)}>
                {t('cancel')}
              </Button>
              <Button
                onClick={() => {
                  onApply(draft)
                  setOpen(false)
                }}
              >
                {t('apply')}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

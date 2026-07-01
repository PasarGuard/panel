import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Loader2, Pencil, Plus, Tag as TagIcon, Trash2, X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { HOST_TAG_COLORS, HOST_TAG_COLOR_KEYS, getTagColorStyle } from '@/constants/hostTagColors'
import type { HostTag, HostTagColor } from '@/service/api'
import { useCreateHostTag, useHostTags, useModifyHostTag, useRemoveHostTag } from '@/service/hostTags'

export function TagChip({
  tag,
  onRemove,
  className,
}: {
  tag: Pick<HostTag, 'name' | 'color'>
  onRemove?: () => void
  className?: string
}) {
  const style = getTagColorStyle(tag.color)
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium', style.chip, className)}>
      <span className={cn('h-2 w-2 rounded-full', style.bar)} />
      <span className="max-w-28 truncate">{tag.name}</span>
      {onRemove && (
        <button
          type="button"
          aria-label={`Remove ${tag.name}`}
          onClick={e => {
            e.stopPropagation()
            onRemove()
          }}
          className="-mr-0.5 ml-0.5 rounded-full hover:bg-black/10 dark:hover:bg-white/10"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  )
}

function ColorSwatchRow({ value, onChange }: { value: HostTagColor; onChange: (c: HostTagColor) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {HOST_TAG_COLOR_KEYS.map(key => (
        <button
          key={key}
          type="button"
          title={key}
          onClick={() => onChange(key)}
          className={cn(
            'flex h-6 w-6 items-center justify-center rounded-full ring-offset-background transition',
            HOST_TAG_COLORS[key].bar,
            value === key ? 'ring-2 ring-ring ring-offset-2' : 'opacity-70 hover:opacity-100',
          )}
        >
          {value === key && <Check className="h-3.5 w-3.5 text-white" />}
        </button>
      ))}
    </div>
  )
}

interface HostTagPickerProps {
  value: number[]
  onChange: (ids: number[]) => void
}

export default function HostTagPicker({ value, onChange }: HostTagPickerProps) {
  const { t } = useTranslation()
  const { data: tags = [], isLoading } = useHostTags()
  const createTag = useCreateHostTag()
  const modifyTag = useModifyHostTag()
  const removeTag = useRemoveHostTag()

  const [open, setOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newColor, setNewColor] = useState<HostTagColor>('slate')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editColor, setEditColor] = useState<HostTagColor>('slate')

  const selected = useMemo(() => tags.filter(tag => tag.id != null && value.includes(tag.id)), [tags, value])

  const toggle = (id: number) => onChange(value.includes(id) ? value.filter(x => x !== id) : [...value, id])

  const handleCreate = () => {
    const name = newName.trim()
    if (!name) return
    createTag.mutate(
      { name, color: newColor },
      {
        onSuccess: tag => {
          if (tag.id != null) onChange([...value, tag.id])
          setNewName('')
          setNewColor('slate')
        },
        onError: () => toast.error(t('hostTags.createFailed', { defaultValue: 'Failed to create tag (name may already exist)' })),
      },
    )
  }

  const startEdit = (tag: HostTag) => {
    setEditingId(tag.id ?? null)
    setEditName(tag.name)
    setEditColor(tag.color)
  }

  const saveEdit = () => {
    if (editingId == null) return
    const name = editName.trim()
    if (!name) return
    modifyTag.mutate(
      { tagId: editingId, data: { name, color: editColor } },
      {
        onSuccess: () => setEditingId(null),
        onError: () => toast.error(t('hostTags.updateFailed', { defaultValue: 'Failed to update tag' })),
      },
    )
  }

  const handleRemove = (id: number) => {
    removeTag.mutate(id, {
      onSuccess: () => onChange(value.filter(x => x !== id)),
      onError: () => toast.error(t('hostTags.deleteFailed', { defaultValue: 'Failed to delete tag' })),
    })
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {selected.map(tag => (
        <TagChip key={tag.id} tag={tag} onRemove={() => tag.id != null && toggle(tag.id)} />
      ))}

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="outline" size="sm" className="h-7 gap-1 border-dashed">
            <Plus className="h-3.5 w-3.5" />
            {t('hostTags.addTag', { defaultValue: 'Tag' })}
          </Button>
        </PopoverTrigger>
        <PopoverContent align="start" className="w-72 p-2">
          <div className="mb-2 flex items-center gap-1.5 px-1 text-xs font-medium text-muted-foreground">
            <TagIcon className="h-3.5 w-3.5" />
            {t('hostTags.title', { defaultValue: 'Host tags' })}
          </div>

          <div className="max-h-52 space-y-0.5 overflow-y-auto">
            {isLoading && (
              <div className="flex justify-center p-3">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            )}
            {!isLoading && tags.length === 0 && (
              <div className="px-2 py-3 text-center text-xs text-muted-foreground">
                {t('hostTags.empty', { defaultValue: 'No tags yet. Create one below.' })}
              </div>
            )}
            {tags.map(tag => {
              const id = tag.id
              if (id == null) return null

              if (editingId === id) {
                return (
                  <div key={id} className="rounded-md border p-2">
                    <Input value={editName} onChange={e => setEditName(e.target.value)} className="mb-2 h-7" />
                    <ColorSwatchRow value={editColor} onChange={setEditColor} />
                    <div className="mt-2 flex justify-end gap-1">
                      <Button type="button" variant="ghost" size="sm" className="h-6" onClick={() => setEditingId(null)}>
                        {t('cancel', { defaultValue: 'Cancel' })}
                      </Button>
                      <Button type="button" size="sm" className="h-6" onClick={saveEdit} disabled={modifyTag.isPending}>
                        {t('save', { defaultValue: 'Save' })}
                      </Button>
                    </div>
                  </div>
                )
              }

              const isSel = value.includes(id)
              const style = getTagColorStyle(tag.color)
              return (
                <div key={id} className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent">
                  <button type="button" className="flex min-w-0 flex-1 items-center gap-2" onClick={() => toggle(id)}>
                    <span className={cn('flex h-4 w-4 items-center justify-center rounded-sm border', isSel ? 'border-primary bg-primary text-primary-foreground' : 'border-input')}>
                      {isSel && <Check className="h-3 w-3" />}
                    </span>
                    <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full', style.bar)} />
                    <span className="truncate text-sm">{tag.name}</span>
                  </button>
                  <button type="button" title={t('edit', { defaultValue: 'Edit' })} className="opacity-0 transition group-hover:opacity-100" onClick={() => startEdit(tag)}>
                    <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
                  </button>
                  <button type="button" title={t('delete', { defaultValue: 'Delete' })} className="opacity-0 transition group-hover:opacity-100" onClick={() => handleRemove(id)}>
                    <Trash2 className="h-3.5 w-3.5 text-destructive" />
                  </button>
                </div>
              )
            })}
          </div>

          <div className="mt-2 border-t pt-2">
            <div className="mb-1.5 px-1 text-xs font-medium text-muted-foreground">{t('hostTags.create', { defaultValue: 'Create tag' })}</div>
            <div className="flex items-center gap-1.5">
              <Input
                value={newName}
                onChange={e => setNewName(e.target.value)}
                placeholder={t('hostTags.namePlaceholder', { defaultValue: 'Tag name' })}
                className="h-7"
                onKeyDown={e => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    handleCreate()
                  }
                }}
              />
              <Button
                type="button"
                size="sm"
                className="h-7"
                aria-label={t('hostTags.create', { defaultValue: 'Create tag' })}
                onClick={handleCreate}
                disabled={!newName.trim() || createTag.isPending}
              >
                {createTag.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
              </Button>
            </div>
            <div className="mt-2">
              <ColorSwatchRow value={newColor} onChange={setNewColor} />
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}

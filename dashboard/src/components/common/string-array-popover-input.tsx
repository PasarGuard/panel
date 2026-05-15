import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { Check, Link2, Pencil, Plus, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

interface StringArrayPopoverInputProps {
  value: string[]
  onChange: (next: string[]) => void
  placeholder: string
  disabled?: boolean
  addPlaceholder?: string
  addButtonLabel?: string
  itemsLabel?: string
  emptyMessage?: string
  duplicateErrorMessage?: string
  clickToEditTitle?: string
  editItemTitle?: string
  removeItemTitle?: string
  saveEditTitle?: string
  cancelEditTitle?: string
  className?: string
}

function normalizeItems(value: string[]): string[] {
  return value
}

export function StringArrayPopoverInput({
  value,
  onChange,
  placeholder,
  disabled,
  addPlaceholder = 'Add value',
  addButtonLabel = 'Add',
  itemsLabel = 'Items',
  emptyMessage = 'No items added.',
  duplicateErrorMessage = 'This value already exists.',
  clickToEditTitle = 'Click to edit',
  editItemTitle = 'Edit',
  removeItemTitle = 'Remove',
  saveEditTitle = 'Save',
  cancelEditTitle = 'Cancel',
  className,
}: StringArrayPopoverInputProps) {
  const [inputValue, setInputValue] = useState('')
  const [isPopoverOpen, setIsPopoverOpen] = useState(false)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editingValue, setEditingValue] = useState('')

  const items = normalizeItems(value ?? [])
  const displayValue =
    items.length > 0
      ? items.length <= 3
        ? items.join(', ')
        : `${items.slice(0, 3).join(', ')}... (+${items.length - 3} more)`
      : ''

  const addItem = () => {
    if (disabled) return
    const trimmedValue = inputValue.trim()

    if (items.includes(trimmedValue)) {
      toast.error(duplicateErrorMessage)
      return
    }

    onChange([...items, trimmedValue])
    setInputValue('')
  }

  const removeItem = (index: number) => {
    if (disabled) return
    onChange(items.filter((_, i) => i !== index))
    setEditingIndex(null)
    setEditingValue('')
  }

  const startEdit = (index: number, currentValue: string) => {
    if (disabled) return
    setEditingIndex(index)
    setEditingValue(currentValue)
  }

  const saveEdit = (index: number) => {
    if (disabled) return
    const trimmedValue = editingValue.trim()

    const isDuplicate = items.some((item, i) => i !== index && item === trimmedValue)
    if (isDuplicate) {
      toast.error(duplicateErrorMessage)
      return
    }

    const next = [...items]
    next[index] = trimmedValue
    onChange(next)
    setEditingIndex(null)
    setEditingValue('')
  }

  const cancelEdit = () => {
    setEditingIndex(null)
    setEditingValue('')
  }

  return (
    <Popover
      open={isPopoverOpen}
      onOpenChange={open => {
        if (disabled) return
        if (!open && editingIndex === null) {
          setIsPopoverOpen(false)
        } else if (open) {
          setIsPopoverOpen(true)
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button
          dir="ltr"
          variant="outline"
          role="combobox"
          className={cn('h-auto w-full min-w-0 overflow-hidden justify-between p-2 text-left', className)}
          title={displayValue || placeholder}
          disabled={disabled}
        >
          <span
            className={cn(
              'min-w-0 flex-1 truncate text-start',
              displayValue ? 'text-foreground' : 'text-muted-foreground',
            )}
            title={displayValue || placeholder}
          >
            {displayValue || placeholder}
          </span>
          <div className="ml-2 flex shrink-0 items-center gap-1">
            {items.length > 0 && (
              <Badge variant="secondary" className="px-1.5 py-0.5 text-xs">
                {items.length}
              </Badge>
            )}
            <Link2 className="h-5 w-5 text-muted-foreground" />
          </div>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[min(90vw,400px)] overflow-hidden p-3"
        side="bottom"
        onWheel={e => e.stopPropagation()}
        onTouchMove={e => e.stopPropagation()}
      >
        <div className="flex max-h-[min(70dvh,24rem)] min-h-0 flex-col gap-3 overflow-hidden">
          <div className="m-1.5 flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              placeholder={addPlaceholder}
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && inputValue.trim()) {
                  e.preventDefault()
                  addItem()
                } else if (e.key === 'Escape') {
                  setInputValue('')
                  setIsPopoverOpen(false)
                }
              }}
              className="min-w-0 flex-1 text-sm"
              autoFocus={isPopoverOpen}
              disabled={disabled}
            />
            <Button
              type="button"
              size="sm"
              variant="default"
              onClick={addItem}
              disabled={!inputValue.trim() || disabled}
              className="h-8 w-full shrink-0 justify-start px-3 py-1 sm:w-auto sm:justify-center"
              title={addButtonLabel}
            >
              <Plus className="h-4 w-4" />
              <span className="ml-1 sm:hidden">{addButtonLabel}</span>
            </Button>
          </div>

          {items.length > 0 && (
            <div dir="ltr" className="flex min-h-0 flex-col gap-2">
              <div className="text-xs font-medium text-muted-foreground">
                {itemsLabel} ({items.length})
              </div>
              <div className="min-h-0 max-h-[min(50dvh,14rem)] space-y-1 overflow-y-auto overscroll-contain pr-1 touch-pan-y">
                {items.map((item, index) => (
                  <div key={`${item}-${index}`} className="group flex min-w-0 max-w-full items-center gap-2 rounded-md border p-2 transition-colors hover:bg-accent/50">
                    {editingIndex === index ? (
                      <Input
                        value={editingValue}
                        onChange={e => setEditingValue(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter' && editingValue.trim()) {
                            e.preventDefault()
                            saveEdit(index)
                          } else if (e.key === 'Escape') {
                            cancelEdit()
                          }
                        }}
                        className="h-7 min-w-0 flex-1 text-sm"
                        autoFocus
                        onBlur={e => {
                          if (!e.relatedTarget || !e.relatedTarget.closest('button')) {
                            saveEdit(index)
                          }
                        }}
                        dir="ltr"
                        disabled={disabled}
                      />
                    ) : (
                      <span
                        className="min-w-0 flex-1 cursor-text truncate text-sm leading-tight transition-colors hover:text-primary"
                        onClick={() => startEdit(index, item)}
                        title={clickToEditTitle}
                      >
                        {item}
                      </span>
                    )}
                    <div className="flex shrink-0 items-center gap-1">
                      {editingIndex === index ? (
                        <>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={e => {
                              e.preventDefault()
                              e.stopPropagation()
                              saveEdit(index)
                            }}
                            className="h-6 w-6 p-0 transition-all duration-200 hover:scale-105"
                            title={saveEditTitle}
                            disabled={!editingValue.trim() || disabled}
                          >
                            <Check className="h-3 w-3" />
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={e => {
                              e.preventDefault()
                              e.stopPropagation()
                              cancelEdit()
                            }}
                            className="h-6 w-6 p-0 transition-all duration-200 hover:scale-105"
                            title={cancelEditTitle}
                            disabled={disabled}
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={e => {
                              e.preventDefault()
                              e.stopPropagation()
                              startEdit(index, item)
                            }}
                            className="h-6 w-6 p-0 transition-all duration-200 hover:scale-105"
                            title={editItemTitle}
                            disabled={disabled}
                          >
                            <Pencil className="h-3 w-3" />
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            onClick={e => {
                              e.preventDefault()
                              e.stopPropagation()
                              removeItem(index)
                            }}
                            className="h-6 w-6 p-0 transition-all duration-200 hover:scale-105"
                            title={removeItemTitle}
                            disabled={disabled}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {items.length === 0 && <div className="py-6 text-start text-sm text-muted-foreground">{emptyMessage}</div>}
        </div>
      </PopoverContent>
    </Popover>
  )
}

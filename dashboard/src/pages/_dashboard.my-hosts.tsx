import PageHeader from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { getMyHosts, resetMyHosts, saveMyHosts, type MyHostItem } from '@/service/my-hosts'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, GripVertical, RotateCcw, Save, Search, Server, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

export default function MyHostsPage() {
  const queryClient = useQueryClient()
  const [items, setItems] = useState<MyHostItem[]>([])
  const [search, setSearch] = useState('')
  const [dirty, setDirty] = useState(false)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['my-hosts'], queryFn: getMyHosts })

  useEffect(() => {
    if (data) {
      setItems(data)
      setDirty(false)
    }
  }, [data])

  const applyResult = (next: MyHostItem[]) => {
    setItems(next)
    setDirty(false)
    queryClient.setQueryData(['my-hosts'], next)
  }

  const save = useMutation({
    mutationFn: () =>
      saveMyHosts(items.map(item => ({ host_id: item.host_id, remark: item.remark, is_disabled: item.is_disabled }))),
    onSuccess: next => {
      applyResult(next)
      toast.success('Hosts saved')
    },
    onError: error => toast.error(error instanceof Error ? error.message : 'Could not save hosts'),
  })

  const reset = useMutation({
    mutationFn: (orderOnly: boolean) => resetMyHosts(orderOnly),
    onSuccess: next => {
      applyResult(next)
      toast.success('Hosts reset')
    },
    onError: error => toast.error(error instanceof Error ? error.message : 'Could not reset hosts'),
  })

  const update = (index: number, patch: Partial<MyHostItem>) => {
    setItems(current => current.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)))
    setDirty(true)
  }

  const move = (index: number, delta: number) => {
    const target = index + delta
    if (target < 0 || target >= items.length) return
    setItems(current => {
      const next = [...current]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
    setDirty(true)
  }

  useEffect(() => {
    if (dragIndex === null) return

    const rowAt = (x: number, y: number) => {
      const row = document.elementFromPoint(x, y)?.closest<HTMLElement>('[data-host-index]')
      const index = Number(row?.dataset.hostIndex)
      return Number.isInteger(index) ? index : null
    }

    const onMove = (event: PointerEvent) => {
      const target = rowAt(event.clientX, event.clientY)
      if (target !== null) setDragOver(target)
    }

    const finish = (event: PointerEvent) => {
      const target = rowAt(event.clientX, event.clientY)
      if (target !== null && target !== dragIndex) {
        setItems(current => {
          const next = [...current]
          const [moved] = next.splice(dragIndex, 1)
          next.splice(target, 0, moved)
          return next
        })
        setDirty(true)
      }
      setDragIndex(null)
      setDragOver(null)
    }

    const cancel = () => {
      setDragIndex(null)
      setDragOver(null)
    }

    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', finish)
    window.addEventListener('pointercancel', cancel)
    return () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', finish)
      window.removeEventListener('pointercancel', cancel)
    }
  }, [dragIndex])

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return items
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => !needle || `${item.remark} ${item.inbound_tag}`.toLowerCase().includes(needle))
  }, [items, search])

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="My Hosts"
        description="Change the server names and order shown to you. These changes only affect your account."
        buttonText="Save"
        buttonIcon={Save}
        onButtonClick={() => save.mutate()}
        buttonTooltip={dirty ? 'Save changes' : 'No changes to save'}
      />
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 pb-10">
        <p className="text-muted-foreground text-sm">
          Names, order, and enabled hosts are reflected in your users&apos; subscription links and copied configurations.
        </p>

        <div className="relative">
          <Search className="text-muted-foreground absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
          <Input
            className="pl-9"
            placeholder="Search hosts"
            value={search}
            onChange={event => setSearch(event.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" onClick={() => reset.mutate(true)} disabled={reset.isPending}>
            <RotateCcw className="h-4 w-4" />
            Reset order
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              if (window.confirm('Reset all names and enabled states?')) reset.mutate(false)
            }}
            disabled={reset.isPending}
          >
            <Trash2 className="h-4 w-4" />
            Reset all
          </Button>
        </div>

        {isLoading ? (
          <div className="text-muted-foreground py-10 text-center text-sm">Loading hosts…</div>
        ) : visible.length === 0 ? (
          <div className="text-muted-foreground py-10 text-center text-sm">No hosts found</div>
        ) : (
          <div className="flex flex-col gap-3">
            {visible.map(({ item, index }) => (
              <div
                key={item.host_id}
                data-host-index={index}
                className={`bg-card rounded-lg border p-3 transition-colors ${
                  dragIndex === index ? 'opacity-60' : ''
                } ${dragOver === index && dragIndex !== null ? 'border-primary' : ''}`}
              >
                <div className="flex items-center gap-2">
                  <Server className="text-muted-foreground h-4 w-4 shrink-0" />
                  <Input
                    value={item.remark}
                    maxLength={256}
                    onChange={event => update(index, { remark: event.target.value })}
                    aria-label="Server name"
                  />
                </div>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 cursor-grab touch-none active:cursor-grabbing"
                      onPointerDown={event => {
                        if (search) return
                        event.preventDefault()
                        setDragIndex(index)
                        setDragOver(index)
                      }}
                      disabled={Boolean(search)}
                      aria-label="Drag to reorder"
                      style={{ touchAction: 'none' }}
                    >
                      <GripVertical className="h-5 w-5" />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => move(index, -1)}
                      disabled={Boolean(search) || index === 0}
                      aria-label="Move up"
                    >
                      <ArrowUp className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => move(index, 1)}
                      disabled={Boolean(search) || index === items.length - 1}
                      aria-label="Move down"
                    >
                      <ArrowDown className="h-4 w-4" />
                    </Button>
                  </div>
                  <Switch
                    checked={!item.is_disabled}
                    onCheckedChange={checked => update(index, { is_disabled: !checked })}
                    aria-label={`Show ${item.remark}`}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

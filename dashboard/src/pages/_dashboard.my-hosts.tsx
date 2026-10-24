import PageHeader from '@/components/layout/page-header'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { PersonalHostRow } from '@/features/my-hosts/components/personal-host-row'
import { HostPermissionsSummary } from '@/features/my-hosts/components/host-permissions-summary'
import { useAdmin } from '@/hooks/use-admin'
import { getGetMyHostsPolicyQueryKey, getGetMyHostsQueryKey, useGetMyHosts, useGetMyHostsPolicy, useModifyMyHosts, type MyHost, type MyHostUpdate } from '@/service/api'
import { isLimited } from '@/utils/rbac'
import { useQueryClient } from '@tanstack/react-query'
import { closestCenter, DndContext, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core'
import { arrayMove, SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { Eye, ListTodo, LockKeyhole, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

export default function MyHostsPage() {
  const { t } = useTranslation()
  const { admin } = useAdmin()
  const { data: policy, isPending: policyPending, isError: policyError, refetch: refetchPolicy } = useGetMyHostsPolicy({ query: { refetchInterval: 30_000 } })
  const { data, isPending, isError, refetch } = useGetMyHosts({ query: { enabled: !!policy?.enabled && !!admin?.id, refetchInterval: 30_000 } })
  const mutation = useModifyMyHosts()
  const queryClient = useQueryClient()
  const [hosts, setHosts] = useState<MyHost[]>([])
  const [dirty, setDirty] = useState(false)
  const [reordered, setReordered] = useState(false)
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }), useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }))
  const disabled = mutation.isPending || isLimited(admin)

  useEffect(() => {
    if (data && !dirty) setHosts(data.hosts)
  }, [data, dirty])

  useEffect(() => {
    if (!policy || !data || JSON.stringify(policy) === JSON.stringify(data.policy)) return
    setDirty(false)
    setReordered(false)
    if (policy.enabled) void refetch()
  }, [policy, data, refetch])

  const updateHost = (id: number, patch: Partial<MyHost>) => {
    setHosts(current => current.map(host => (host.id === id ? { ...host, ...patch } : host)))
    setDirty(true)
  }
  const move = (from: number, to: number) => {
    if (disabled || !policy?.allow_reorder || to < 0 || to >= hosts.length) return
    setHosts(current => arrayMove(current, from, to))
    setReordered(true)
    setDirty(true)
  }
  const onDragEnd = ({ active, over }: DragEndEvent) => {
    if (over && active.id !== over.id)
      move(
        hosts.findIndex(host => host.id === active.id),
        hosts.findIndex(host => host.id === over.id),
      )
  }
  const resetHost = (id: number) => {
    const host = hosts.find(item => item.id === id)
    if (!host || !policy) return
    updateHost(id, {
      ...(policy.allow_rename ? { remark: host.original_remark } : {}),
      ...(policy.allow_disable ? { is_disabled: host.globally_disabled } : {}),
      preference: { ...host.preference, ...(policy.allow_rename ? { remark: null } : {}), ...(policy.allow_disable ? { is_disabled: false } : {}) },
    })
  }
  const restoreAll = () => {
    if (!policy) return
    setHosts(current =>
      current
        .map(host => ({
          ...host,
          ...(policy.allow_rename ? { remark: host.original_remark } : {}),
          ...(policy.allow_disable ? { is_disabled: host.globally_disabled } : {}),
          preference: {
            ...host.preference,
            ...(policy.allow_rename ? { remark: null } : {}),
            ...(policy.allow_reorder ? { position: null } : {}),
            ...(policy.allow_disable ? { is_disabled: false } : {}),
          },
        }))
        .sort((a, b) => (policy.allow_reorder ? a.default_position - b.default_position : 0)),
    )
    setReordered(false)
    setDirty(true)
  }
  const cancel = () => {
    setHosts(data?.hosts || [])
    setReordered(false)
    setDirty(false)
  }
  const save = async () => {
    if (!policy || !data) return
    const updates: MyHostUpdate[] = []
    const originals = new Map(data.hosts.map(host => [host.id, host]))
    for (const [index, host] of hosts.entries()) {
      const original = originals.get(host.id)
      if (!original) continue
      const update: MyHostUpdate = { id: host.id }
      if (policy.allow_rename && host.preference.remark !== original.preference.remark) update.remark = host.preference.remark
      if (policy.allow_rename && host.remark !== original.remark) update.remark = host.remark.trim() === host.original_remark ? null : host.remark.trim()
      if (policy.allow_disable && host.preference.is_disabled !== original.preference.is_disabled) update.is_disabled = host.preference.is_disabled
      if (policy.allow_disable && !host.globally_disabled && host.is_disabled !== original.is_disabled) update.is_disabled = host.is_disabled
      if (policy.allow_reorder && reordered) update.position = index
      else if (policy.allow_reorder && host.preference.position !== original.preference.position) update.position = host.preference.position
      if (Object.keys(update).length > 1) updates.push(update)
    }
    try {
      const result = await mutation.mutateAsync({ data: { hosts: updates } })
      queryClient.setQueryData(getGetMyHostsQueryKey(), result)
      queryClient.setQueryData(getGetMyHostsPolicyQueryKey(), result.policy)
      setHosts(result.hosts)
      setDirty(false)
      setReordered(false)
      toast.success(t('myHosts.saved'))
    } catch {
      toast.error(t('myHosts.saveFailed'))
      void refetchPolicy()
      void refetch()
    }
  }

  let content
  if (policyPending) content = <Skeleton className="h-40 w-full" />
  else if (policyError && !policy)
    content = (
      <div role="alert" className="space-y-3 rounded-lg border p-8">
        <p>{t('myHosts.loadFailed')}</p>
        <Button onClick={() => refetchPolicy()}>{t('myHosts.retry')}</Button>
      </div>
    )
  else if (!policy?.enabled || !admin?.id)
    content = (
      <div className="flex flex-col items-center gap-3 rounded-lg border px-6 py-16 text-center">
        <LockKeyhole className="text-muted-foreground h-9 w-9" />
        <h2 className="font-semibold">{t('myHosts.unavailable')}</h2>
        <p className="text-muted-foreground max-w-md text-sm">{t(!policy?.enabled ? 'myHosts.disabledDescription' : 'myHosts.databaseAccount')}</p>
      </div>
    )
  else if (isPending)
    content = (
      <div className="space-y-3">
        {[1, 2, 3].map(key => (
          <Skeleton key={key} className="h-28 w-full" />
        ))}
      </div>
    )
  else if (isError && !data)
    content = (
      <div role="alert" className="space-y-3 rounded-lg border p-8">
        <p>{t('myHosts.loadFailed')}</p>
        <Button onClick={() => refetch()}>{t('myHosts.retry')}</Button>
      </div>
    )
  else
    content = (
      <>
        <HostPermissionsSummary policy={policy} />
        {isLimited(admin) && (
          <p role="status" className="text-muted-foreground text-sm">
            {t('myHosts.limited')}
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <span className="flex items-center gap-2">
            <ListTodo className="h-4 w-4" />
            {t('myHosts.hostCount', { count: hosts.length })}
          </span>
          <span className="text-muted-foreground flex items-center gap-2">
            <Eye className="h-4 w-4" />
            {t('myHosts.visibleCount', { count: hosts.filter(host => !host.is_disabled).length })}
          </span>
          <Button
            variant="outline"
            size="sm"
            title={t('myHosts.restoreDescription')}
            disabled={disabled || !hosts.length || (!policy.allow_rename && !policy.allow_reorder && !policy.allow_disable)}
            onClick={restoreAll}
          >
            {t('myHosts.restoreAll')}
          </Button>
        </div>
        {hosts.length === 0 ? (
          <div className="text-muted-foreground rounded-lg border p-12 text-center text-sm">{t('myHosts.empty')}</div>
        ) : (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
            <SortableContext items={hosts.map(host => host.id)} strategy={verticalListSortingStrategy}>
              <div className="space-y-3">
                {hosts.map((host, index) => (
                  <PersonalHostRow
                    key={host.id}
                    host={host}
                    index={index}
                    total={hosts.length}
                    policy={policy}
                    disabled={disabled}
                    onRename={remark => updateHost(host.id, { remark, preference: { ...host.preference, remark: remark.trim() === host.original_remark ? null : remark } })}
                    onToggle={enabled => updateHost(host.id, { is_disabled: !enabled, preference: { ...host.preference, is_disabled: !enabled } })}
                    onMove={offset => move(index, index + offset)}
                    onReset={() => resetHost(host.id)}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
        <div className="bg-background/95 sticky bottom-0 flex flex-wrap items-center justify-between gap-3 border-t py-4 backdrop-blur-sm">
          <span role="status" className="text-muted-foreground text-sm">
            {t(dirty ? 'myHosts.unsaved' : 'myHosts.upToDate')}
          </span>
          <div className="flex gap-2">
            <Button variant="outline" disabled={!dirty || mutation.isPending} onClick={cancel}>
              {t('myHosts.cancel')}
            </Button>
            <Button disabled={!dirty || disabled || hosts.some(host => !host.remark.trim())} onClick={save}>
              <Save className="h-4 w-4" />
              {t(mutation.isPending ? 'myHosts.saving' : 'myHosts.save')}
            </Button>
          </div>
        </div>
      </>
    )
  return (
    <div className="flex w-full flex-col">
      <PageHeader title="myHosts.title" description="myHosts.description" />
      <div className="w-full max-w-6xl space-y-5 p-4">{content}</div>
    </div>
  )
}

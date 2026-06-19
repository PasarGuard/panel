import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { setupColumns } from './columns'
import { APIKeyResponse, useGetAdminsSimple, RolePermissions } from '@/service/api'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Edit2, RotateCcw, Trash2, Key, Calendar as CalendarIcon, User as UserIcon, ShieldCheck, MoreHorizontal } from 'lucide-react'
import { dateUtils } from '@/utils/dateFormatter'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

interface ApiKeysTableProps {
  onEdit: (apiKey: APIKeyResponse) => void
  onDelete: (apiKey: APIKeyResponse) => void
  onRevoke: (apiKey: APIKeyResponse) => void
  isCardView?: boolean
  apiKeys: APIKeyResponse[]
  isLoading: boolean
}

export default function ApiKeysTable({
  onEdit,
  onDelete,
  onRevoke,
  isCardView = false,
  apiKeys,
  isLoading,
}: ApiKeysTableProps) {
  const { t } = useTranslation()
  const adminsQuery = useGetAdminsSimple()
  const admins = adminsQuery.data?.admins || []

  const columns = useMemo(
    () => setupColumns({ t, onEdit, onDelete, onRevoke, admins }),
    [t, onEdit, onDelete, onRevoke, admins]
  )

  const table = useReactTable({
    data: apiKeys,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  if (isLoading) {
    if (isCardView) {
      return (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Card key={i} className="h-32 p-4">
              <div className="flex items-start gap-3">
                <div className="flex-1 space-y-2">
                  <div className="flex items-center gap-2">
                    <Skeleton className="h-4 w-4 rounded-full" />
                    <Skeleton className="h-5 w-32" />
                  </div>
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-3 w-40" />
                </div>
                <Skeleton className="h-8 w-8 rounded-md" />
              </div>
            </Card>
          ))}
        </div>
      )
    }
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-md" />
        ))}
      </div>
    )
  }

  if (isCardView) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {apiKeys.length ? (
          apiKeys.map((apiKey) => {
            const admin = admins.find(a => a.id === apiKey.admin_id)
            const permissions = apiKey.permissions as RolePermissions | undefined
            const resourceCount = permissions ? Object.keys(permissions).length : 0
            const actionCount = permissions
              ? Object.values(permissions).reduce((sum, r) => sum + (r ? Object.values(r as object).filter(Boolean).length : 0), 0)
              : 0
            
            return (
              <Card
                key={apiKey.id}
                className={cn(
                  "group relative overflow-hidden border transition-all hover:bg-accent cursor-pointer",
                  apiKey.is_expired && "border-destructive/20 opacity-80"
                )}
                onClick={() => onEdit(apiKey)}
              >
                <div className="p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                        <Key className={cn("h-3.5 w-3.5 shrink-0", apiKey.status === 'active' ? "text-primary" : "text-muted-foreground")} />
                        <h3 className="truncate text-sm font-semibold tracking-tight">{apiKey.name}</h3>
                        {admin && (
                          <Badge variant="outline" className="h-3.5 px-1 text-[8px] font-normal opacity-70 shrink-0">
                            {admin.username}
                          </Badge>
                        )}
                      </div>
                      {apiKey.api_key_trimmed && (
                        <div className="mt-1">
                          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">
                            {apiKey.api_key_trimmed}
                          </code>
                        </div>
                      )}
                      
                      <div className="space-y-1 mt-2">
                        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                          <ShieldCheck className="h-3 w-3" />
                          <span className="truncate">
                            {resourceCount} res · {actionCount} actions
                          </span>
                        </div>
                        
                        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                          <CalendarIcon className="h-3 w-3" />
                          <span className={cn(apiKey.is_expired && "text-destructive font-medium")}>
                            {apiKey.expire_date ? dateUtils.formatDate(apiKey.expire_date) : t('never')}
                            {apiKey.is_expired && ` (${t('expired')})`}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col gap-1 items-end shrink-0">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                          <Button variant="ghost" className="h-7 w-7 p-0 hover:bg-accent">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuLabel>{t('actions')}</DropdownMenuLabel>
                          <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onEdit(apiKey); }}>
                            <Edit2 className="mr-2 h-3.5 w-3.5" />
                            {t('edit')}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onRevoke(apiKey); }}>
                            <RotateCcw className="mr-2 h-3.5 w-3.5" />
                            {t('apiKeys.revoke')}
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive focus:text-destructive"
                            onClick={(e) => { e.stopPropagation(); onDelete(apiKey); }}
                          >
                            <Trash2 className="mr-2 h-3.5 w-3.5" />
                            {t('delete')}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>

                      <Badge variant={apiKey.status === 'active' ? 'green' : 'secondary'} className="px-1.5 py-0 text-[9px] uppercase font-bold mt-1">
                        {t(`admins.${apiKey.status}`)}
                      </Badge>
                    </div>
                  </div>
                </div>
              </Card>
            )
          })
        ) : (
          <div className="col-span-full flex h-40 items-center justify-center rounded-xl border border-dashed text-muted-foreground">
            {t('noResults')}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id}>
                  {header.isPlaceholder
                    ? null
                    : flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows?.length ? (
            table.getRowModel().rows.map((row) => (
              <TableRow
                key={row.id}
                data-state={row.getIsSelected() && 'selected'}
                className="cursor-pointer"
                onClick={() => onEdit(row.original)}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center">
                {t('noResults')}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}

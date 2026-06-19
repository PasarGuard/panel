import { ColumnDef } from '@tanstack/react-table'
import { MoreHorizontal, Trash2, Edit2, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Badge } from '@/components/ui/badge'
import { APIKeyResponse, AdminBase, AdminRoleSimple } from '@/service/api'
import { dateUtils } from '@/utils/dateFormatter'

interface ColumnsProps {
  t: any
  onEdit: (apiKey: APIKeyResponse) => void
  onDelete: (apiKey: APIKeyResponse) => void
  onRevoke: (apiKey: APIKeyResponse) => void
  admins: AdminBase[]
  roles: AdminRoleSimple[]
}

export const setupColumns = ({ t, onEdit, onDelete, onRevoke, admins, roles }: ColumnsProps): ColumnDef<APIKeyResponse>[] => {
  return [
    {
      accessorKey: 'name',
      header: t('apiKeys.name'),
      cell: ({ row }) => {
        const adminId = row.original.admin_id
        const admin = admins.find(a => a.id === adminId)
        return (
          <div className="flex items-center gap-2">
            <span className="font-medium">{row.getValue('name')}</span>
            {admin && (
              <Badge variant="outline" className="h-4 px-1 text-[9px] font-normal opacity-70">
                {admin.username}
              </Badge>
            )}
          </div>
        )
      },
    },
    {
      accessorKey: 'api_key_trimmed',
      header: t('apiKeys.key', { defaultValue: 'API Key' }),
      cell: ({ row }) => {
        const trimmed = row.original.api_key_trimmed
        return trimmed ? (
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
            {trimmed}
          </code>
        ) : (
          <span className="text-muted-foreground">-</span>
        )
      },
    },
    {
      accessorKey: 'role_id',
      header: t('apiKeys.role'),
      cell: ({ row }) => {
        const roleId = row.getValue('role_id')
        const adminId = row.original.admin_id
        const admin = admins.find(a => a.id === adminId)
        
        const role = roles.find(r => r.id === roleId)
        const roleName = role?.name || (roleId === 1 ? 'Owner' : roleId === 2 ? 'Admin' : 'Role ' + roleId)

        return (
          <div className="flex flex-col gap-1">
            <Badge variant="outline" className="w-fit">{roleName}</Badge>
          </div>
        )
      },
    },
    {
      accessorKey: 'status',
      header: t('apiKeys.status'),
      cell: ({ row }) => {
        const status = row.getValue('status') as string
        const isExpired = row.original.is_expired
        if (isExpired) return <Badge variant="destructive">{t('expired')}</Badge>
        return (
          <Badge variant={status === 'active' ? 'green' : 'secondary'}>
            {t(`admins.${status}`)}
          </Badge>
        )
      },
    },
    {
      accessorKey: 'expire_date',
      header: t('apiKeys.expireDate'),
      cell: ({ row }) => {
        const date = row.getValue('expire_date') as string | null
        return date ? dateUtils.formatDate(date) : t('never')
      },
    },
    {
      id: 'actions',
      cell: ({ row }) => {
        const apiKey = row.original

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
              <Button variant="ghost" className="h-8 w-8 p-0">
                <span className="sr-only">Open menu</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>{t('actions')}</DropdownMenuLabel>
              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onEdit(apiKey); }}>
                <Edit2 className="mr-2 h-4 w-4" />
                {t('edit')}
              </DropdownMenuItem>
              <DropdownMenuItem onClick={(e) => { e.stopPropagation(); onRevoke(apiKey); }}>
                <RotateCcw className="mr-2 h-4 w-4" />
                {t('apiKeys.revoke')}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="text-destructive focus:text-destructive"
                onClick={(e) => { e.stopPropagation(); onDelete(apiKey); }}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                {t('delete')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )
      },
    },
  ]
}

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
import { APIKeyResponse } from '@/service/api'
import { dateUtils } from '@/utils/dateFormatter'

interface ColumnsProps {
  t: any
  onEdit: (apiKey: APIKeyResponse) => void
  onDelete: (apiKey: APIKeyResponse) => void
  onRevoke: (apiKey: APIKeyResponse) => void
}

export const setupColumns = ({ t, onEdit, onDelete, onRevoke }: ColumnsProps): ColumnDef<APIKeyResponse>[] => [
  {
    accessorKey: 'name',
    header: t('apiKeys.name'),
    cell: ({ row }) => <div className="font-medium">{row.getValue('name')}</div>,
  },
  {
    accessorKey: 'role_id',
    header: t('apiKeys.role'),
    cell: ({ row }) => {
      const roleId = row.getValue('role_id')
      return <Badge variant="outline">{roleId === 1 ? 'Owner' : roleId === 2 ? 'Admin' : 'Role ' + roleId}</Badge>
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
    accessorKey: 'created_at',
    header: t('apiKeys.createdAt'),
    cell: ({ row }) => dateUtils.formatDate(row.getValue('created_at')),
  },
  {
    id: 'actions',
    cell: ({ row }) => {
      const apiKey = row.original

      return (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 p-0">
              <span className="sr-only">Open menu</span>
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{t('actions')}</DropdownMenuLabel>
            <DropdownMenuItem onClick={() => onEdit(apiKey)}>
              <Edit2 className="mr-2 h-4 w-4" />
              {t('edit')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onRevoke(apiKey)}>
              <RotateCcw className="mr-2 h-4 w-4" />
              {t('apiKeys.revoke')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => onDelete(apiKey)}
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

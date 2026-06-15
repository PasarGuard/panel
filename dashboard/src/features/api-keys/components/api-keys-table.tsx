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
import { APIKeyResponse, useListApiKeys } from '@/service/api'
import { Skeleton } from '@/components/ui/skeleton'

interface ApiKeysTableProps {
  onEdit: (apiKey: APIKeyResponse) => void
  onDelete: (apiKey: APIKeyResponse) => void
  onRevoke: (apiKey: APIKeyResponse) => void
}

export default function ApiKeysTable({ onEdit, onDelete, onRevoke }: ApiKeysTableProps) {
  const { t } = useTranslation()
  const { data: apiKeysResponse, isLoading } = useListApiKeys()
  const apiKeys = apiKeysResponse?.api_keys || []

  const columns = useMemo(
    () => setupColumns({ t, onEdit, onDelete, onRevoke }),
    [t, onEdit, onDelete, onRevoke]
  )

  const table = useReactTable({
    data: apiKeys,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
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

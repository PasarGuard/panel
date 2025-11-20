import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import Node from '@/components/nodes/node'
import {useGetNodes, useModifyNode, NodeResponse, NodeConnectionType} from '@/service/api'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'
import NodeModal from '@/components/dialogs/node-modal'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { nodeFormSchema, NodeFormValues } from '@/components/dialogs/node-modal'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { NodeFilters, NodePaginationControls } from '@/components/nodes/node-filters'

const NODES_PER_PAGE = 15

const initialDefaultValues: Partial<NodeFormValues> = {
  name: '',
  address: '',
  port: 62050,
  usage_coefficient: 1,
  connection_type: NodeConnectionType.grpc,
  server_ca: '',
  keep_alive: 20000,
}

export default function NodesList() {
  const { t } = useTranslation()
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [editingNode, setEditingNode] = useState<NodeResponse | null>(null)
  const [currentPage, setCurrentPage] = useState(0)
  const [isChangingPage, setIsChangingPage] = useState(false)
  const isFirstLoadRef = useRef(true)
  const modifyNodeMutation = useModifyNode()

  const [filters, setFilters] = useState<{
    limit: number
    offset: number
    search?: string
  }>({
    limit: NODES_PER_PAGE,
    offset: 0,
    search: undefined,
  })

  const form = useForm<NodeFormValues>({
    resolver: zodResolver(nodeFormSchema),
    defaultValues: initialDefaultValues,
  })

  const {
    data: nodesResponse,
    isLoading,
    isFetching,
    refetch,
  } = useGetNodes(filters, {
    query: {
      refetchInterval: false,
      staleTime: 0,
      gcTime: 0,
      retry: 1,
      refetchOnMount: true,
      refetchOnWindowFocus: false,
    },
  })

  useEffect(() => {
    if (nodesResponse && isFirstLoadRef.current) {
      isFirstLoadRef.current = false
    }
  }, [nodesResponse])

  useEffect(() => {
    const handleOpenDialog = () => setIsDialogOpen(true)
    window.addEventListener('openNodeDialog', handleOpenDialog)
    return () => window.removeEventListener('openNodeDialog', handleOpenDialog)
  }, [])

  const handleFilterChange = useCallback((newFilters: Partial<typeof filters>) => {
    setFilters(prev => ({
      ...prev,
      ...newFilters,
    }))
    if (newFilters.offset === 0) {
      setCurrentPage(0)
    }
  }, [])

  const handlePageChange = (newPage: number) => {
    if (newPage === currentPage || isChangingPage) return

    setIsChangingPage(true)
    setCurrentPage(newPage)
    setFilters(prev => ({
      ...prev,
      offset: newPage * NODES_PER_PAGE,
    }))
    setIsChangingPage(false)
  }

  const handleEdit = (node: NodeResponse) => {
    setEditingNode(node)
    form.reset({
      name: node.name,
      address: node.address,
      port: node.port || 62050,
      usage_coefficient: node.usage_coefficient || 1,
      connection_type: node.connection_type,
      server_ca: node.server_ca,
      keep_alive: node.keep_alive,
    })
    setIsDialogOpen(true)
  }

  const handleToggleStatus = async (node: NodeResponse) => {
    try {
      const shouldEnable = node.status === 'disabled'
      const newStatus = shouldEnable ? 'connected' : 'disabled'

      await modifyNodeMutation.mutateAsync({
        nodeId: node.id,
        data: {
          name: node.name,
          address: node.address,
          port: node.port,
          usage_coefficient: node.usage_coefficient,
          connection_type: node.connection_type,
          server_ca: node.server_ca,
          keep_alive: node.keep_alive,
          status: newStatus,
        },
      })

      toast.success(t('success', { defaultValue: 'Success' }), {
        description: t(shouldEnable ? 'nodes.enableSuccess' : 'nodes.disableSuccess', {
          name: node.name,
          defaultValue: `Node "{name}" has been ${shouldEnable ? 'enabled' : 'disabled'} successfully`,
        }),
      })

      queryClient.invalidateQueries({
        queryKey: ['/api/nodes'],
      })
    } catch (error) {
      toast.error(t('error', { defaultValue: 'Error' }), {
        description: t(node.status === 'disabled' ? 'nodes.enableFailed' : 'nodes.disableFailed', {
          name: node.name,
          defaultValue: `Failed to ${node.status === 'disabled' ? 'enable' : 'disable'} node "{name}"`,
        }),
      })
    }
  }

  const nodesData = nodesResponse?.nodes || []
  const totalNodes = nodesResponse?.total || 0
  const totalPages = Math.ceil(totalNodes / NODES_PER_PAGE)
  const showLoadingSpinner = isLoading && isFirstLoadRef.current || isFetching
  const isPageLoading = isChangingPage

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full flex-1 space-y-4 pt-6">
        <NodeFilters filters={filters} onFilterChange={handleFilterChange} refetch={refetch} isFetching={isFetching} />
        <div className="min-h-[55dvh]">
        <div
          className=" grid transform-gpu animate-slide-up grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
          style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}
        >
          {showLoadingSpinner
            ? [...Array(6)].map((_, i) => (
                <Card key={i} className="p-4">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <Skeleton className="h-5 w-24 sm:w-32" />
                      <Skeleton className="h-6 w-6 shrink-0 rounded-full" />
                    </div>
                    <Skeleton className="h-4 w-20 sm:w-24" />
                    <div className="flex gap-2">
                      <Skeleton className="h-8 flex-1" />
                      <Skeleton className="h-8 w-8 shrink-0" />
                    </div>
                  </div>
                </Card>
              ))
            : nodesData.map(node => <Node key={node.id} node={node} onEdit={handleEdit} onToggleStatus={handleToggleStatus} />)}
        </div>

        {!showLoadingSpinner && nodesData.length === 0 && !filters.search && (
          <Card className="mb-12">
            <CardContent className="p-8 text-center">
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">{t('nodes.noNodes')}</h3>
                <p className="mx-auto max-w-2xl text-muted-foreground">
                  {t('nodes.noNodesDescription')}{' '}
                  <a href="https://github.com/PasarGuard/node" target="_blank" rel="noopener noreferrer" className="font-medium text-primary underline-offset-4 hover:underline">
                    PasarGuard/node
                  </a>{' '}
                  {t('nodes.noNodesDescription2', { defaultValue: 'and connect it to the panel.' })}
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {!showLoadingSpinner && nodesData.length === 0 && (filters.search) && (
          <Card className="mb-12">
            <CardContent className="p-8 text-center">
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">{t('noResults')}</h3>
                <p className="mx-auto max-w-2xl text-muted-foreground">
                  {t('nodes.noSearchResults', { defaultValue: 'No nodes match your search criteria. Try adjusting your search terms.' })}
                </p>
              </div>
            </CardContent>
          </Card>
        )}
        </div>
        {!showLoadingSpinner && nodesData.length > 0 && totalNodes > NODES_PER_PAGE && (
          <NodePaginationControls
            currentPage={currentPage}
            totalPages={totalPages}
            totalNodes={totalNodes}
            isLoading={isPageLoading}
            onPageChange={handlePageChange}
          />
        )}

        <NodeModal
          isDialogOpen={isDialogOpen}
          onOpenChange={open => {
            if (!open) {
              setEditingNode(null)
              form.reset(initialDefaultValues)
            }
            setIsDialogOpen(open)
          }}
          form={form}
          editingNode={!!editingNode}
          editingNodeId={editingNode?.id}
          initialNodeData={editingNode || undefined}
        />
      </div>
    </div>
  )
}

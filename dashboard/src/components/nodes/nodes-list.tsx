import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import Node from '@/components/nodes/node'
import { useGetNodes, useModifyNode, NodeResponse, NodeConnectionType, NodeStatus } from '@/service/api'
import { toast } from 'sonner'
import { queryClient } from '@/utils/query-client'
import NodeModal from '@/components/dialogs/node-modal'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { nodeFormSchema, NodeFormValues } from '@/components/dialogs/node-modal'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { NodeFilters, NodePaginationControls } from '@/components/nodes/node-filters'
import NodeAdvanceSearchModal, { NodeAdvanceSearchFormValue, nodeAdvanceSearchFormSchema } from '@/components/dialogs/node-advance-search-modal'

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
  const wasFetchingRef = useRef(false)
  const isFirstLoadRef = useRef(true)
  const previousTotalPagesRef = useRef(0)
  const isAutoRefreshingRef = useRef(false)
  const modifyNodeMutation = useModifyNode()
  const [allNodes, setAllNodes] = useState<NodeResponse[]>([])
  const [localSearchTerm, setLocalSearchTerm] = useState<string>('')
  const [isAdvanceSearchOpen, setIsAdvanceSearchOpen] = useState(false)

  const [filters, setFilters] = useState<{
    limit: number
    offset: number
    search?: string
    status?: NodeStatus[]
    core_id?: number
  }>({
    limit: NODES_PER_PAGE,
    offset: 0,
    search: undefined,
    status: undefined,
    core_id: undefined
  })

  const form = useForm<NodeFormValues>({
    resolver: zodResolver(nodeFormSchema),
    defaultValues: initialDefaultValues,
  })

  const advanceSearchForm = useForm<NodeAdvanceSearchFormValue>({
    resolver: zodResolver(nodeAdvanceSearchFormSchema),
    defaultValues: {
      status: filters.status || [],
      core_id: filters.core_id || undefined
    },
  })

  const {
    data: nodesResponse,
    isLoading,
    isFetching,
    refetch,
  } = useGetNodes(filters, {
    query: {
      refetchInterval: 10000,
      staleTime: 0,
      gcTime: 0,
      retry: 1,
      refetchOnMount: true,
      refetchOnWindowFocus: true,
    },
  })

  const totalNodesFromResponse = nodesResponse?.total || 0
  const shouldUseLocalSearch = totalNodesFromResponse > 0 && totalNodesFromResponse <= NODES_PER_PAGE && !filters.search

  useEffect(() => {
    if (nodesResponse && isFirstLoadRef.current) {
      isFirstLoadRef.current = false
    }
    if (nodesResponse && shouldUseLocalSearch && !filters.search && filters.offset === 0) {
      setAllNodes(nodesResponse.nodes || [])
    }
  }, [nodesResponse, shouldUseLocalSearch, filters.search, filters.offset])

  useEffect(() => {
    if (isFetching && !isChangingPage && !isFirstLoadRef.current && nodesResponse) {
      isAutoRefreshingRef.current = true
    }
    if (!isFetching && wasFetchingRef.current && isChangingPage) {
      setIsChangingPage(false)
      wasFetchingRef.current = false
    }
    if (isFetching) {
      wasFetchingRef.current = true
    }
    if (!isFetching && isAutoRefreshingRef.current) {
      isAutoRefreshingRef.current = false
    }
  }, [isFetching, isChangingPage, nodesResponse])

  useEffect(() => {
    const handleOpenDialog = () => setIsDialogOpen(true)
    window.addEventListener('openNodeDialog', handleOpenDialog)
    return () => window.removeEventListener('openNodeDialog', handleOpenDialog)
  }, [])

  const handleFilterChange = useCallback(
    (newFilters: Partial<typeof filters>) => {
      const searchValue = newFilters.search !== undefined ? newFilters.search : filters.search
      setLocalSearchTerm(searchValue || '')

      if (shouldUseLocalSearch && searchValue) {
        setCurrentPage(0)
        return
      }

      setFilters(prev => ({
        ...prev,
        ...newFilters,
      }))
      if (newFilters.offset === 0) {
        setCurrentPage(0)
      }
    },
    [filters.search, shouldUseLocalSearch],
  )

  const handlePageChange = (newPage: number) => {
    if (newPage === currentPage || isChangingPage) return

    // If using local search, just update page without API call
    if (shouldUseLocalSearch && localSearchTerm) {
      setCurrentPage(newPage)
      return
    }

    setIsChangingPage(true)
    setCurrentPage(newPage)
    setFilters(prev => ({
      ...prev,
      offset: newPage * NODES_PER_PAGE,
    }))
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

  const filteredNodes = useMemo(() => {
    if (shouldUseLocalSearch && localSearchTerm && allNodes.length > 0) {
      const searchLower = localSearchTerm.toLowerCase()
      return allNodes.filter((node: NodeResponse) => node.name.toLowerCase().includes(searchLower) || node.address.toLowerCase().includes(searchLower) || node.port?.toString().includes(searchLower))
    }
    return nodesResponse?.nodes || []
  }, [shouldUseLocalSearch, localSearchTerm, allNodes, nodesResponse?.nodes])

  const paginatedNodes = useMemo(() => {
    if (shouldUseLocalSearch && localSearchTerm) {
      const start = currentPage * NODES_PER_PAGE
      const end = start + NODES_PER_PAGE
      return filteredNodes.slice(start, end)
    }
    return filteredNodes
  }, [shouldUseLocalSearch, localSearchTerm, filteredNodes, currentPage])

  const nodesData = paginatedNodes
  const totalNodes = shouldUseLocalSearch && localSearchTerm ? filteredNodes.length : nodesResponse?.total || 0
  const showLoadingSpinner = isLoading && isFirstLoadRef.current
  const isBackgroundRefetch = isFetching && !isChangingPage && !isFirstLoadRef.current && !!nodesResponse
  const isPageLoading = isChangingPage || (isFetching && !isFirstLoadRef.current && !shouldUseLocalSearch && !isBackgroundRefetch)
  const showPageLoadingSkeletons = isPageLoading && !showLoadingSpinner

  const calculatedTotalPages = Math.ceil(totalNodes / NODES_PER_PAGE)
  const totalPages = calculatedTotalPages > 0 ? calculatedTotalPages : isPageLoading ? previousTotalPagesRef.current : 0

  useEffect(() => {
    if (calculatedTotalPages > 0) {
      previousTotalPagesRef.current = calculatedTotalPages
    }
  }, [calculatedTotalPages])

  useEffect(() => {
    if (calculatedTotalPages > 0 && currentPage >= calculatedTotalPages) {
      const lastPage = calculatedTotalPages - 1
      setCurrentPage(lastPage)
      setFilters(prev => ({
        ...prev,
        offset: lastPage * NODES_PER_PAGE,
      }))
    }
  }, [calculatedTotalPages, currentPage])

  const handleAdvanceSearchSubmit = (values: NodeAdvanceSearchFormValue) => {
    setFilters(prev => ({
      ...prev,
      status: values.status && values.status.length > 0 ? values.status : undefined,
      core_id: values.core_id || undefined,
      offset: 0,
    }))
    setCurrentPage(0)
    setIsAdvanceSearchOpen(false)
  }

  const handleClearAdvanceSearch = () => {
    advanceSearchForm.reset({
      status: [],
      core_id: undefined,
    })
    setFilters(prev => ({
      ...prev,
      status: undefined,
      core_id: undefined,
      offset: 0,
    }))
    setCurrentPage(0)
  }

  const handleAdvanceSearchOpen = (open: boolean) => {
    if (open) {
      // Sync form with current filters when opening
      advanceSearchForm.reset({
        status: filters.status || [],
        core_id: filters.core_id || undefined,
      })
    }
    setIsAdvanceSearchOpen(open)
  }

  return (
    <div className="flex w-full flex-col items-start gap-2">
      <div className="w-full flex-1 space-y-4 py-4">
        <NodeFilters
          filters={filters}
          onFilterChange={handleFilterChange}
          refetch={refetch}
          isFetching={isFetching}
          advanceSearchOnOpen={handleAdvanceSearchOpen}
          onClearAdvanceSearch={handleClearAdvanceSearch}
        />
        <div className="min-h-[55dvh]">
          <div
            className="grid transform-gpu animate-slide-up grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
            style={{ animationDuration: '500ms', animationDelay: '100ms', animationFillMode: 'both' }}
          >
            {showLoadingSpinner || showPageLoadingSkeletons
              ? [...Array(6)].map((_, i) => (
                  <Card key={i} className="group relative h-full p-4">
                    <div className="flex items-center gap-3">
                      <div className="min-w-0 flex-1">
                        {/* Status dot + Node name */}
                        <div className="mb-1 flex items-center gap-2">
                          <Skeleton className="h-2 w-2 shrink-0 rounded-full" />
                          <Skeleton className="h-5 w-32 sm:w-40" />
                        </div>
                        {/* Address:port */}
                        <Skeleton className="mb-1 h-4 w-28 sm:w-36" />
                        {/* Version info (optional, sometimes shown) */}
                        {i % 3 === 0 && <Skeleton className="mb-2 mt-1 h-3 w-40 sm:w-48" />}
                        {/* Usage display section */}
                        <div className="mt-2 space-y-1.5">
                          {/* Progress bar */}
                          <Skeleton className="h-1.5 w-full rounded-full" />
                          {/* Usage stats */}
                          <div className="flex items-center justify-between gap-2">
                            <Skeleton className="h-3 w-20" />
                            <Skeleton className="h-3 w-16" />
                          </div>
                          {/* Uplink/Downlink */}
                          <div className="flex items-center gap-3">
                            <Skeleton className="h-2.5 w-16" />
                            <Skeleton className="h-2.5 w-16" />
                          </div>
                        </div>
                      </div>
                      {/* Dropdown menu button */}
                      <div>
                        <Skeleton className="h-9 w-9 shrink-0 rounded-md" />
                      </div>
                    </div>
                  </Card>
                ))
              : nodesData.map(node => <Node key={node.id} node={node} onEdit={handleEdit} onToggleStatus={handleToggleStatus} />)}
          </div>

          {!showLoadingSpinner && !showPageLoadingSkeletons && nodesData.length === 0 && !filters.search && !localSearchTerm && totalNodes === 0 && (
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

          {!showLoadingSpinner && !showPageLoadingSkeletons && nodesData.length === 0 && (filters.search || localSearchTerm) && (
            <Card className="mb-12">
              <CardContent className="p-8 text-center">
                <div className="space-y-4">
                  <h3 className="text-lg font-semibold">{t('noResults')}</h3>
                  <p className="mx-auto max-w-2xl text-muted-foreground">{t('nodes.noSearchResults', { defaultValue: 'No nodes match your search criteria. Try adjusting your search terms.' })}</p>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
        {totalPages > 1 && <NodePaginationControls currentPage={currentPage} totalPages={totalPages} isLoading={isPageLoading} onPageChange={handlePageChange} />}

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

        <NodeAdvanceSearchModal
          isDialogOpen={isAdvanceSearchOpen}
          onOpenChange={setIsAdvanceSearchOpen}
          form={advanceSearchForm}
          onSubmit={handleAdvanceSearchSubmit}
        />
      </div>
    </div>
  )
}

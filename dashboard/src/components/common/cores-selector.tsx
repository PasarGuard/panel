import { FormItem, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { useGetAllCores } from '@/service/api'
import { Search, Check } from 'lucide-react'
import { useState } from 'react'
import { Control, FieldPath, FieldValues, useController } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

interface CoresSelectorProps<T extends FieldValues> {
    control: Control<T>
    name: FieldPath<T>
    onCoreChange?: (core: number | null) => void
    placeholder?: string
}

export default function CoresSelector<T extends FieldValues>({ control, name, onCoreChange, placeholder }: CoresSelectorProps<T>) {
    const { t } = useTranslation()
    const [searchQuery, setSearchQuery] = useState('')

    const { field } = useController({
        control,
        name,
    })

    const { data: coresData, isLoading: coresLoading } = useGetAllCores(undefined, {
        query: {
            staleTime: 5 * 60 * 1000, // 5 minutes
            gcTime: 10 * 60 * 1000, // 10 minutes
            refetchOnWindowFocus: true,
            refetchOnMount: true,
            refetchOnReconnect: true,
        },
    })

    const selectedCoreId = field.value as number | null | undefined
    const filteredCores = (coresData?.cores || []).filter((core: any) => 
        core.name.toLowerCase().includes(searchQuery.toLowerCase())
    )

    const handleCoreSelect = (coreId: number) => {
        // Toggle selection: if clicking on already selected core, deselect it
        if (selectedCoreId === coreId) {
            field.onChange(null)
            onCoreChange?.(null)
        } else {
            field.onChange(coreId)
            onCoreChange?.(coreId)
        }
    }

    const selectedCore = coresData?.cores?.find((core: any) => core.id === selectedCoreId)

    if (coresLoading) {
        return (
            <FormItem>
                <div className="space-y-4">
                    <div className="relative">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Skeleton className="h-10 w-full pl-8" />
                    </div>
                    <div className="max-h-[200px] space-y-2 overflow-y-auto rounded-md border p-2">
                        {Array.from({ length: 5 }).map((_, index) => (
                            <div key={index} className="flex items-center gap-2 rounded-md p-2">
                                <Skeleton className="h-4 w-full" />
                            </div>
                        ))}
                    </div>
                </div>
            </FormItem>
        )
    }

    return (
        <FormItem>
            <div className="space-y-4">
                <div className="relative">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                        placeholder={placeholder || t('search', { defaultValue: 'Search' }) + ' ' + t('cores', { defaultValue: 'cores' })}
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        className="pl-8"
                    />
                </div>

                <div className="max-h-[200px] space-y-2 overflow-y-auto rounded-md border p-2">
                    {filteredCores.length === 0 ? (
                        <div className="flex w-full flex-col gap-2 rounded-md p-4 text-center">
                            <span className="text-sm text-muted-foreground">
                                {searchQuery 
                                    ? t('advanceSearch.noCoresFound', { defaultValue: 'No cores found' })
                                    : t('advanceSearch.noCoresAvailable', { defaultValue: 'No cores available' })
                                }
                            </span>
                        </div>
                    ) : (
                        filteredCores.map((core: any) => (
                            <button
                                key={core.id}
                                type="button"
                                onClick={() => handleCoreSelect(core.id)}
                                className={cn(
                                    "flex w-full cursor-pointer items-center justify-between gap-2 rounded-md p-2 text-left hover:bg-accent",
                                    selectedCoreId === core.id && "bg-accent"
                                )}
                            >
                                <span className="text-sm">{core.name}</span>
                                {selectedCoreId === core.id && (
                                    <Check className="h-4 w-4 text-primary" />
                                )}
                            </button>
                        ))
                    )}
                </div>
                
                {selectedCore && (
                    <div className="text-sm text-muted-foreground">
                        {t('advanceSearch.selectedCore', {
                            defaultValue: 'Selected: {{name}}',
                            name: selectedCore.name
                        })}
                    </div>
                )}
            </div>
            <FormMessage />
        </FormItem>
    )
}

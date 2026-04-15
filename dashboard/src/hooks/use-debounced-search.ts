import { useState, useRef, useEffect, useCallback } from 'react'
import { debounce } from 'es-toolkit'

export function useDebouncedSearch(initialValue: string = '', delay: number = 300) {
  const normalizedInitialValue = initialValue || ''
  const [search, setSearch] = useState(normalizedInitialValue)
  const [debouncedSearch, setDebouncedSearch] = useState<string | undefined>(normalizedInitialValue || undefined)

  const debouncedSearchRef = useRef(
    debounce((value: string) => {
      setDebouncedSearch(value || undefined)
    }, delay),
  )

  useEffect(() => {
    return () => {
      debouncedSearchRef.current.cancel()
    }
  }, [])

  useEffect(() => {
    debouncedSearchRef.current.cancel()
    setSearch(prev => (prev === normalizedInitialValue ? prev : normalizedInitialValue))
    setDebouncedSearch(prev => (prev === (normalizedInitialValue || undefined) ? prev : (normalizedInitialValue || undefined)))
  }, [normalizedInitialValue])

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value)
    debouncedSearchRef.current(value)
  }, [])

  return {
    search,
    debouncedSearch,
    setSearch: handleSearchChange,
  }
}


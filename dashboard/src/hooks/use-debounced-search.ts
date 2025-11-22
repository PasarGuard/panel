import { useState, useRef, useEffect, useCallback } from 'react'
import { debounce } from 'es-toolkit'

export function useDebouncedSearch(initialValue: string = '', delay: number = 300) {
  const [search, setSearch] = useState(initialValue)
  const [debouncedSearch, setDebouncedSearch] = useState<string | undefined>(undefined)

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


import { useEffect } from 'react'
import { type CommandCreateTarget, useCommandPaletteStore } from '@/hooks/use-command-palette-store'

export function useCommandCreate(target: CommandCreateTarget, handler: () => void) {
  const createTarget = useCommandPaletteStore(s => s.createTarget)
  const consumeCreate = useCommandPaletteStore(s => s.consumeCreate)

  useEffect(() => {
    if (createTarget !== target) return
    handler()
    consumeCreate()
  }, [consumeCreate, createTarget, handler, target])
}

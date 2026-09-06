import { create } from 'zustand'

export type CommandCreateTarget = 'user' | 'group' | 'host' | 'node' | 'admin' | 'template' | 'core'

interface CommandPaletteState {
  open: boolean
  setOpen: (open: boolean | ((value: boolean) => boolean)) => void
  createTarget: CommandCreateTarget | null
  requestCreate: (target: CommandCreateTarget) => void
  consumeCreate: () => void
}

export const useCommandPaletteStore = create<CommandPaletteState>(set => ({
  open: false,
  setOpen: open => set(state => ({ open: typeof open === 'function' ? open(state.open) : open })),
  createTarget: null,
  requestCreate: target => set({ createTarget: target, open: false }),
  consumeCreate: () => set({ createTarget: null }),
}))

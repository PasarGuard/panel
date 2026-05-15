import type { CoreKind } from '@pasarguard/core-kit'
import type { Profile } from '@pasarguard/xray-config-kit'
import type { WireGuardCoreDraft } from '@pasarguard/wireguard-config-kit'
import { create } from 'zustand'
import type { CoreResponse } from '@/service/api'
import { apiCoreTypeToKind } from '../kit/core-kind'
import { createNewXrayProfile, importRawToProfile, profileToPersistedConfig } from '../kit/xray-adapter'
import { createNewWireGuardDraft, draftToPersistedConfig, wireGuardConfigToDraft } from '../kit/wireguard-adapter'

export type XrayCoreSection = 'bindings' | 'inbounds' | 'outbounds' | 'routing' | 'balancers' | 'dns' | 'advanced'

export type WgCoreSection = 'interface' | 'advanced'

function cloneProfile(p: Profile): Profile {
  return JSON.parse(JSON.stringify(p)) as Profile
}

function cloneWg(d: WireGuardCoreDraft): WireGuardCoreDraft {
  return JSON.parse(JSON.stringify(d)) as WireGuardCoreDraft
}

export interface PersistedSnapshot {
  kind: CoreKind
  coreName: string
  fallbacksInboundTags: string[]
  excludeInboundTags: string[]
  xrayProfile: Profile | null
  wgDraft: WireGuardCoreDraft | null
  activeSection: XrayCoreSection | WgCoreSection
  monacoJson: string
  xrayImportWarnings: string[]
  /** Last `JSON.stringify(core.config)` from the API used to hydrate this draft (clean-state refetch sync). */
  serverHydratedConfigJson: string | null
}

function captureSnapshot(s: CoreEditorStoreState): PersistedSnapshot {
  return {
    kind: s.kind,
    coreName: s.coreName,
    fallbacksInboundTags: [...s.fallbacksInboundTags],
    excludeInboundTags: [...s.excludeInboundTags],
    xrayProfile: s.xrayProfile ? cloneProfile(s.xrayProfile) : null,
    wgDraft: s.wgDraft ? cloneWg(s.wgDraft) : null,
    activeSection: s.activeSection,
    monacoJson: s.monacoJson,
    xrayImportWarnings: [...s.xrayImportWarnings],
    serverHydratedConfigJson: s.serverHydratedConfigJson,
  }
}

/** Legacy snapshots used `overview`; map to current sections. */
function normalizePersistedActiveSection(snapshot: PersistedSnapshot): XrayCoreSection | WgCoreSection {
  const s = snapshot.activeSection as string
  if (snapshot.kind === 'wg' && s === 'overview') return 'interface'
  if (snapshot.kind === 'xray' && s === 'overview') return 'bindings'
  return snapshot.activeSection
}

function applyPersistedSnapshot(snapshot: PersistedSnapshot): Partial<CoreEditorStoreState> {
  if (snapshot.kind === 'wg' && snapshot.wgDraft) {
    const d = cloneWg(snapshot.wgDraft)
    return {
      kind: snapshot.kind,
      coreName: snapshot.coreName,
      fallbacksInboundTags: [...snapshot.fallbacksInboundTags],
      excludeInboundTags: [...snapshot.excludeInboundTags],
      xrayProfile: null,
      xrayBaseline: null,
      wgDraft: d,
      wgBaseline: cloneWg(d),
      activeSection: normalizePersistedActiveSection(snapshot),
      monacoJson: snapshot.monacoJson,
      monacoDirty: false,
      xrayImportWarnings: [...snapshot.xrayImportWarnings],
      serverHydratedConfigJson: snapshot.serverHydratedConfigJson ?? null,
      dirty: false,
    }
  }
  if (snapshot.kind === 'xray' && snapshot.xrayProfile) {
    const p = cloneProfile(snapshot.xrayProfile)
    return {
      kind: snapshot.kind,
      coreName: snapshot.coreName,
      fallbacksInboundTags: [...snapshot.fallbacksInboundTags],
      excludeInboundTags: [...snapshot.excludeInboundTags],
      xrayProfile: p,
      xrayBaseline: cloneProfile(p),
      wgDraft: null,
      wgBaseline: null,
      activeSection: normalizePersistedActiveSection(snapshot),
      monacoJson: snapshot.monacoJson,
      monacoDirty: false,
      xrayImportWarnings: [...snapshot.xrayImportWarnings],
      serverHydratedConfigJson: snapshot.serverHydratedConfigJson ?? null,
      dirty: false,
    }
  }
  return {}
}

export interface CoreEditorStoreState {
  hydrated: boolean
  isNew: boolean
  coreId: number | null
  coreName: string
  kind: CoreKind
  restartNodes: boolean
  fallbacksInboundTags: string[]
  excludeInboundTags: string[]
  xrayProfile: Profile | null
  xrayBaseline: Profile | null
  wgDraft: WireGuardCoreDraft | null
  wgBaseline: WireGuardCoreDraft | null
  activeSection: XrayCoreSection | WgCoreSection
  dirty: boolean
  monacoJson: string
  monacoDirty: boolean
  xrayImportWarnings: string[]
  /** Fingerprint of last server `config` JSON applied while hydrated; used to pick up refetches when the draft is clean. */
  serverHydratedConfigJson: string | null
  persistedSnapshot: PersistedSnapshot | null

  initFromCore: (core: CoreResponse, options?: { preserveNavigation?: boolean }) => void
  initNew: (kind: CoreKind, name?: string) => void
  reset: () => void
  setCoreName: (name: string) => void
  setActiveSection: (s: XrayCoreSection | WgCoreSection) => void
  setRestartNodes: (v: boolean) => void
  setFallbacksInboundTags: (tags: string[]) => void
  setExcludeInboundTags: (tags: string[]) => void
  setXrayProfile: (p: Profile) => void
  updateXrayProfile: (updater: (p: Profile) => Profile) => void
  setWgDraft: (d: WireGuardCoreDraft) => void
  updateWgDraft: (updater: (d: WireGuardCoreDraft) => WireGuardCoreDraft) => void
  markClean: () => void
  discardDraft: () => void
  switchKind: (nextKind: CoreKind) => void
  setMonacoJson: (json: string, opts?: { dirty?: boolean }) => void
  syncMonacoFromDraft: () => void
  applyMonacoJson: () => { ok: true } | { ok: false; error: string }
}

const defaultSection = (kind: CoreKind): XrayCoreSection | WgCoreSection => (kind === 'wg' ? 'interface' : 'inbounds')

export const useCoreEditorStore = create<CoreEditorStoreState>((set, get) => ({
  hydrated: false,
  isNew: false,
  coreId: null,
  coreName: '',
  kind: 'xray',
  restartNodes: true,
  fallbacksInboundTags: [],
  excludeInboundTags: [],
  xrayProfile: null,
  xrayBaseline: null,
  wgDraft: null,
  wgBaseline: null,
  activeSection: 'inbounds',
  dirty: false,
  monacoJson: '{}',
  monacoDirty: false,
  xrayImportWarnings: [],
  serverHydratedConfigJson: null,
  persistedSnapshot: null,

  initFromCore: (core, options) => {
    const preserveNavigation = options?.preserveNavigation === true
    const prev = preserveNavigation ? get() : null
    const kind = apiCoreTypeToKind(core.type)
    const fallbacks = (core.fallbacks_inbound_tags ?? []).map(String)
    const excludes = (core.exclude_inbound_tags ?? []).map(String)
    const serverJson = JSON.stringify(core.config)
    const nav =
      preserveNavigation && prev && prev.coreId === core.id
        ? { activeSection: prev.activeSection, restartNodes: prev.restartNodes }
        : { activeSection: defaultSection(kind), restartNodes: true }
    if (kind === 'wg') {
      const parsed = wireGuardConfigToDraft(core.config)
      if (!parsed.ok) {
        const fallbackDraft = createNewWireGuardDraft()
        set({
          hydrated: true,
          isNew: false,
          coreId: core.id,
          coreName: core.name,
          kind,
          restartNodes: nav.restartNodes,
          fallbacksInboundTags: [],
          excludeInboundTags: [],
          xrayProfile: null,
          xrayBaseline: null,
          wgDraft: fallbackDraft,
          wgBaseline: cloneWg(fallbackDraft),
          activeSection: nav.activeSection,
          dirty: false,
          monacoJson: JSON.stringify(core.config, null, 2),
          monacoDirty: false,
          xrayImportWarnings: [parsed.message],
          serverHydratedConfigJson: serverJson,
        })
        set({ persistedSnapshot: captureSnapshot(get()) })
        return
      }
      const draft = parsed.draft
      set({
        hydrated: true,
        isNew: false,
        coreId: core.id,
        coreName: core.name,
        kind,
        restartNodes: nav.restartNodes,
        fallbacksInboundTags: [],
        excludeInboundTags: [],
        xrayProfile: null,
        xrayBaseline: null,
        wgDraft: draft,
        wgBaseline: cloneWg(draft),
        activeSection: nav.activeSection,
        dirty: false,
        monacoJson: JSON.stringify(draftToPersistedConfig(draft), null, 2),
        monacoDirty: false,
        xrayImportWarnings: [],
        serverHydratedConfigJson: serverJson,
      })
      set({ persistedSnapshot: captureSnapshot(get()) })
      return
    }
    const { profile, issues } = importRawToProfile(core.config)
    const p = cloneProfile(profile)
    set({
      hydrated: true,
      isNew: false,
      coreId: core.id,
      coreName: core.name,
      kind,
      restartNodes: nav.restartNodes,
      fallbacksInboundTags: fallbacks,
      excludeInboundTags: excludes,
      xrayProfile: p,
      xrayBaseline: cloneProfile(p),
      wgDraft: null,
      wgBaseline: null,
      activeSection: nav.activeSection,
      dirty: false,
      monacoJson: JSON.stringify(profileToPersistedConfig(p), null, 2),
      monacoDirty: false,
      xrayImportWarnings: issues.filter(i => i.severity !== 'error').map(i => i.message),
      serverHydratedConfigJson: serverJson,
    })
    set({ persistedSnapshot: captureSnapshot(get()) })
  },

  initNew: (kind, name = '') => {
    if (kind === 'wg') {
      const draft = createNewWireGuardDraft()
      set({
        hydrated: true,
        isNew: true,
        coreId: null,
        coreName: name,
        kind,
        restartNodes: true,
        fallbacksInboundTags: [],
        excludeInboundTags: [],
        xrayProfile: null,
        xrayBaseline: null,
        wgDraft: draft,
        wgBaseline: cloneWg(draft),
        activeSection: defaultSection(kind),
        dirty: false,
        monacoJson: JSON.stringify(draftToPersistedConfig(draft), null, 2),
        monacoDirty: false,
        xrayImportWarnings: [],
        serverHydratedConfigJson: null,
      })
      set({ persistedSnapshot: captureSnapshot(get()) })
      return
    }
    const p = createNewXrayProfile()
    set({
      hydrated: true,
      isNew: true,
      coreId: null,
      coreName: name,
      kind,
      restartNodes: true,
      fallbacksInboundTags: [],
      excludeInboundTags: [],
      xrayProfile: p,
      xrayBaseline: cloneProfile(p),
      wgDraft: null,
      wgBaseline: null,
      activeSection: defaultSection(kind),
      dirty: false,
      monacoJson: JSON.stringify(profileToPersistedConfig(p), null, 2),
      monacoDirty: false,
      xrayImportWarnings: [],
      serverHydratedConfigJson: null,
    })
    set({ persistedSnapshot: captureSnapshot(get()) })
  },

  reset: () =>
    set({
      hydrated: false,
      isNew: false,
      coreId: null,
      coreName: '',
      kind: 'xray',
      restartNodes: true,
      fallbacksInboundTags: [],
      excludeInboundTags: [],
      xrayProfile: null,
      xrayBaseline: null,
      wgDraft: null,
      wgBaseline: null,
      activeSection: 'inbounds',
      dirty: false,
      monacoJson: '{}',
      monacoDirty: false,
      xrayImportWarnings: [],
      serverHydratedConfigJson: null,
      persistedSnapshot: null,
    }),

  setCoreName: coreName => set({ coreName, dirty: true }),

  setActiveSection: activeSection => set({ activeSection }),

  setRestartNodes: restartNodes => set({ restartNodes }),

  setFallbacksInboundTags: fallbacksInboundTags => set({ fallbacksInboundTags, dirty: true }),

  setExcludeInboundTags: excludeInboundTags => set({ excludeInboundTags, dirty: true }),

  setXrayProfile: xrayProfile => {
    set({ xrayProfile, dirty: true })
    get().syncMonacoFromDraft()
  },

  updateXrayProfile: updater => {
    const cur = get().xrayProfile
    if (!cur) return
    const next = updater(cloneProfile(cur))
    set({ xrayProfile: next, dirty: true })
    get().syncMonacoFromDraft()
  },

  setWgDraft: wgDraft => {
    set({ wgDraft, dirty: true })
    get().syncMonacoFromDraft()
  },

  updateWgDraft: updater => {
    const cur = get().wgDraft
    if (!cur) return
    const next = updater(cloneWg(cur))
    set({ wgDraft: next, dirty: true })
    get().syncMonacoFromDraft()
  },

  markClean: () => {
    const { kind, xrayProfile, wgDraft } = get()
    if (kind === 'wg' && wgDraft) {
      set({ wgBaseline: cloneWg(wgDraft), dirty: false, monacoDirty: false })
    } else if (kind === 'xray' && xrayProfile) {
      set({ xrayBaseline: cloneProfile(xrayProfile), dirty: false, monacoDirty: false })
    }
    get().syncMonacoFromDraft()
    set({ persistedSnapshot: captureSnapshot(get()) })
  },

  discardDraft: () => {
    const snap = get().persistedSnapshot
    if (!snap) return
    const partial = applyPersistedSnapshot(snap)
    if (Object.keys(partial).length === 0) return
    set(partial)
  },

  switchKind: nextKind => {
    const cur = get().kind
    if (nextKind === cur) return
    if (nextKind === 'wg') {
      const draft = createNewWireGuardDraft()
      set({
        kind: 'wg',
        fallbacksInboundTags: [],
        excludeInboundTags: [],
        xrayProfile: null,
        xrayBaseline: null,
        wgDraft: draft,
        wgBaseline: cloneWg(draft),
        activeSection: defaultSection('wg'),
        dirty: true,
        monacoJson: JSON.stringify(draftToPersistedConfig(draft), null, 2),
        monacoDirty: false,
        xrayImportWarnings: [],
      })
      return
    }
    const p = createNewXrayProfile()
    set({
      kind: 'xray',
      fallbacksInboundTags: [],
      excludeInboundTags: [],
      xrayProfile: p,
      xrayBaseline: cloneProfile(p),
      wgDraft: null,
      wgBaseline: null,
      activeSection: defaultSection('xray'),
      dirty: true,
      monacoJson: JSON.stringify(profileToPersistedConfig(p), null, 2),
      monacoDirty: false,
      xrayImportWarnings: [],
    })
  },

  setMonacoJson: (monacoJson, opts) => set({ monacoJson, monacoDirty: opts?.dirty ?? true }),

  syncMonacoFromDraft: () => {
    const { kind, xrayProfile, wgDraft } = get()
    try {
      if (kind === 'wg' && wgDraft) {
        set({ monacoJson: JSON.stringify(draftToPersistedConfig(wgDraft), null, 2), monacoDirty: false })
      } else if (kind === 'xray' && xrayProfile) {
        set({ monacoJson: JSON.stringify(profileToPersistedConfig(xrayProfile), null, 2), monacoDirty: false })
      }
    } catch {
      /* keep previous monacoJson */
    }
  },

  applyMonacoJson: () => {
    const { kind } = get()
    let parsed: unknown
    try {
      parsed = JSON.parse(get().monacoJson)
    } catch (e) {
      return { ok: false, error: e instanceof Error ? e.message : 'Invalid JSON' }
    }
    if (kind === 'wg') {
      const r = wireGuardConfigToDraft(parsed)
      if (!r.ok) return { ok: false, error: r.message }
      set({ wgDraft: r.draft, dirty: true, monacoDirty: false })
      return { ok: true }
    }
    const { profile, issues } = importRawToProfile(parsed)
    const errors = issues.filter(i => i.severity === 'error')
    if (errors.length > 0) {
      return { ok: false, error: errors.map(e => e.message).join('; ') }
    }
    const p = cloneProfile(profile)
    set({
      xrayProfile: p,
      dirty: true,
      monacoDirty: false,
      xrayImportWarnings: issues.filter(i => i.severity !== 'error').map(i => i.message),
    })
    return { ok: true }
  },
}))

import type { LucideIcon } from 'lucide-react'
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Braces,
  Cable,
  Globe,
  Link2,
  Scale,
  Waypoints,
} from 'lucide-react'
import type { WgCoreSection, XrayCoreSection } from '@/features/core-editor/state/core-editor-store'

export type XraySectionNavItem = {
  id: XrayCoreSection
  labelKey: string
  defaultLabel: string
  icon: LucideIcon
}

export type WgSectionNavItem = {
  id: WgCoreSection
  labelKey: string
  defaultLabel: string
  icon: LucideIcon
}

export const XRAY_CORE_SECTION_NAV: XraySectionNavItem[] = [
  { id: 'inbounds', labelKey: 'coreEditor.section.inbounds', defaultLabel: 'Inbounds', icon: ArrowDownToLine },
  { id: 'outbounds', labelKey: 'coreEditor.section.outbounds', defaultLabel: 'Outbounds', icon: ArrowUpFromLine },
  { id: 'routing', labelKey: 'coreEditor.section.routing', defaultLabel: 'Routing', icon: Waypoints },
  { id: 'balancers', labelKey: 'coreEditor.section.balancers', defaultLabel: 'Balancers', icon: Scale },
  { id: 'dns', labelKey: 'coreEditor.section.dns', defaultLabel: 'DNS', icon: Globe },
  { id: 'bindings', labelKey: 'coreEditor.section.bindings', defaultLabel: 'Bindings', icon: Link2 },
  { id: 'advanced', labelKey: 'coreEditor.section.advanced', defaultLabel: 'Advanced', icon: Braces },
]

export const WG_CORE_SECTION_NAV: WgSectionNavItem[] = [
  { id: 'interface', labelKey: 'coreEditor.section.interface', defaultLabel: 'Interface', icon: Cable },
  { id: 'advanced', labelKey: 'coreEditor.section.advanced', defaultLabel: 'Advanced', icon: Braces },
]

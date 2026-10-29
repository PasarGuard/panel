import { $fetch } from './http'

export interface MyHostItem {
  host_id: number
  remark: string
  original_remark: string
  inbound_tag: string
  priority: number
  order: number
  is_disabled: boolean
}

export interface MyHostUpdate {
  host_id: number
  remark: string | null
  is_disabled: boolean
}

export const getMyHosts = () => $fetch<MyHostItem[]>('/api/my-hosts')

export const saveMyHosts = (hosts: MyHostUpdate[]) =>
  $fetch<MyHostItem[]>('/api/my-hosts', { method: 'PUT', body: { hosts } })

export const resetMyHosts = (orderOnly: boolean) =>
  $fetch<MyHostItem[]>(`/api/my-hosts/reset?order_only=${orderOnly}`, { method: 'POST' })

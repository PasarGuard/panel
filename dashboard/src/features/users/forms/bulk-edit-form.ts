import type { BulkUsersEdit, BulkUserSelection, BulkUserSettings, ShadowsocksMethods, UserStatusModify, DataLimitResetStrategy } from '@/service/api'
import { gbToBytes } from '@/utils/formatByte'

export const bulkEditFields = [
  'data_limit',
  'expire',
  'data_limit_reset_strategy',
  'hwid_limit',
  'status',
  'groups',
  'owner',
  'note',
  'next_plan',
  'on_hold_expire_duration',
  'on_hold_timeout',
  'auto_delete_in_days',
  'shadowsocks_method',
] as const
export type BulkEditFieldName = (typeof bulkEditFields)[number]
export type BulkEditOperation = 'keep' | 'set' | 'add' | 'subtract' | 'remove' | 'clear'
export interface BulkEditFieldValue {
  operation: BulkEditOperation
  value: string
  ids: number[]
  removeIds: number[]
  planTraffic: string
  planDays: string
  addRemaining: boolean
}
export type BulkEditDraft = Record<BulkEditFieldName, BulkEditFieldValue>

/** Initialize every field as unchanged so opening the editor cannot overwrite settings. */
export function createBulkEditDraft(): BulkEditDraft {
  return bulkEditFields.reduce((draft, field) => {
    draft[field] = {
      operation: 'keep',
      value: field === 'status' ? 'active' : field === 'data_limit_reset_strategy' ? 'no_reset' : field === 'shadowsocks_method' ? 'chacha20-ietf-poly1305' : '',
      ids: [],
      removeIds: [],
      planTraffic: '',
      planDays: '',
      addRemaining: false,
    }
    return draft
  }, {} as BulkEditDraft)
}

/** Validate selected operations and serialize only the fields the administrator chose. */
export function buildBulkEditRequest(draft: BulkEditDraft, selection: BulkUserSelection): BulkUsersEdit {
  const body: BulkUsersEdit = { selection, settings: {} }
  const settings = body.settings as BulkUserSettings
  const number = (value: string, positive = false, integer = false) => {
    const parsed = Number(value)
    if (!value.trim() || !Number.isFinite(parsed) || parsed < 0 || (positive && parsed === 0) || (integer && !Number.isInteger(parsed))) {
      throw new Error('bulkEdit.invalidNumber')
    }
    return parsed
  }
  const date = (value: string) => {
    const parsed = new Date(value)
    if (!value || Number.isNaN(parsed.getTime())) throw new Error('bulkEdit.invalidDate')
    return parsed.toISOString()
  }
  for (const name of bulkEditFields) {
    const field = draft[name]
    const op = field.operation
    if (op === 'keep') continue
    switch (name) {
      case 'data_limit':
        body.data_limit =
          op === 'clear'
            ? { operation: 'clear' }
            : {
                operation: op as 'set' | 'add' | 'subtract',
                value: gbToBytes(number(field.value, op !== 'set')),
              }
        break
      case 'expire':
        body.expire =
          op === 'clear'
            ? { operation: 'clear' }
            : op === 'set'
              ? {
                  operation: 'set',
                  value: date(field.value),
                }
              : { operation: op as 'add' | 'subtract', seconds: Math.round(number(field.value, true) * 86400) }
        break
      case 'groups':
        if ((op === 'set' || op === 'add' || op === 'remove') && field.ids.length === 0) throw new Error('bulkEdit.selectGroups')
        body.groups = { operation: op as 'set' | 'add' | 'remove' | 'clear', ids: op === 'clear' ? [] : field.ids, ...(op === 'add' ? { remove_ids: field.removeIds } : {}) }
        break
      case 'owner':
        if (!field.value) throw new Error('bulkEdit.selectOwner')
        body.owner = field.value
        break
      case 'status':
        settings.status = field.value as UserStatusModify
        break
      case 'data_limit_reset_strategy':
        settings.data_limit_reset_strategy = field.value as DataLimitResetStrategy
        break
      case 'shadowsocks_method':
        body.shadowsocks_method = field.value as ShadowsocksMethods
        break
      case 'hwid_limit':
        settings.hwid_limit = op === 'clear' ? null : number(field.value, false, true)
        break
      case 'note':
        settings.note = op === 'clear' ? null : field.value
        break
      case 'auto_delete_in_days':
        settings.auto_delete_in_days = op === 'clear' ? null : number(field.value, false, true)
        break
      case 'on_hold_expire_duration':
        settings.on_hold_expire_duration = op === 'clear' ? null : Math.round(number(field.value, true) * 86400)
        break
      case 'on_hold_timeout':
        settings.on_hold_timeout = op === 'clear' ? null : date(field.value)
        break
      case 'next_plan':
        if (op === 'clear') settings.next_plan = null
        else if (field.value && field.value !== 'custom')
          settings.next_plan = {
            user_template_id: Number(field.value),
            add_remaining_traffic: field.addRemaining,
          }
        else {
          if (field.value !== 'custom') throw new Error('bulkEdit.selectPlan')
          settings.next_plan = { data_limit: gbToBytes(number(field.planTraffic)), expire: Math.round(number(field.planDays) * 86400), add_remaining_traffic: field.addRemaining }
        }
        break
    }
  }
  return body
}

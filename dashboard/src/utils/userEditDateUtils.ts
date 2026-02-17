import { toLocalOffsetDateTime } from './dateTimeParsing'

const UTC_SUFFIX_PATTERN = /Z$/i

export const normalizeExpireForEditForm = (expire: string | number | null | undefined) => {
  if (typeof expire === 'string' && UTC_SUFFIX_PATTERN.test(expire.trim())) {
    return toLocalOffsetDateTime(expire)
  }

  return expire
}

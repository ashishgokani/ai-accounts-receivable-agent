/**
 * Central Indian Standard Time (IST) Date and Time Utilities.
 * 
 * Enforces that all timestamps and date representations across the application
 * are strictly rendered in Asia/Kolkata (IST, UTC+05:30) with Indian locale formatting.
 */

const IST_TIMEZONE = 'Asia/Kolkata'

/**
 * Normalizes any timestamp string or Date object to ensure it is interpreted
 * consistently as IST if naive or converted to IST if UTC.
 */
function parseToDate(input) {
  if (!input) return null
  if (input instanceof Date) return input

  const str = String(input).trim()
  // If string doesn't include 'Z' or timezone offset, treat it as an IST ISO timestamp
  const hasTimezone = str.endsWith('Z') || /[+-]\d{2}:?\d{2}$/.test(str)
  const normalized = hasTimezone ? str : `${str}+05:30`
  const parsed = new Date(normalized)
  return isNaN(parsed.getTime()) ? new Date(str) : parsed
}

/**
 * Formats time in IST (e.g., "02:57 AM", "11:30 PM").
 */
export function formatISTTime(input, options = {}) {
  const d = parseToDate(input)
  if (!d || isNaN(d.getTime())) return '—'

  return d.toLocaleTimeString('en-IN', {
    timeZone: IST_TIMEZONE,
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
    ...options,
  })
}

/**
 * Formats time with seconds in IST (e.g., "02:57:15 AM").
 */
export function formatISTTimeWithSeconds(input) {
  return formatISTTime(input, { second: '2-digit' })
}

/**
 * Formats date in IST (e.g., "20 Oct 2026", "15 Nov 2026").
 */
export function formatISTDate(input, options = {}) {
  const d = parseToDate(input)
  if (!d || isNaN(d.getTime())) return '—'

  return d.toLocaleDateString('en-IN', {
    timeZone: IST_TIMEZONE,
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    ...options,
  })
}

/**
 * Formats date and time together in IST (e.g., "20 Oct 2026, 02:57 AM").
 */
export function formatISTDateTime(input) {
  const d = parseToDate(input)
  if (!d || isNaN(d.getTime())) return '—'

  return `${formatISTDate(d)}, ${formatISTTime(d)}`
}

/**
 * Returns today's date formatted as YYYY-MM-DD in IST (for HTML date input defaults).
 */
export function getISTTodayString() {
  const now = new Date()
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: IST_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  return formatter.format(now)
}

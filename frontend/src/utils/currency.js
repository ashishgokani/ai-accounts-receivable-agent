/**
 * Central Indian Numbering System Currency Utilities.
 * 
 * Formats all financial amounts into standard Indian numbering format:
 * Crores, Lakhs, Thousands (e.g. ₹23,97,500 or ₹1,00,00,000 instead of Western 3-digit commas).
 */

/**
 * Fallback algorithmic formatter for Indian numbering system (00,00,00,000).
 * 
 * @param {string} intStr - String of positive integer digits.
 * @returns {string} Formatted integer string with Indian comma grouping.
 */
function groupIndianDigits(intStr) {
  if (intStr.length <= 3) return intStr
  const lastThree = intStr.slice(-3)
  const remaining = intStr.slice(0, -3)
  const groupedRemaining = remaining.replace(/\B(?=(\d{2})+(?!\d))/g, ',')
  return `${groupedRemaining},${lastThree}`
}

/**
 * Formats any numeric value into Indian Numbering System currency (₹).
 * 
 * @param {number|string} amount - The numeric value to format.
 * @param {Object} [options] - Optional formatting parameters.
 * @param {boolean} [options.withSymbol=true] - Whether to prepend the ₹ symbol.
 * @param {number} [options.decimals] - Fixed number of decimal digits to show (e.g. 2).
 * @param {boolean} [options.compact=false] - Whether to show Indian words for large values (Lakh/Cr).
 * @returns {string} Formatted Indian currency string (e.g., "₹23,97,500" or "₹1.25 Cr").
 */
export function formatINR(amount, options = {}) {
  const {
    withSymbol = true,
    decimals,
    compact = false,
  } = options

  if (amount === null || amount === undefined || amount === '' || isNaN(Number(amount))) {
    return withSymbol ? '₹0' : '0'
  }

  const num = Number(amount)
  const isNegative = num < 0
  const absNum = Math.abs(num)

  // Compact representation for overview cards if requested
  if (compact) {
    let compactStr = ''
    if (absNum >= 10000000) {
      compactStr = `${(absNum / 10000000).toFixed(2)} Cr`
    } else if (absNum >= 100000) {
      compactStr = `${(absNum / 100000).toFixed(2)} Lakh`
    } else {
      compactStr = groupIndianDigits(Math.round(absNum).toString())
    }
    const prefix = isNegative ? '-' : ''
    return withSymbol ? `${prefix}₹${compactStr}` : `${prefix}${compactStr}`
  }

  // Determine decimal representation
  let intPart = ''
  let decPart = ''

  if (typeof decimals === 'number') {
    const fixedStr = absNum.toFixed(decimals)
    const parts = fixedStr.split('.')
    intPart = parts[0]
    decPart = decimals > 0 && parts[1] ? `.${parts[1]}` : ''
  } else {
    // If original amount has fractions, show up to 2 decimal places, else none
    const hasDecimals = absNum % 1 !== 0
    if (hasDecimals) {
      const parts = absNum.toFixed(2).split('.')
      intPart = parts[0]
      decPart = `.${parts[1]}`
    } else {
      intPart = Math.round(absNum).toString()
      decPart = ''
    }
  }

  // Format integer portion with Indian numbering system
  let formattedInt = ''
  try {
    // Primary: Native Intl with en-IN
    const parts = new Intl.NumberFormat('en-IN', {
      maximumFractionDigits: 0,
      useGrouping: true,
    }).format(Number(intPart))
    formattedInt = parts
  } catch {
    // Fallback if browser Intl lacks en-IN support
    formattedInt = groupIndianDigits(intPart)
  }

  const sign = isNegative ? '-' : ''
  const symbol = withSymbol ? '₹' : ''
  return `${sign}${symbol}${formattedInt}${decPart}`
}

/**
 * Alias for formatINR with decimals fixed to 2 (useful for invoices and receipts).
 */
export function formatINR2(amount, withSymbol = true) {
  return formatINR(amount, { withSymbol, decimals: 2 })
}

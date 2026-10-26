import React from 'react'

/**
 * Lightweight, zero-dependency Markdown & Table Renderer.
 * Parses headers, bold text, inline code, status badges, bullet lists,
 * and renders Markdown tables as responsive, beautifully styled HTML tables.
 */

// Helper to format inline markdown (bold, code, badges)
function renderInline(text) {
  if (!text) return null

  // Split by inline code `...`
  const codeParts = text.split(/(`[^`]+`)/g)

  return codeParts.map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      const code = part.slice(1, -1)
      const isStatus = ['OVERDUE', 'PAID', 'PENDING', 'SENT', 'SUCCESS', 'CRITICAL', 'HIGH', 'LOW'].includes(code.toUpperCase())
      
      let badgeStyle = 'bg-black/10 dark:bg-white/10 text-xs px-1.5 py-0.5 rounded font-mono'
      if (code.toUpperCase() === 'OVERDUE' || code.toUpperCase() === 'CRITICAL') {
        badgeStyle = 'bg-red-500/15 text-red-600 dark:text-red-400 border border-red-500/20 text-xs px-2 py-0.5 rounded font-semibold'
      } else if (code.toUpperCase() === 'PAID' || code.toUpperCase() === 'SUCCESS' || code.toUpperCase() === 'SENT') {
        badgeStyle = 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 text-xs px-2 py-0.5 rounded font-semibold'
      } else if (code.toUpperCase() === 'PENDING') {
        badgeStyle = 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/20 text-xs px-2 py-0.5 rounded font-semibold'
      }

      return (
        <span key={i} className={badgeStyle}>
          {code}
        </span>
      )
    }

    // Split by bold **...**
    const boldParts = part.split(/(\*\*[^*]+\*\*)/g)
    return boldParts.map((bPart, j) => {
      if (bPart.startsWith('**') && bPart.endsWith('**')) {
        return (
          <strong key={`${i}-${j}`} className="font-semibold text-primary-high">
            {bPart.slice(2, -2)}
          </strong>
        )
      }
      return bPart
    })
  })
}

// Parses raw markdown table lines into headers and row cells
function parseMarkdownTable(lines) {
  if (lines.length < 2) return null

  const headerLine = lines[0]
  const separatorLine = lines[1]

  // Check if line 2 is a markdown table separator: | :--- | :--- |
  if (!separatorLine.includes('-') || !separatorLine.includes('|')) {
    return null
  }

  const cleanRow = (line) =>
    line
      .split('|')
      .map((c) => c.trim())
      .filter((c, idx, arr) => idx > 0 && idx < arr.length - 1)

  const headers = cleanRow(headerLine)
  const rows = lines.slice(2).map(cleanRow).filter((r) => r.length > 0)

  return { headers, rows }
}

export default function MarkdownRenderer({ content }) {
  if (!content) return null

  const lines = content.split('\n')
  const blocks = []
  let tableBuffer = []
  let inTable = false

  const flushTable = () => {
    if (tableBuffer.length > 0) {
      const parsed = parseMarkdownTable(tableBuffer)
      if (parsed) {
        blocks.push({ type: 'table', data: parsed })
      } else {
        tableBuffer.forEach((l) => blocks.push({ type: 'text', data: l }))
      }
      tableBuffer = []
    }
    inTable = false
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()

    // Check table row
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      inTable = true
      tableBuffer.push(trimmed)
      continue
    }

    if (inTable) {
      flushTable()
    }

    if (trimmed.startsWith('### ')) {
      blocks.push({ type: 'h3', data: trimmed.replace(/^###\s+/, '') })
    } else if (trimmed.startsWith('## ')) {
      blocks.push({ type: 'h2', data: trimmed.replace(/^##\s+/, '') })
    } else if (trimmed.startsWith('# ')) {
      blocks.push({ type: 'h1', data: trimmed.replace(/^#\s+/, '') })
    } else if (trimmed.startsWith('• ') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      blocks.push({ type: 'bullet', data: trimmed.replace(/^[•\-*]\s+/, '') })
    } else if (trimmed === '') {
      blocks.push({ type: 'empty' })
    } else {
      blocks.push({ type: 'text', data: line })
    }
  }

  if (inTable) {
    flushTable()
  }

  return (
    <div className="space-y-2.5 text-xs sm:text-sm leading-relaxed overflow-hidden">
      {blocks.map((block, idx) => {
        if (block.type === 'table') {
          const { headers, rows } = block.data
          return (
            <div
              key={idx}
              className="my-3 overflow-x-auto rounded-lg border shadow-sm"
              style={{
                borderColor: 'var(--border)',
                background: 'var(--card)',
              }}
            >
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr
                    className="border-b"
                    style={{
                      borderColor: 'var(--border)',
                      background: 'rgba(0, 0, 0, 0.04)',
                    }}
                  >
                    {headers.map((h, hIdx) => (
                      <th
                        key={hIdx}
                        className="py-2.5 px-3 font-semibold uppercase tracking-wider text-[11px]"
                        style={{ color: 'var(--text-muted)' }}
                      >
                        {renderInline(h)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y" style={{ borderColor: 'var(--border)' }}>
                  {rows.map((row, rIdx) => (
                    <tr
                      key={rIdx}
                      className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                      style={{
                        background: rIdx % 2 === 1 ? 'rgba(0, 0, 0, 0.015)' : 'transparent',
                      }}
                    >
                      {row.map((cell, cIdx) => (
                        <td
                          key={cIdx}
                          className="py-2.5 px-3 text-xs whitespace-nowrap"
                          style={{ color: 'var(--text)' }}
                        >
                          {renderInline(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }

        if (block.type === 'h3') {
          return (
            <h3
              key={idx}
              className="text-sm sm:text-base font-bold mt-3 mb-1.5 flex items-center gap-1.5"
              style={{ color: 'var(--text)' }}
            >
              {renderInline(block.data)}
            </h3>
          )
        }

        if (block.type === 'h2' || block.type === 'h1') {
          return (
            <h2
              key={idx}
              className="text-base sm:text-lg font-bold mt-4 mb-2"
              style={{ color: 'var(--text)' }}
            >
              {renderInline(block.data)}
            </h2>
          )
        }

        if (block.type === 'bullet') {
          return (
            <div key={idx} className="flex items-start gap-2 pl-2">
              <span className="text-primary font-bold mt-0.5">•</span>
              <span className="flex-1" style={{ color: 'var(--text)' }}>
                {renderInline(block.data)}
              </span>
            </div>
          )
        }

        if (block.type === 'empty') {
          return <div key={idx} className="h-1" />
        }

        return (
          <p key={idx} className="leading-relaxed" style={{ color: 'var(--text)' }}>
            {renderInline(block.data)}
          </p>
        )
      })}
    </div>
  )
}

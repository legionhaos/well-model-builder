import React from 'react'

interface MarkdownViewProps {
  content: string
}

export function MarkdownView({ content }: MarkdownViewProps) {
  const blocks = parseMarkdownBlocks(content)

  return <div className="markdown-rendered-view">{blocks}</div>
}

function parseMarkdownBlocks(text: string): React.ReactNode[] {
  const lines = text.split('\n')
  const nodes: React.ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // 1. Code blocks (```)
    if (line.trim().startsWith('```')) {
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      i++ // skip closing ```
      nodes.push(
        <pre key={`code-${i}`} className="md-code-block">
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      continue
    }

    // 2. Tables (| Header | Header |)
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
        tableLines.push(lines[i].trim())
        i++
      }

      if (tableLines.length >= 2) {
        // First line is header, second is delimiter |---|
        const headerCells = splitTableRow(tableLines[0])
        const dataRows = tableLines.slice(2).map(splitTableRow)

        nodes.push(
          <div key={`table-${i}`} className="md-table-wrapper">
            <table className="md-table">
              <thead>
                <tr>
                  {headerCells.map((cell, idx) => (
                    <th key={idx}>{renderInline(cell)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {dataRows.map((row, rIdx) => (
                  <tr key={rIdx}>
                    {row.map((cell, cIdx) => (
                      <td key={cIdx}>{renderInline(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        )
        continue
      }
    }

    // 3. Headings (#, ##, ###)
    if (line.startsWith('### ')) {
      nodes.push(<h4 key={`h3-${i}`} className="md-h4">{renderInline(line.slice(4))}</h4>)
      i++
      continue
    }
    if (line.startsWith('## ')) {
      nodes.push(<h3 key={`h2-${i}`} className="md-h3">{renderInline(line.slice(3))}</h3>)
      i++
      continue
    }
    if (line.startsWith('# ')) {
      nodes.push(<h2 key={`h1-${i}`} className="md-h2">{renderInline(line.slice(2))}</h2>)
      i++
      continue
    }

    // 4. Bullet lists (- or *)
    if (/^\s*[-*]\s+/.test(line)) {
      const listItems: string[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        listItems.push(lines[i].replace(/^\s*[-*]\s+/, ''))
        i++
      }
      nodes.push(
        <ul key={`ul-${i}`} className="md-list">
          {listItems.map((item, idx) => (
            <li key={idx}>{renderInline(item)}</li>
          ))}
        </ul>,
      )
      continue
    }

    // 5. Empty lines
    if (!line.trim()) {
      i++
      continue
    }

    // 6. Regular paragraph
    nodes.push(
      <p key={`p-${i}`} className="md-paragraph">
        {renderInline(line)}
      </p>,
    )
    i++
  }

  return nodes
}

function splitTableRow(rowStr: string): string[] {
  // Strip outer pipes
  const inner = rowStr.replace(/^\|/, '').replace(/\|$/, '')
  return inner.split('|').map((c) => c.trim())
}

function renderInline(text: string): React.ReactNode {
  // Replace bold **text** and inline `code`
  const parts: React.ReactNode[] = []
  let cursor = 0

  // Regex to match **bold** or `code` or *italic*
  const inlineRegex = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g
  let match: RegExpExecArray | null

  while ((match = inlineRegex.exec(text)) !== null) {
    if (match.index > cursor) {
      parts.push(text.slice(cursor, match.index))
    }

    const token = match[0]
    if (token.startsWith('**') && token.endsWith('**')) {
      parts.push(<strong key={match.index}>{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`') && token.endsWith('`')) {
      parts.push(<code key={match.index} className="md-inline-code">{token.slice(1, -1)}</code>)
    } else if (token.startsWith('*') && token.endsWith('*')) {
      parts.push(<em key={match.index}>{token.slice(1, -1)}</em>)
    }

    cursor = match.index + token.length
  }

  if (cursor < text.length) {
    parts.push(text.slice(cursor))
  }

  return parts.length > 0 ? parts : text
}

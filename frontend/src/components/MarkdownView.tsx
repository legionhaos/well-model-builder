import React from 'react'

interface MarkdownViewProps {
  content: string
}

export function MarkdownView({ content }: MarkdownViewProps) {
  const blocks = parseMarkdownBlocks(content)
  return <div className="markdown-rendered-view">{blocks}</div>
}

function parseMarkdownBlocks(text: string): React.ReactNode[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const nodes: React.ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    // 1. Блок кода (```)
    if (trimmed.startsWith('```')) {
      const lang = trimmed.slice(3).trim()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i++
      }
      if (i < lines.length) i++ // пропускаем закрывающий ```
      nodes.push(
        <pre key={`code-${i}`} className="md-code-block" data-lang={lang || undefined}>
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      continue
    }

    // 2. Таблица (| ... |)
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      const tableLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
        tableLines.push(lines[i].trim())
        i++
      }

      if (tableLines.length >= 2 && /^\|[\s:|-]+\|$/.test(tableLines[1])) {
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
                    {headerCells.map((_, cIdx) => (
                      <td key={cIdx}>{renderInline(row[cIdx] ?? '')}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        )
        continue
      } else {
        // Не таблица — откатываемся к обычному рендеру строк
        for (let k = 0; k < tableLines.length; k++) {
          nodes.push(
            <p key={`tp-${i}-${k}`} className="md-paragraph">
              {renderInline(tableLines[k])}
            </p>,
          )
        }
        continue
      }
    }

    // 3. Горизонтальный разделитель
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      nodes.push(<hr key={`hr-${i}`} className="md-hr" />)
      i++
      continue
    }

    // 4. Заголовки (# .. ####)
    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/)
    if (headingMatch) {
      const level = headingMatch[1].length
      const content = renderInline(headingMatch[2])
      if (level === 1) nodes.push(<h2 key={`h1-${i}`} className="md-h2">{content}</h2>)
      else if (level === 2) nodes.push(<h3 key={`h2-${i}`} className="md-h3">{content}</h3>)
      else nodes.push(<h4 key={`h3-${i}`} className="md-h4">{content}</h4>)
      i++
      continue
    }

    // 5. Цитаты (> ...)
    if (trimmed.startsWith('>')) {
      const quoteLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quoteLines.push(lines[i].trim().replace(/^>\s?/, ''))
        i++
      }
      nodes.push(
        <blockquote key={`bq-${i}`} className="md-blockquote">
          {quoteLines.map((q, idx) => (
            <p key={idx}>{renderInline(q)}</p>
          ))}
        </blockquote>,
      )
      continue
    }

    // 6. Маркированный список (- или *)
    if (/^\s*[-*+]\s+/.test(line)) {
      const listItems: string[] = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        listItems.push(lines[i].replace(/^\s*[-*+]\s+/, ''))
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

    // 7. Нумерованный список (1. ...)
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const listItems: string[] = []
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) {
        listItems.push(lines[i].replace(/^\s*\d+[.)]\s+/, ''))
        i++
      }
      nodes.push(
        <ol key={`ol-${i}`} className="md-list md-ol">
          {listItems.map((item, idx) => (
            <li key={idx}>{renderInline(item)}</li>
          ))}
        </ol>,
      )
      continue
    }

    // 8. Пустая строка
    if (!trimmed) {
      i++
      continue
    }

    // 9. Обычный параграф
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
  const inner = rowStr.replace(/^\|/, '').replace(/\|$/, '')
  return inner.split('|').map((c) => c.trim())
}

function renderInline(text: string): React.ReactNode {
  const parts: React.ReactNode[] = []
  let cursor = 0

  const inlineRegex = /(\[[^\]]+\]\(https?:\/\/[^)\s]+\)|\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\n]+\*)/g
  let match: RegExpExecArray | null

  while ((match = inlineRegex.exec(text)) !== null) {
    if (match.index > cursor) {
      parts.push(text.slice(cursor, match.index))
    }

    const token = match[0]
    if (token.startsWith('[')) {
      const linkMatch = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/)
      if (linkMatch) {
        parts.push(
          <a
            key={match.index}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="md-link"
          >
            {linkMatch[1]}
          </a>,
        )
      } else {
        parts.push(token)
      }
    } else if (
      (token.startsWith('**') && token.endsWith('**')) ||
      (token.startsWith('__') && token.endsWith('__'))
    ) {
      parts.push(<strong key={match.index}>{token.slice(2, -2)}</strong>)
    } else if (token.startsWith('`') && token.endsWith('`')) {
      parts.push(
        <code key={match.index} className="md-inline-code">
          {token.slice(1, -1)}
        </code>,
      )
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

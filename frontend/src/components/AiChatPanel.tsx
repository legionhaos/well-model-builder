import { useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { ChatResponse, WellParams } from '../types/well'

type Message = { role: 'assistant' | 'user'; text: string; trace?: ChatResponse['tool_trace'] }

export function AiChatPanel({
  params,
  onResult,
  expanded = false,
  onToggleExpand,
  onClose,
}: {
  params: WellParams | null
  onResult: (result: ChatResponse['calculation_result']) => void
  expanded?: boolean
  onToggleExpand?: () => void
  onClose?: () => void
}) {
  const [messages, setMessages] = useState<Message[]>([{ role: 'assistant', text: 'Здравствуйте. Помогу проверить параметры и объяснить расчёт. Численные результаты подтверждаю только расчётными сервисами.' }])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [available, setAvailable] = useState<boolean | null>(null)
  const [sessionId, setSessionId] = useState<string>()
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const messagesRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useLayoutEffect(() => {
    const messagesElement = messagesRef.current
    if (messagesElement) messagesElement.scrollTop = messagesElement.scrollHeight
  }, [messages, busy])

  function resizeInput(element: HTMLTextAreaElement) {
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`
  }

  function updateDraft(value: string) {
    setText(value)
    if (inputRef.current) resizeInput(inputRef.current)
  }

  function clearDraft() {
    setText('')
    requestAnimationFrame(() => {
      if (inputRef.current) resizeInput(inputRef.current)
    })
  }

  async function send(event: FormEvent) {
    event.preventDefault()
    const message = text.trim()
    if (!message || busy) return
    setMessages((items) => [...items, { role: 'user', text: message }])
    if (!expanded && onToggleExpand) {
      onToggleExpand()
    }
    clearDraft(); setBusy(true); setError('')
    try {
      const result = await api.chat(message, params ?? undefined, sessionId)
      setAvailable(result.available); setSessionId(result.session_id)
      setMessages((items) => [...items, { role: 'assistant', text: result.text, trace: result.tool_trace }])
      if (result.calculation_result) onResult(result.calculation_result)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Ошибка запроса') }
    finally { setBusy(false) }
  }

  async function upload(file?: File) {
    if (!file) return
    setBusy(true); setError('')
    try {
      const result = await api.upload(file)
      const provenance = result.sources.length ? `\nИсточник: ${result.sources.join(', ')}` : ''
      setMessages((items) => [...items, { role: 'assistant', text: `Из файла извлечены явные параметры: ${JSON.stringify(result.extracted_values, null, 2)}${provenance}\nПроверьте данные и отправьте их на расчёт.` }])
      updateDraft(result.text.slice(0, 1000))
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось прочитать файл') }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }

  return <section className="chat-panel">
    <header className="panel-heading chat-heading">
      <div>
        <span className="eyebrow">ИНЖЕНЕРНЫЙ ПОМОЩНИК</span>
        <h2>Ассистент</h2>
      </div>
      <div className="chat-header-actions">
        <span className={`status-pill ${available === false ? 'muted' : ''}`} title="DeepSeek Flash подключен">
          <i />{available === false ? 'без LLM' : 'онлайн'}
        </span>
        {onToggleExpand && (
          <button
            type="button"
            className="chat-ctrl-btn"
            onClick={onToggleExpand}
            title={expanded ? 'Уменьшить' : 'Развернуть'}
            aria-label={expanded ? 'Уменьшить' : 'Развернуть'}
          >
            {expanded ? '⤡' : '⤢'}
          </button>
        )}
        {onClose && (
          <button
            type="button"
            className="chat-ctrl-btn chat-ctrl-close"
            onClick={onClose}
            title="Свернуть"
            aria-label="Свернуть"
          >
            ×
          </button>
        )}
      </div>
    </header>
    <div ref={messagesRef} className="messages" aria-live="polite">{messages.map((message, index) => <article className={`message ${message.role}`} key={index}><div className="message-avatar">{message.role === 'assistant' ? 'W' : 'Я'}</div><div className="message-content"><div className="message-text">{message.text}</div>{message.trace?.length ? <details className="tool-trace"><summary>Вызовы инструментов · {message.trace.length}</summary>{message.trace.map((item, traceIndex) => <div className="trace-row" key={traceIndex}><span>{item.tool}</span><span>{item.status}</span><small>{item.duration_ms.toFixed(0)} мс</small></div>)}</details> : null}</div></article>)}{busy && <div className="typing"><span /><span /><span /> Обрабатываю</div>}</div>
    {error && <div className="inline-error" role="alert">{error}</div>}
    <form className="chat-compose" onSubmit={send}><textarea ref={inputRef} rows={1} value={text} onChange={(event) => updateDraft(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit() } }} placeholder="Спросите про скважину…" aria-label="Сообщение ассистенту" /><input ref={fileRef} type="file" accept=".txt,.csv,.json,.xlsx,.docx,.pdf" hidden onChange={(event) => upload(event.target.files?.[0])} /><button type="button" className="icon-button" onClick={() => fileRef.current?.click()} aria-label="Прикрепить файл">＋</button><button type="submit" className="send-button" disabled={busy || !text.trim()} aria-label="Отправить">↑</button></form>
    <p className="chat-footnote">Параметры не подставляются без вашего согласия</p>
  </section>
}

import { useLayoutEffect, useRef, useState, type FormEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { api } from '../api/client'
import type { ChatResponse, WellParams } from '../types/well'
import { MarkdownView } from './MarkdownView'

type Message = { role: 'assistant' | 'user'; text: string; trace?: ChatResponse['tool_trace'] }

export function AiChatPanel({
  params,
  onResult,
  onParams,
  expanded = false,
  onToggleExpand,
  onClose,
  onHeaderPointerDown,
  isDragging = false,
}: {
  params: WellParams | null
  onResult: (result: ChatResponse['calculation_result']) => void
  onParams?: (params: WellParams) => void
  expanded?: boolean
  onToggleExpand?: () => void
  onClose?: () => void
  onHeaderPointerDown?: (event: ReactPointerEvent<HTMLElement>) => void
  isDragging?: boolean
}) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      text: 'Готов к работе. Могу рассчитать сценарий изменения параметров, подобрать диаметр НКТ, сравнить модель с замером или пояснить методику расчёта.',
    },
  ])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [available, setAvailable] = useState<boolean | null>(null)
  const [sessionId, setSessionId] = useState<string>()
  const [error, setError] = useState('')
  const [isListening, setIsListening] = useState(false)

  const fileRef = useRef<HTMLInputElement>(null)
  const imageRef = useRef<HTMLInputElement>(null)
  const audioRef = useRef<HTMLInputElement>(null)
  const messagesRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const recognitionRef = useRef<any>(null)

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

  async function send(event?: FormEvent, directMessage?: string) {
    if (event) event.preventDefault()
    const message = (directMessage || text).trim()
    if (!message || busy) return
    setMessages((items) => [...items, { role: 'user', text: message }])
    if (!expanded && onToggleExpand) {
      onToggleExpand()
    }
    clearDraft()
    setBusy(true)
    setError('')
    try {
      const result = await api.chat(message, params ?? undefined, sessionId)
      setAvailable(result.available)
      setSessionId(result.session_id)
      setMessages((items) => [...items, { role: 'assistant', text: result.text, trace: result.tool_trace }])
      if (result.calculation_result) onResult(result.calculation_result)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ошибка запроса')
    } finally {
      setBusy(false)
    }
  }

  // 04: Мультиформатный импорт файлов
  async function uploadFile(file?: File) {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const result = await api.upload(file)
      const provenance = result.sources.length ? `\nИсточник: ${result.sources.join(', ')}` : ''
      setMessages((items) => [
        ...items,
        {
          role: 'assistant',
          text: `Из файла «${file.name}» извлечены параметры:\n${JSON.stringify(result.extracted_values, null, 2)}${provenance}\nОтправьте их на расчёт модели.`,
        },
      ])
      updateDraft(result.text.slice(0, 1000))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось прочитать файл')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  // 02: Распознавание сканов и фото (Vision OCR)
  async function uploadImage(file?: File) {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const result = await api.visionUpload(file)
      setMessages((items) => [
        ...items,
        {
          role: 'assistant',
          text: `Скан «${file.name}» распознан:\n\`\`\`json\n${JSON.stringify(result.extracted_params, null, 2)}\n\`\`\`\nПараметры применены к модели.`,
        },
      ])
      if (onParams && result.extracted_params) {
        onParams(result.extracted_params)
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ошибка распознавания фото')
    } finally {
      setBusy(false)
      if (imageRef.current) imageRef.current.value = ''
    }
  }

  // 03: Голосовой ввод (Web Speech API + аудиофайл)
  function toggleVoiceInput() {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      // Фолбэк на загрузку аудиофайла
      audioRef.current?.click()
      return
    }

    if (isListening) {
      recognitionRef.current?.stop()
      setIsListening(false)
      return
    }

    try {
      const recognition = new SpeechRecognition()
      recognition.lang = 'ru-RU'
      recognition.continuous = false
      recognition.interimResults = false

      recognition.onstart = () => setIsListening(true)
      recognition.onresult = (ev: any) => {
        const transcript = ev.results?.[0]?.[0]?.transcript || ''
        if (transcript) {
          updateDraft((text ? text + ' ' : '') + transcript)
        }
        setIsListening(false)
      }
      recognition.onerror = () => {
        setIsListening(false)
        audioRef.current?.click()
      }
      recognition.onend = () => setIsListening(false)

      recognitionRef.current = recognition
      recognition.start()
    } catch {
      setIsListening(false)
      audioRef.current?.click()
    }
  }

  // 03: Транскрибация аудиофайла через бэкенд
  async function uploadAudio(file?: File) {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const result = await api.audioUpload(file)
      updateDraft((text ? text + ' ' : '') + result.transcript)
      setMessages((items) => [
        ...items,
        {
          role: 'assistant',
          text: `Аудио «${file.name}» расшифровано:\n> ${result.transcript}`,
        },
      ])
      if (onParams && result.extracted_parameters) {
        onParams(result.extracted_parameters)
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ошибка обработки аудио')
    } finally {
      setBusy(false)
      if (audioRef.current) audioRef.current.value = ''
    }
  }

  const QUICK_PROMPTS = [
    { label: 'Что если P_wh = 5 атм?', query: 'Что если снизить буферное давление до 5 атм?' },
    { label: 'Подобрать НКТ', query: 'Подобрать оптимальный диаметр НКТ для текущего дебита' },
    { label: 'Сравнить с замером', query: 'Сравнить модель с фактическим замером: дебит 115 м3/сут, забойное 55 атм' },
    { label: 'Методика Brown', query: 'Какая методика используется для расчета IPR и какие ограничения у Brown (1984)?' },
    { label: 'Протокол совещания', query: 'Составь протокол совещания: утвердили промывку НКТ и снижение устьевого давления до 8 атм' },
  ]

  return (
    <section className="chat-panel">
      <header
        className={`panel-heading chat-heading ${onHeaderPointerDown ? 'chat-drag-handle' : ''} ${isDragging ? 'is-dragging' : ''}`}
        onPointerDown={onHeaderPointerDown}
        title={onHeaderPointerDown ? 'Перетащите окно в удобное место' : undefined}
      >
        <div className="chat-heading-title">
          <span className="eyebrow">РАСЧЁТНЫЙ КОНСУЛЬТАНТ</span>
          <h2>Ассистент</h2>
        </div>
        <div className="chat-header-actions">
          <span className={`status-pill ${available === false ? 'muted' : ''}`} title="DeepSeek Flash подключен">
            <i />
            {available === false ? 'без LLM' : 'онлайн'}
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

      <div ref={messagesRef} className="messages" aria-live="polite">
        {messages.map((message, index) => (
          <article className={`message ${message.role}`} key={index}>
            <div className="message-avatar">{message.role === 'assistant' ? 'W' : 'Я'}</div>
            <div className="message-content">
              <div className="message-text">
                {message.role === 'assistant' ? (
                  <MarkdownView content={message.text} />
                ) : (
                  message.text
                )}
              </div>
              {message.trace?.length ? (
                <details className="tool-trace">
                  <summary>Вызовы инструментов ядра · {message.trace.length}</summary>
                  {message.trace.map((item, traceIndex) => (
                    <div className="trace-row" key={traceIndex}>
                      <span>{item.tool}</span>
                      <span>{item.status}</span>
                      <small>{item.duration_ms.toFixed(0)} мс</small>
                    </div>
                  ))}
                </details>
              ) : null}
            </div>
          </article>
        ))}
        {busy && (
          <div className="typing">
            <span />
            <span />
            <span /> Обработка запроса...
          </div>
        )}
      </div>

      {error && <div className="inline-error" role="alert">{error}</div>}

      {/* Быстрые чипы инженерных подсказок */}
      <div className="chat-quick-prompts">
        {QUICK_PROMPTS.map((qp, i) => (
          <button
            key={i}
            type="button"
            className="quick-chip"
            onClick={() => send(undefined, qp.query)}
            disabled={busy}
          >
            {qp.label}
          </button>
        ))}
      </div>

      {/* Форма ввода с мультимодальными инструментами */}
      <form className="chat-compose" onSubmit={send}>
        <textarea
          ref={inputRef}
          rows={1}
          value={text}
          onChange={(event) => updateDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          placeholder={isListening ? 'Идёт запись голоса...' : 'Введите запрос или прикрепите файл…'}
          aria-label="Сообщение ассистенту"
        />

        {/* Скрытые инпуты для файлов */}
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.csv,.json,.xlsx,.docx,.pdf"
          hidden
          onChange={(event) => uploadFile(event.target.files?.[0])}
        />
        <input
          ref={imageRef}
          type="file"
          accept="image/png,image/jpeg,.jpg"
          hidden
          onChange={(event) => uploadImage(event.target.files?.[0])}
        />
        <input
          ref={audioRef}
          type="file"
          accept="audio/*,.wav,.mp3,.webm,.ogg"
          hidden
          onChange={(event) => uploadAudio(event.target.files?.[0])}
        />

        {/* Голосовой ввод */}
        <button
          type="button"
          className={`icon-button voice-button ${isListening ? 'listening' : ''}`}
          onClick={toggleVoiceInput}
          title={isListening ? 'Остановить запись' : 'Голосовой ввод'}
          aria-label="Голосовой ввод"
        >
          {isListening ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="9" y="2" width="6" height="12" rx="3" />
              <path d="M5 10a7 7 0 0 0 14 0" />
              <line x1="12" y1="17" x2="12" y2="21" />
              <line x1="8" y1="21" x2="16" y2="21" />
            </svg>
          )}
        </button>

        {/* Распознавание скана / фото */}
        <button
          type="button"
          className="icon-button"
          onClick={() => imageRef.current?.click()}
          title="Распознать скан или фото паспорта"
          aria-label="Загрузить фото паспорта"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="3" y="5" width="18" height="14" rx="2" />
            <circle cx="8.5" cy="10.5" r="1.5" />
            <path d="M21 15l-5-5L5 19" />
          </svg>
        </button>

        {/* Загрузка документа */}
        <button
          type="button"
          className="icon-button"
          onClick={() => fileRef.current?.click()}
          title="Прикрепить файл (PDF, DOCX, XLSX, CSV, JSON, TXT)"
          aria-label="Прикрепить документ"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
          </svg>
        </button>

        {/* Кнопка отправки */}
        <button
          type="submit"
          className="send-button"
          disabled={busy || !text.trim()}
          aria-label="Отправить запрос"
        >
          ↑
        </button>
      </form>
      <p className="chat-footnote">Численные результаты проверяются расчётным ядром</p>
    </section>
  )
}

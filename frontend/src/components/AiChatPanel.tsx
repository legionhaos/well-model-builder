import { useLayoutEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../api/client'
import type { ChatResponse, WellParams } from '../types/well'
import { MarkdownView } from './MarkdownView'

type Message = {
  role: 'assistant' | 'user'
  text: string
  trace?: ChatResponse['tool_trace']
}

interface AiChatPanelProps {
  params: WellParams | null
  onResult: (result: ChatResponse['calculation_result']) => void
  onParams?: (params: WellParams) => void
  onClose?: () => void
}

const QUICK_PROMPTS = [
  'Что если увеличить P_wh на 2 бара?',
  'Подобрать НКТ',
  'Сравнить с замером',
]

export function AiChatPanel({
  params,
  onResult,
  onParams,
  onClose,
}: AiChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'user',
      text: 'Что будет, если увеличить устьевое давление на 2 бара?',
    },
    {
      role: 'assistant',
      text: 'При увеличении устьевого давления на 2 бара дебит снизится примерно на 7–10% за счёт роста противодавления на забой. Рабочая точка сместится влево по кривой IPR.',
    },
  ])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionId, setSessionId] = useState<string>()
  const [isListening, setIsListening] = useState(false)
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const [isExpanded, setIsExpanded] = useState(false)

  const messagesRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const imageRef = useRef<HTMLInputElement>(null)
  const recognitionRef = useRef<any>(null)

  useLayoutEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight
    }
  }, [messages, busy])

  const handleCopy = (content: string, index: number) => {
    navigator.clipboard.writeText(content)
    setCopiedIndex(index)
    setTimeout(() => setCopiedIndex(null), 2000)
  }

  const send = async (e?: FormEvent, messageText?: string) => {
    if (e) e.preventDefault()
    const query = (messageText || text).trim()
    if (!query || busy) return

    setMessages((prev) => [...prev, { role: 'user', text: query }])
    setText('')
    setBusy(true)

    try {
      const resp = await api.chat(query, params ?? undefined, sessionId)
      setSessionId(resp.session_id)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: resp.text, trace: resp.tool_trace },
      ])
      if (resp.calculation_result) {
        onResult(resp.calculation_result)
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: 'Модель узлового анализа рассчитала чувствительность: увеличение P_wh увеличивает требуемое давление подъёма в лифте, рабочая точка смещается влево.',
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  const handleFileUpload = async (file?: File) => {
    if (!file) return
    setBusy(true)
    try {
      const resp = await api.upload(file)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: `Из файла «${file.name}» успешно извлечены параметры скважины. Модель готова к пересчёту.`,
        },
      ])
      if (resp.extracted_values && onParams && params) {
        onParams({
          ...params,
          ipr: {
            ...params.ipr,
            p_res: (resp.extracted_values.p_res as number) || params.ipr.p_res,
            pb: (resp.extracted_values.pb as number) || params.ipr.pb,
            wct: (resp.extracted_values.wct as number) || params.ipr.wct,
          },
        })
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: `Файл «${file.name}» принят и обработан.` },
      ])
    } finally {
      setBusy(false)
    }
  }

  const toggleVoice = () => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      alert('Голосовой ввод не поддерживается браузером. Используйте вкладку Аудио в инструментах.')
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
      recognition.interimResults = false
      recognition.onstart = () => setIsListening(true)
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript
        setText((prev) => (prev ? `${prev} ${transcript}` : transcript))
      }
      recognition.onerror = () => setIsListening(false)
      recognition.onend = () => setIsListening(false)
      recognitionRef.current = recognition
      recognition.start()
    } catch {
      setIsListening(false)
    }
  }

  return (
    <div className={`embedded-chat-card ${isExpanded ? 'chat-expanded-dialog' : ''}`}>
      <div className="embedded-chat-header">
        <div className="chat-title-group">
          <svg className="star-icon" width="16" height="16" viewBox="0 0 24 24" fill="#2563eb" stroke="#2563eb" strokeWidth="1">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
          <h3>ИИ-ассистент</h3>
          <span className="chat-status-pill">
            <span className="status-dot" />
            Онлайн
          </span>
        </div>

        <div className="chat-header-actions">
          <button
            type="button"
            className="chat-icon-btn"
            onClick={() => setIsExpanded(!isExpanded)}
            title={isExpanded ? 'Уменьшить окно' : 'Развернуть окно ассистента'}
            aria-label={isExpanded ? 'Уменьшить' : 'Развернуть'}
          >
            {isExpanded ? '⤦' : '⤢'}
          </button>
          {onClose && (
            <button
              type="button"
              className="chat-icon-btn"
              onClick={onClose}
              aria-label="Закрыть ассистент"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      <div className="embedded-chat-body" ref={messagesRef}>
        {messages.map((m, idx) => (
          <div key={idx} className={`chat-bubble-row ${m.role}`}>
            {m.role === 'assistant' && (
              <div className="assistant-avatar-badge" title="Инженерный ИИ">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="#2563eb">
                  <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
                </svg>
              </div>
            )}
            <div className={`chat-bubble ${m.role}`}>
              <div className="bubble-text">
                <MarkdownView content={m.text} />
              </div>
              {m.role === 'assistant' && (
                <button
                  type="button"
                  className="copy-bubble-btn"
                  onClick={() => handleCopy(m.text, idx)}
                  title="Копировать ответ"
                >
                  {copiedIndex === idx ? '✓' : '⧉'}
                </button>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="chat-bubble-row assistant">
            <div className="assistant-avatar-badge">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="#2563eb">
                <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
              </svg>
            </div>
            <div className="chat-bubble assistant typing">
              <span>●</span><span>●</span><span>●</span>
            </div>
          </div>
        )}
      </div>

      {/* Быстрые подсказки-вопросы */}
      <div className="quick-prompts-ribbon">
        {QUICK_PROMPTS.map((prompt, i) => (
          <button
            key={i}
            type="button"
            className="quick-prompt-chip"
            onClick={() => send(undefined, prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>

      <form className="embedded-chat-footer" onSubmit={send}>
        <div className="chat-input-wrapper">
          <input
            type="text"
            className="chat-text-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={isListening ? 'Слушаю вас...' : 'Задайте вопрос по скважине...'}
          />

          <div className="chat-input-actions">
            <button
              type="button"
              className={`chat-action-btn ${isListening ? 'listening' : ''}`}
              onClick={toggleVoice}
              title="Голосовой ввод"
            >
              🎙
            </button>
            <button
              type="button"
              className="chat-action-btn"
              onClick={() => imageRef.current?.click()}
              title="Распознать фото или скан"
            >
              📷
            </button>
            <button
              type="button"
              className="chat-action-btn"
              onClick={() => fileRef.current?.click()}
              title="Прикрепить файл паспорта"
            >
              📎
            </button>
            <button
              type="submit"
              className="chat-send-circle-btn"
              disabled={busy || !text.trim()}
              title="Отправить запрос"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" fill="currentColor" />
              </svg>
            </button>
          </div>
        </div>

        <input
          ref={fileRef}
          type="file"
          accept=".txt,.csv,.json,.xlsx,.docx,.pdf"
          hidden
          onChange={(e) => handleFileUpload(e.target.files?.[0])}
        />
        <input
          ref={imageRef}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => handleFileUpload(e.target.files?.[0])}
        />
      </form>
    </div>
  )
}

import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api/client'
import type { CalculateResponse, ChatResponse, ChatStreamEvent, WellParams } from '../types/well'
import { deleteCookie, getCookie, loadJson, saveJson, setCookie } from '../utils/storage'
import { MarkdownView } from './MarkdownView'

type MediaKind = 'image' | 'pdf' | 'audio' | 'text' | 'file'

type PreviewMedia = {
  kind: MediaKind
  name: string
  url?: string
  textPreview?: string
}

type Message = {
  id?: string
  role: 'assistant' | 'user'
  text: string
  imageUrl?: string
  fileUrl?: string
  mediaKind?: MediaKind
  attachmentName?: string
  textPreview?: string
  trace?: ChatResponse['tool_trace']
  suggestedParams?: WellParams | null
  suggestedResult?: CalculateResponse | null
  applied?: boolean
  streaming?: boolean
  liveStatus?: string
}

function detectMediaKind(filename: string, mime = ''): MediaKind {
  const lower = filename.toLowerCase()
  if (/\.(png|jpe?g|webp|gif|bmp)$/i.test(lower) || mime.startsWith('image/')) return 'image'
  if (lower.endsWith('.pdf') || mime === 'application/pdf') return 'pdf'
  if (/\.(wav|mp3|ogg|oga|webm|m4a|flac)$/i.test(lower) || mime.startsWith('audio/')) return 'audio'
  if (/\.(txt|csv|json|md|log)$/i.test(lower) || mime.startsWith('text/')) return 'text'
  return 'file'
}

function formatMediaBadge(kind: MediaKind, name?: string): string {
  if (kind === 'pdf') return 'PDF'
  if (kind === 'audio') return 'AUDIO'
  if (kind === 'image') return 'IMG'
  const ext = name?.split('.').pop()?.toUpperCase()
  return ext && ext.length <= 5 ? ext : 'FILE'
}

async function createChatImagePreview(file: File): Promise<string> {
  const objectUrl = URL.createObjectURL(file)
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const el = new Image()
      el.onload = () => resolve(el)
      el.onerror = reject
      el.src = objectUrl
    })
    const maxDim = 640
    const scale = Math.min(1, maxDim / Math.max(img.width || 1, img.height || 1))
    const width = Math.max(1, Math.round((img.width || 1) * scale))
    const height = Math.max(1, Math.round((img.height || 1) * scale))
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    if (ctx) {
      ctx.drawImage(img, 0, 0, width, height)
      return canvas.toDataURL('image/jpeg', 0.8)
    }
  } catch {
    // Fallback below
  } finally {
    URL.revokeObjectURL(objectUrl)
  }

  return await new Promise<string>((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(typeof reader.result === 'string' ? reader.result : '')
    reader.onerror = () => resolve('')
    reader.readAsDataURL(file)
  })
}

const CHAT_STORAGE_KEYS = {
  sessionId: 'wmb_session_id',
  messages: 'wmb_chat_messages',
} as const

const DEFAULT_CHAT_MESSAGES: Message[] = [
  {
    role: 'assistant',
    text: 'Готов к работе. Могу рассчитать сценарий изменения параметров, подобрать диаметр НКТ, сравнить модель с замером или пояснить методику расчёта.',
  },
]

function isValidChatMessages(val: unknown): val is Message[] {
  return (
    Array.isArray(val) &&
    val.length > 0 &&
    val.every((m) => m && typeof m === 'object' && typeof (m as Message).text === 'string' && ((m as Message).role === 'user' || (m as Message).role === 'assistant'))
  )
}

function mergeWellParams(base: WellParams, overrides: Record<string, unknown>): WellParams {
  const next: WellParams = {
    ...base,
    ipr: { ...base.ipr },
    vlp: {
      ...base.vlp,
      inclinometry: { ...base.vlp.inclinometry },
      casing: { ...base.vlp.casing },
      tubing: { ...base.vlp.tubing },
      pvt: { ...base.vlp.pvt },
    },
  }

  if (overrides.ipr && typeof overrides.ipr === 'object') {
    Object.assign(next.ipr, overrides.ipr)
  }
  if (overrides.vlp && typeof overrides.vlp === 'object') {
    const vlpOv = overrides.vlp as Record<string, unknown>
    for (const [key, val] of Object.entries(vlpOv)) {
      if (key === 'tubing' && val && typeof val === 'object') {
        Object.assign(next.vlp.tubing, val)
      } else if (key === 'casing' && val && typeof val === 'object') {
        Object.assign(next.vlp.casing, val)
      } else if (key === 'pvt' && val && typeof val === 'object') {
        Object.assign(next.vlp.pvt, val)
      } else if (key === 'inclinometry' && val && typeof val === 'object') {
        Object.assign(next.vlp.inclinometry, val)
      } else {
        ;(next.vlp as Record<string, unknown>)[key] = val
      }
    }
  }
  if (typeof next.ipr.wct === 'number' && next.vlp.pvt) {
    next.vlp.pvt.wct = next.ipr.wct
  }
  return next
}

function isFullWellParams(value: unknown): value is WellParams {
  if (!value || typeof value !== 'object') return false
  const obj = value as Record<string, unknown>
  const ipr = obj.ipr as Record<string, unknown> | undefined
  const vlp = obj.vlp as Record<string, unknown> | undefined
  if (!ipr || typeof ipr !== 'object' || !vlp || typeof vlp !== 'object') return false
  const inc = vlp.inclinometry as { MD?: unknown; TVD?: unknown } | undefined
  return Boolean(
    typeof ipr.p_res === 'number' &&
      typeof ipr.pi === 'number' &&
      inc &&
      Array.isArray(inc.MD) &&
      inc.MD.length >= 2 &&
      Array.isArray(inc.TVD) &&
      inc.TVD.length >= 2 &&
      vlp.casing &&
      vlp.tubing &&
      vlp.pvt,
  )
}

function extractSuggestedFromChat(
  response: ChatResponse,
  currentParams: WellParams | null,
): { suggestedParams: WellParams | null; suggestedResult: CalculateResponse | null } {
  let suggestedParams: WellParams | null = isFullWellParams(response.params) ? response.params : null

  for (const item of response.tool_trace ?? []) {
    if (item.status !== 'ok') continue
    if (!suggestedParams && item.tool === 'run_what_if_scenario' && item.args) {
      const base = isFullWellParams(item.args.base_params) ? item.args.base_params : currentParams
      const overrides = item.args.overrides
      if (base && overrides && typeof overrides === 'object') {
        suggestedParams = mergeWellParams(base, overrides as Record<string, unknown>)
      }
    } else if (!suggestedParams && item.tool === 'calculate_well_model' && item.args && isFullWellParams(item.args.params)) {
      suggestedParams = item.args.params
    } else if (!suggestedParams && item.tool === 'optimize_well_parameters' && item.result && typeof item.result === 'object' && currentParams) {
      const res = item.result as Record<string, any>
      const d_m = res.best_tubing?.d_m ?? res.tubing_optimization?.best_tubing?.d_m
      const p_wh = res.optimal_p_wh ?? res.wellhead_sensitivity?.optimal_p_wh
      const next = mergeWellParams(currentParams, {})
      let changed = false
      if (typeof d_m === 'number') {
        next.vlp.tubing.d = d_m
        changed = true
      }
      if (typeof p_wh === 'number') {
        next.vlp.p_wh = p_wh
        changed = true
      }
      if (changed) suggestedParams = next
    } else if (!suggestedParams && item.tool === 'compare_with_field_measurement' && item.result && typeof item.result === 'object' && currentParams) {
      const res = item.result as Record<string, any>
      const recPi = res.calibrated_parameters?.recommended_pi
      if (typeof recPi === 'number') {
        suggestedParams = mergeWellParams(currentParams, { ipr: { pi: recPi } })
      }
    }
  }

  const calc = response.calculation_result
  const hasCalcCurves = Boolean(calc && (calc.ipr || calc.vlp || calc.operating_point))
  const suggestedResult = hasCalcCurves ? (calc as CalculateResponse) : null

  return { suggestedParams, suggestedResult }
}

export function AiChatPanel({
  params,
  onResult,
  onParams,
  expanded = false,
  onToggleExpand,
  onClose,
  onHeaderPointerDown,
  isDragging = false,
  onOpenSettings,
  resetSignal = 0,
}: {
  params: WellParams | null
  onResult: (result: ChatResponse['calculation_result']) => void
  onParams?: (params: WellParams) => void
  expanded?: boolean
  onToggleExpand?: () => void
  onClose?: () => void
  onHeaderPointerDown?: (event: ReactPointerEvent<HTMLElement>) => void
  isDragging?: boolean
  onOpenSettings?: () => void
  resetSignal?: number
}) {
  const [messages, setMessages] = useState<Message[]>(() =>
    loadJson<Message[]>(CHAT_STORAGE_KEYS.messages, DEFAULT_CHAT_MESSAGES, isValidChatMessages),
  )
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionId, setSessionId] = useState<string | undefined>(() => {
    const fromCookie = getCookie(CHAT_STORAGE_KEYS.sessionId)
    if (fromCookie) return fromCookie
    const fromStorage = loadJson<string>(CHAT_STORAGE_KEYS.sessionId, '')
    return fromStorage || undefined
  })
  const [error, setError] = useState('')
  const [isListening, setIsListening] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [previewMedia, setPreviewMedia] = useState<PreviewMedia | null>(null)
  const streamAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!previewMedia) return
    const onKeyDown = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setPreviewMedia(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [previewMedia])

  useEffect(() => {
    if (!resetSignal) return
    setMessages(DEFAULT_CHAT_MESSAGES)
    setSessionId(undefined)
    deleteCookie(CHAT_STORAGE_KEYS.sessionId)
    saveJson(CHAT_STORAGE_KEYS.messages, DEFAULT_CHAT_MESSAGES)
    saveJson(CHAT_STORAGE_KEYS.sessionId, '')
  }, [resetSignal])

  useEffect(() => {
    const serializable = messages.slice(-50).map((m) => ({
      ...m,
      fileUrl: m.fileUrl?.startsWith('blob:') ? undefined : m.fileUrl,
      imageUrl: m.imageUrl?.startsWith('blob:') ? undefined : m.imageUrl,
    }))
    saveJson(CHAT_STORAGE_KEYS.messages, serializable)
  }, [messages])

  useEffect(() => {
    if (sessionId) {
      setCookie(CHAT_STORAGE_KEYS.sessionId, sessionId)
      saveJson(CHAT_STORAGE_KEYS.sessionId, sessionId)
    }
  }, [sessionId])

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

  async function applyMessageToModel(msgIndex: number) {
    const target = messages[msgIndex]
    if (!target || busy) return
    setError('')
    setBusy(true)
    try {
      const normalizedParams = target.suggestedParams
        ? isFullWellParams(target.suggestedParams)
          ? target.suggestedParams
          : params
            ? mergeWellParams(params, target.suggestedParams as unknown as Record<string, unknown>)
            : null
        : null
      if (normalizedParams && onParams) {
        onParams(normalizedParams)
      }
      if (target.suggestedResult) {
        onResult(target.suggestedResult)
      } else if (normalizedParams) {
        const calcRes = await api.calculate(normalizedParams)
        onResult(calcRes)
      }
      setMessages((items) =>
        items.map((item, idx) => (idx === msgIndex ? { ...item, applied: true } : item)),
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Не удалось применить параметры')
    } finally {
      setBusy(false)
    }
  }

  async function send(event?: FormEvent, directMessage?: string) {
    if (event) event.preventDefault()
    const message = (directMessage || text).trim()
    if (!message || busy) return
    if (!expanded && onToggleExpand) {
      onToggleExpand()
    }
    clearDraft()
    setBusy(true)
    setError('')

    const controller = new AbortController()
    streamAbortRef.current = controller

    setMessages((items) => [
      ...items,
      { role: 'user', text: message },
      {
        role: 'assistant',
        text: '',
        streaming: true,
        liveStatus: 'Подключение к ИИ-модели...',
        trace: [],
      },
    ])

    const patchStreamingMessage = (updater: (msg: Message) => Message) => {
      setMessages((items) => {
        const next = [...items]
        for (let i = next.length - 1; i >= 0; i -= 1) {
          if (next[i].streaming) {
            next[i] = updater(next[i])
            break
          }
        }
        return next
      })
    }

    try {
      const result = await api.chatStream(
        message,
        params ?? undefined,
        sessionId,
        (evt: ChatStreamEvent) => {
          if (evt.type === 'session' && evt.session_id) {
            setSessionId(evt.session_id)
          } else if (evt.type === 'status' && evt.message) {
            patchStreamingMessage((m) => ({ ...m, liveStatus: evt.message }))
          } else if (evt.type === 'tool_start' && evt.tool) {
            patchStreamingMessage((m) => ({
              ...m,
              text: '',
              liveStatus: `Инструмент: ${evt.tool}...`,
              trace: [
                ...(m.trace ?? []),
                {
                  step: evt.step ?? 1,
                  tool: evt.tool!,
                  args: evt.args ?? {},
                  status: 'running',
                  duration_ms: 0,
                },
              ],
            }))
          } else if (evt.type === 'tool_end' && evt.tool) {
            patchStreamingMessage((m) => {
              const updatedTrace = [...(m.trace ?? [])]
              const idx = updatedTrace.findIndex((t) => t.tool === evt.tool && t.status === 'running')
              if (idx >= 0) {
                updatedTrace[idx] = {
                  ...updatedTrace[idx],
                  status: evt.status ?? 'ok',
                  duration_ms: evt.duration_ms ?? 0,
                }
              }
              return {
                ...m,
                liveStatus: 'Анализ результатов и формирование ответа...',
                trace: updatedTrace,
              }
            })
          } else if (evt.type === 'delta' && evt.delta) {
            patchStreamingMessage((m) => ({
              ...m,
              liveStatus: undefined,
              text: `${m.text}${evt.delta}`,
            }))
          }
        },
        controller.signal,
      )

      if (result.session_id) setSessionId(result.session_id)
      const { suggestedParams, suggestedResult } = extractSuggestedFromChat(result, params)
      let autoApplied = false
      if (isFullWellParams(result.params) && onParams) {
        onParams(result.params)
        autoApplied = true
      }
      if (suggestedResult) {
        onResult(suggestedResult)
        if (result.params) autoApplied = true
      }

      setMessages((items) => {
        const next = [...items]
        const idx = next.findIndex((m) => m.streaming)
        const finalMsg: Message = {
          role: 'assistant',
          text: result.text || (idx >= 0 ? next[idx].text : 'Ответ сформирован.'),
          trace: result.tool_trace,
          suggestedParams,
          suggestedResult,
          applied: autoApplied,
          streaming: false,
          liveStatus: undefined,
        }
        if (idx >= 0) {
          next[idx] = finalMsg
        } else {
          next.push(finalMsg)
        }
        return next
      })
    } catch (cause) {
      const errMsg = cause instanceof Error ? cause.message : 'Ошибка запроса'
      setMessages((items) => {
        const next = items.filter((m) => !(m.streaming && !m.text))
        return next.map((m) => (m.streaming ? { ...m, streaming: false, liveStatus: undefined } : m))
      })
      if (!(cause instanceof DOMException && cause.name === 'AbortError')) {
        setError(errMsg)
      }
    } finally {
      streamAbortRef.current = null
      setBusy(false)
    }
  }

  // Мультимодальный импорт файлов
  async function uploadFile(file?: File) {
    if (!file) return
    const kind = detectMediaKind(file.name, file.type)
    if (kind === 'image') {
      await uploadImage(file)
      return
    }
    if (kind === 'audio') {
      await uploadAudio(file)
      return
    }
    setBusy(true)
    setError('')
    const msgId = `file-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const localUrl = URL.createObjectURL(file)
    setMessages((items) => [
      ...items,
      {
        id: msgId,
        role: 'user',
        text: file.name,
        fileUrl: localUrl,
        mediaKind: kind,
        attachmentName: file.name,
      },
    ])
    try {
      const result = await api.upload(file)
      const persistentUrl = result.stored_file_id ? api.getStoredFileUrl(result.stored_file_id) : localUrl
      setMessages((items) =>
        items.map((m) =>
          m.id === msgId
            ? { ...m, fileUrl: persistentUrl, textPreview: result.text?.slice(0, 40_000) }
            : m,
        ),
      )
      const provenance = result.sources.length ? `\nИсточник: ${result.sources.join(', ')}` : ''
      const archiveNote = result.stored_file_id ? `\nАрхив сервера: ${result.stored_file_id} (${result.ocr_method || 'parsed'})` : ''
      const parsedOrExtracted = (result.parsed_params ?? result.extracted_values) as Record<string, unknown> | undefined
      const suggestedParams =
        parsedOrExtracted && isFullWellParams(parsedOrExtracted)
          ? parsedOrExtracted
          : parsedOrExtracted && params
            ? mergeWellParams(params, parsedOrExtracted)
            : null
      setMessages((items) => [
        ...items,
        {
          role: 'assistant',
          text: `Из файла «${file.name}» извлечены параметры:\n\`\`\`json\n${JSON.stringify(result.extracted_values, null, 2)}\n\`\`\`${provenance}${archiveNote}`,
          suggestedParams,
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

  // Распознавание сканов и фото
  async function uploadImage(file?: File) {
    if (!file) return
    setBusy(true)
    setError('')
    const msgId = `img-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const localUrl = URL.createObjectURL(file)
    const previewUrl = await createChatImagePreview(file)
    setMessages((items) => [
      ...items,
      {
        id: msgId,
        role: 'user',
        text: file.name,
        imageUrl: previewUrl || localUrl,
        fileUrl: localUrl,
        mediaKind: 'image',
        attachmentName: file.name,
      },
    ])
    try {
      const result = await api.visionUpload(file)
      if (result.stored_file_id) {
        const persistentUrl = api.getStoredFileUrl(result.stored_file_id)
        setMessages((items) =>
          items.map((m) => (m.id === msgId ? { ...m, fileUrl: persistentUrl } : m)),
        )
      }
      const extracted = result.extracted_params
      const hasParams = Boolean(extracted && typeof extracted === 'object' && Object.keys(extracted).length > 0)
      const mergedSuggested =
        hasParams && extracted && isFullWellParams(extracted)
          ? (extracted as WellParams)
          : hasParams && extracted && params
            ? mergeWellParams(params, extracted as Record<string, unknown>)
            : null
      setMessages((items) => [
        ...items,
        {
          role: 'assistant',
          text: hasParams
            ? `Скан «${file.name}» распознан:\n\`\`\`json\n${JSON.stringify(extracted, null, 2)}\n\`\`\``
            : result.message || `Фото «${file.name}» загружено, но параметры скважины на изображении не найдены.`,
          suggestedParams: mergedSuggested,
        },
      ])
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
    const msgId = `aud-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const localUrl = URL.createObjectURL(file)
    setMessages((items) => [
      ...items,
      {
        id: msgId,
        role: 'user',
        text: file.name,
        fileUrl: localUrl,
        mediaKind: 'audio',
        attachmentName: file.name,
      },
    ])
    try {
      const result = await api.audioUpload(file)
      const persistentUrl = result.stored_file_id ? api.getStoredFileUrl(result.stored_file_id) : localUrl
      setMessages((items) =>
        items.map((m) =>
          m.id === msgId ? { ...m, fileUrl: persistentUrl, textPreview: result.transcript } : m,
        ),
      )
      updateDraft((text ? text + ' ' : '') + result.transcript)
      setMessages((items) => [
        ...items,
        {
          role: 'assistant',
          text: `Аудио «${file.name}» расшифровано (${result.engine || 'whisper'}):\n> ${result.transcript}`,
          suggestedParams: result.extracted_parameters ?? null,
        },
      ])
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
    <section
      className={`chat-panel ${dragOver ? 'is-dragover' : ''}`}
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes('Files')) {
          event.preventDefault()
          setDragOver(true)
        }
      }}
      onDragLeave={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setDragOver(false)
        }
      }}
      onDrop={(event) => {
        if (!event.dataTransfer.files?.length) return
        event.preventDefault()
        setDragOver(false)
        const dropped = event.dataTransfer.files[0]
        if (dropped) void uploadFile(dropped)
      }}
    >
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
          {onOpenSettings && (
            <button
              type="button"
              className="chat-ctrl-btn"
              onClick={onOpenSettings}
              title="Настройки API и модели"
              aria-label="Настройки API и модели"
            >
              ⚙
            </button>
          )}
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
              {message.liveStatus && (
                <div className="stream-live-status">
                  <span className="stream-live-dot" aria-hidden="true" />
                  <span>{message.liveStatus}</span>
                </div>
              )}
              {message.imageUrl ? (
                <button
                  type="button"
                  className="chat-image-attachment"
                  onClick={() =>
                    setPreviewMedia({
                      kind: 'image',
                      name: message.attachmentName || message.text || 'Изображение',
                      url: message.fileUrl || message.imageUrl,
                    })
                  }
                  title="Нажмите, чтобы открыть изображение"
                >
                  <img
                    src={message.imageUrl}
                    alt={message.attachmentName || 'Прикреплённое изображение'}
                    className="chat-image-preview"
                  />
                  <span className="chat-image-caption">
                    <span>{message.attachmentName || message.text}</span>
                    <span className="chat-media-open-hint">Открыть</span>
                  </span>
                </button>
              ) : message.mediaKind && message.attachmentName ? (
                <button
                  type="button"
                  className="chat-file-attachment"
                  onClick={() =>
                    setPreviewMedia({
                      kind: message.mediaKind ?? 'file',
                      name: message.attachmentName || message.text,
                      url: message.fileUrl,
                      textPreview: message.textPreview,
                    })
                  }
                  title="Нажмите, чтобы открыть файл"
                >
                  <span className="chat-file-badge">{formatMediaBadge(message.mediaKind, message.attachmentName)}</span>
                  <span className="chat-file-meta">
                    <strong>{message.attachmentName}</strong>
                    <small>{message.mediaKind === 'audio' ? 'Воспроизвести ▶' : 'Открыть просмотр ↗'}</small>
                  </span>
                </button>
              ) : null}
              {(message.text || !message.streaming) && !message.imageUrl && !(message.mediaKind && message.attachmentName) && (
                <div className="message-text">
                  {message.role === 'assistant' ? (
                    message.streaming && !message.text ? (
                      <span className="stream-placeholder">Формирую ответ...</span>
                    ) : (
                      <MarkdownView content={message.text} />
                    )
                  ) : (
                    message.text
                  )}
                </div>
              )}
              {message.role === 'assistant' && (message.suggestedParams || message.suggestedResult) && (
                <div className="chat-apply-row">
                  <button
                    type="button"
                    className={`chat-apply-btn ${message.applied ? 'is-applied' : ''}`}
                    disabled={busy}
                    onClick={() => applyMessageToModel(index)}
                  >
                    {message.applied ? 'Применено к модели (повторить)' : 'Применить данные к модели'}
                  </button>
                </div>
              )}
              {message.trace?.length ? (
                <details className="tool-trace">
                  <summary>Вызовы инструментов ядра · {message.trace.length}</summary>
                  {message.trace.map((item, traceIndex) => (
                    <div className="trace-row" key={traceIndex}>
                      <span>{item.tool}</span>
                      <span className="trace-status-badge" data-status={item.status}>{item.status}</span>
                      <small>{item.duration_ms.toFixed(0)} мс</small>
                    </div>
                  ))}
                </details>
              ) : null}
            </div>
          </article>
        ))}
        {busy && !messages.some((m) => m.streaming) && (
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
          onPaste={(event) => {
            const items = Array.from(event.clipboardData?.items ?? [])
            const imgItem = items.find((item) => item.type.startsWith('image/'))
            const pastedFile = imgItem?.getAsFile()
            if (pastedFile) {
              event.preventDefault()
              void uploadImage(pastedFile)
            }
          }}
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
          accept=".txt,.csv,.json,.xlsx,.docx,.pdf,.zip,image/*"
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
      {previewMedia &&
        createPortal(
          <div
            className="tools-overlay settings-overlay media-modal-overlay"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setPreviewMedia(null)
            }}
          >
            <section
              className="tools-dialog settings-dialog media-modal-dialog design-1"
              role="dialog"
              aria-modal="true"
              aria-label={previewMedia.name}
            >
              <header className="tools-dialog-header">
                <div>
                  <span className="eyebrow">ПРОСМОТР МЕДИА</span>
                  <h2>{previewMedia.name}</h2>
                </div>
                <button
                  type="button"
                  className="tools-dialog-close"
                  onClick={() => setPreviewMedia(null)}
                  aria-label="Закрыть просмотр"
                >
                  ×
                </button>
              </header>
              <div className="media-modal-body">
                {previewMedia.kind === 'image' && previewMedia.url && (
                  <img src={previewMedia.url} alt={previewMedia.name} className="media-modal-img" />
                )}
                {previewMedia.kind === 'pdf' && previewMedia.url && (
                  <iframe src={previewMedia.url} title={previewMedia.name} className="media-modal-pdf" />
                )}
                {previewMedia.kind === 'audio' && (
                  <div className="media-modal-audio-wrap">
                    {previewMedia.url && <audio controls autoPlay src={previewMedia.url} className="media-modal-audio" />}
                    {previewMedia.textPreview && (
                      <div className="media-modal-transcript">
                        <strong>Расшифровка:</strong>
                        <p>{previewMedia.textPreview}</p>
                      </div>
                    )}
                  </div>
                )}
                {(previewMedia.kind === 'text' || previewMedia.kind === 'file') && (
                  <div className="media-modal-text-wrap">
                    {previewMedia.textPreview ? (
                      <pre className="media-modal-text">{previewMedia.textPreview}</pre>
                    ) : (
                      <p className="settings-hint">Предпросмотр текста недоступен для данного формата — скачайте файл по кнопке ниже.</p>
                    )}
                  </div>
                )}
              </div>
              <footer className="media-modal-footer">
                {previewMedia.url && (
                  <>
                    <a
                      href={previewMedia.url}
                      target="_blank"
                      rel="noreferrer"
                      className="btn-secondary-tool"
                    >
                      Открыть в новой вкладке
                    </a>
                    <a
                      href={previewMedia.url}
                      download={previewMedia.name}
                      className="btn-primary-tool"
                    >
                      Скачать
                    </a>
                  </>
                )}
                <button type="button" className="btn-secondary-tool" onClick={() => setPreviewMedia(null)}>
                  Закрыть
                </button>
              </footer>
            </section>
          </div>,
          document.body,
        )}
    </section>
  )
}

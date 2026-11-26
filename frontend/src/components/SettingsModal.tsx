import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ServerFileEntry, WellParams } from '../types/well'
import { loadAppSettings, resetAppSettings, saveAppSettings, type AppSettings } from '../utils/storage'

interface SettingsModalProps {
  open: boolean
  onClose: () => void
  onSettingsChanged?: () => void
  onApplyParams?: (partial: Partial<WellParams>) => void
  onResetSession?: () => void
}

const PROVIDER_PRESETS = [
  { label: 'OpenRouter (GPT-4o mini)', base_url: 'https://openrouter.ai/api/v1', model: 'openai/gpt-4o-mini' },
  { label: 'OpenRouter (Gemini 2.5 Flash)', base_url: 'https://openrouter.ai/api/v1', model: 'google/gemini-2.5-flash' },
  { label: 'DeepSeek API', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { label: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { label: 'Ollama (локально)', base_url: 'http://host.docker.internal:11434/v1', model: 'qwen2.5:14b' },
]

export function SettingsModal({
  open,
  onClose,
  onSettingsChanged,
  onApplyParams,
  onResetSession,
}: SettingsModalProps) {
  const [tab, setTab] = useState<'llm' | 'files'>('llm')
  const [form, setForm] = useState<AppSettings>(() => loadAppSettings())
  const [showKey, setShowKey] = useState(false)
  const [status, setStatus] = useState<{ kind: 'ok' | 'err' | 'info'; text: string } | null>(null)
  const [checking, setChecking] = useState(false)
  const [files, setFiles] = useState<ServerFileEntry[]>([])
  const [filesBusy, setFilesBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    setForm(loadAppSettings())
    setStatus(null)
    void loadFiles()
  }, [open])

  async function loadFiles() {
    setFilesBusy(true)
    try {
      const resp = await api.mcpFiles()
      setFiles(resp.files ?? [])
    } catch {
      setFiles([])
    } finally {
      setFilesBusy(false)
    }
  }

  if (!open) return null

  function emitUpdate() {
    window.dispatchEvent(new Event('wmb-settings-updated'))
    onSettingsChanged?.()
  }

  async function handleSave() {
    const saved = saveAppSettings({
      ...form,
      base_url: form.base_url.trim(),
      model: form.model.trim(),
      api_key: form.api_key.trim(),
    })
    setForm(saved)
    emitUpdate()
    try {
      const st = await api.chatStatus()
      setStatus({
        kind: st.available ? 'ok' : 'info',
        text: st.available
          ? `Настройки сохранены в cookie на 30 дней. ${st.message || 'Провайдер активен.'}`
          : 'Настройки сохранены в cookie (30 дн.), но LLM-ключ не задан — используется конфигурация сервера.',
      })
    } catch {
      setStatus({ kind: 'ok', text: 'Настройки сохранены в cookie браузера на 30 дней.' })
    }
  }

  async function handleCheck() {
    setChecking(true)
    setStatus(null)
    try {
      saveAppSettings(form)
      emitUpdate()
      const res = await api.chatStatus()
      if (res.available) {
        setStatus({ kind: 'ok', text: res.message || 'Конфигурация активна: провайдер готов к работе.' })
      } else {
        setStatus({ kind: 'err', text: res.message || 'API-ключ не настроен.' })
      }
    } catch (err) {
      setStatus({ kind: 'err', text: err instanceof Error ? err.message : 'Ошибка проверки настроек' })
    } finally {
      setChecking(false)
    }
  }

  function handleResetDefaults() {
    const def = resetAppSettings()
    setForm(def)
    emitUpdate()
    setStatus({ kind: 'info', text: 'Настройки сброшены на конфигурацию сервера (.env).' })
  }

  async function handleLoadServerFile(item: ServerFileEntry) {
    setFilesBusy(true)
    setStatus(null)
    try {
      const data = await api.mcpReadFile(item.id)
      if (data.parsed_params && onApplyParams) {
        onApplyParams(data.parsed_params)
        setStatus({ kind: 'ok', text: `Параметры из «${item.filename}» применены к модели.` })
      } else {
        setStatus({
          kind: 'info',
          text: `Файл «${item.filename}» прочитан (${data.text.length} симв.), но явные параметры не найдены.`,
        })
      }
    } catch (err) {
      setStatus({ kind: 'err', text: err instanceof Error ? err.message : 'Не удалось прочитать файл' })
    } finally {
      setFilesBusy(false)
    }
  }

  return (
    <div
      className="tools-overlay settings-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section className="tools-dialog settings-dialog design-1" role="dialog" aria-modal="true" aria-label="Настройки ИИ и хранилище">
        <header className="tools-dialog-header">
          <div>
            <span className="eyebrow">КОНФИГУРАЦИЯ</span>
            <h2>Настройки ИИ, API и хранилище</h2>
          </div>
          <button type="button" className="tools-dialog-close" onClick={onClose} aria-label="Закрыть настройки">
            ×
          </button>
        </header>

        <div className="settings-tabs-bar">
          <button
            type="button"
            className={`tab-btn ${tab === 'llm' ? 'active' : ''}`}
            onClick={() => setTab('llm')}
          >
            Модель и API (Cookie 30 дн.)
          </button>
          <button
            type="button"
            className={`tab-btn ${tab === 'files' ? 'active' : ''}`}
            onClick={() => setTab('files')}
          >
            Файлы на сервере ({files.length})
          </button>
        </div>

        <div className="settings-body">
          {tab === 'llm' ? (
            <div className="tool-pane">
              <p className="settings-hint">
                Переопределите OpenAI-совместимую нейросеть, режим Whisper Tiny и PDF OCR прямо в интерфейсе (без правки{' '}
                <code>.env</code>). Данные сохраняются в <strong>cookie браузера на 30 дней</strong>.
              </p>

              <div className="rag-quick-topics">
                {PROVIDER_PRESETS.map((preset) => {
                  const isSelected = form.base_url.trim() === preset.base_url && form.model.trim() === preset.model
                  return (
                    <button
                      key={preset.label}
                      type="button"
                      className={`quick-chip ${isSelected ? 'is-selected' : ''}`}
                      onClick={() =>
                        setForm((prev) => ({
                          ...prev,
                          base_url: preset.base_url,
                          model: preset.model,
                          api_key: preset.label.startsWith('Ollama') ? prev.api_key || 'ollama' : prev.api_key,
                        }))
                      }
                    >
                      {preset.label}
                    </button>
                  )
                })}
              </div>

              <label className="field-full">
                API Base URL
                <input
                  type="url"
                  value={form.base_url}
                  placeholder="Например: https://openrouter.ai/api/v1"
                  onChange={(e) => setForm((prev) => ({ ...prev, base_url: e.target.value }))}
                />
              </label>

              <label className="field-full">
                Модель (LLM / Vision)
                <input
                  type="text"
                  value={form.model}
                  placeholder="Например: openai/gpt-4o-mini, deepseek-chat"
                  onChange={(e) => setForm((prev) => ({ ...prev, model: e.target.value }))}
                />
              </label>

              <label className="field-full">
                API Key
                <div className="settings-key-row">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={form.api_key}
                    placeholder="sk-... (оставьте пустым для использования ключа .env)"
                    onChange={(e) => setForm((prev) => ({ ...prev, api_key: e.target.value }))}
                  />
                  <button
                    type="button"
                    className="btn-secondary-tool"
                    onClick={() => setShowKey((prev) => !prev)}
                  >
                    {showKey ? 'Скрыть' : 'Показать'}
                  </button>
                </div>
              </label>

              <label className="field-full">
                Распознавание речи
                <select
                  value={form.audio_mode}
                  onChange={(e) =>
                    setForm((prev) => ({ ...prev, audio_mode: e.target.value as AppSettings['audio_mode'] }))
                  }
                >
                  <option value="auto">Авто (Whisper Tiny оффлайн → Multimodal LLM)</option>
                  <option value="whisper">Только оффлайн Whisper Tiny</option>
                  <option value="multimodal">Через мультимодальную LLM</option>
                </select>
              </label>

              <div className="tool-actions">
                <button type="button" className="btn-primary-tool" onClick={() => void handleSave()}>
                  Сохранить в Cookie (30 дней)
                </button>
                <button type="button" className="btn-secondary-tool" disabled={checking} onClick={() => void handleCheck()}>
                  {checking ? 'Проверка...' : 'Проверить подключение'}
                </button>
                <button type="button" className="btn-secondary-tool" onClick={handleResetDefaults}>
                  Сбросить к серверу (.env)
                </button>
              </div>

              {onResetSession && (
                <div className="settings-danger-zone">
                  <span>Текущие параметры скважины и история чата также хранятся в cookie / браузере (30 дней).</span>
                  <button
                    type="button"
                    className="btn-secondary-tool"
                    onClick={() => {
                      onResetSession()
                      setStatus({ kind: 'info', text: 'Параметры и история чата сброшены к эталону well_01.' })
                    }}
                  >
                    Очистить сессию и параметры
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="tool-pane">
              <div className="settings-files-head">
                <span>Архив загруженных PDF/документов и <code>samples/</code> на сервере (доступен ИИ через MCP):</span>
                <button type="button" className="btn-secondary-tool" disabled={filesBusy} onClick={() => void loadFiles()}>
                  {filesBusy ? 'Обновление...' : 'Обновить'}
                </button>
              </div>

              {files.length === 0 ? (
                <p className="settings-hint">На сервере пока нет загруженных документов.</p>
              ) : (
                <div className="scanned-files-list">
                  {files.map((item) => (
                    <div key={item.id} className="scanned-file-item">
                      <div>
                        <strong>{item.filename}</strong>
                        <div className="server-file-meta">
                          <span className="file-scope-badge">{item.scope}</span>
                          <span>{(item.size_bytes / 1024).toFixed(1)} КБ</span>
                          {item.ocr_method && <span>· {item.ocr_method}</span>}
                        </div>
                      </div>
                      <button
                        type="button"
                        className="btn-apply-param"
                        disabled={filesBusy}
                        onClick={() => void handleLoadServerFile(item)}
                      >
                        Применить в модель
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {status && (
            <div
              className={
                status.kind === 'ok'
                  ? 'inline-success'
                  : status.kind === 'err'
                    ? 'inline-error'
                    : 'inline-info'
              }
              role="status"
            >
              {status.text}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

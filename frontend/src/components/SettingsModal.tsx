import { useEffect, useState } from 'react'
import { api, LLM_SETTINGS_COOKIE_KEY } from '../api/client'
import type { LLMSettingsConfig, ServerFileItem, WellParams } from '../types/well'
import { clearPersistedJson, loadPersistedJson, savePersistedJson } from '../utils/cookies'

interface SettingsModalProps {
  open: boolean
  onClose: () => void
  onSettingsChanged: (settings: LLMSettingsConfig | null) => void
  onApplyParams?: (partial: Partial<WellParams>) => void
  onResetSession?: () => void
}

const EMPTY_CONFIG: LLMSettingsConfig = { base_url: '', model: '', api_key: '' }

const PROVIDER_PRESETS = [
  { label: 'DeepSeek', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { label: 'OpenAI', base_url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1', model: 'qwen/qwen-2.5-72b-instruct' },
  { label: 'Gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/', model: 'gemini-2.5-flash' },
]

export function SettingsModal({
  open,
  onClose,
  onSettingsChanged,
  onApplyParams,
  onResetSession,
}: SettingsModalProps) {
  const [tab, setTab] = useState<'llm' | 'files'>('llm')
  const [form, setForm] = useState<LLMSettingsConfig>(EMPTY_CONFIG)
  const [showKey, setShowKey] = useState(false)
  const [status, setStatus] = useState<{ kind: 'ok' | 'err' | 'info'; text: string } | null>(null)
  const [checking, setChecking] = useState(false)
  const [files, setFiles] = useState<ServerFileItem[]>([])
  const [filesBusy, setFilesBusy] = useState(false)

  useEffect(() => {
    if (!open) return
    const saved = loadPersistedJson<LLMSettingsConfig>(LLM_SETTINGS_COOKIE_KEY)
    setForm(saved ?? EMPTY_CONFIG)
    setStatus(null)
    void loadFiles()
  }, [open])

  async function loadFiles() {
    setFilesBusy(true)
    try {
      const resp = await api.serverFiles()
      setFiles(resp.files ?? [])
    } catch {
      setFiles([])
    } finally {
      setFilesBusy(false)
    }
  }

  if (!open) return null

  async function handleSave() {
    const cleaned: LLMSettingsConfig = {
      base_url: form.base_url.trim(),
      model: form.model.trim(),
      api_key: form.api_key.trim(),
    }
    if (!cleaned.base_url && !cleaned.model && !cleaned.api_key) {
      clearPersistedJson(LLM_SETTINGS_COOKIE_KEY)
      onSettingsChanged(null)
      setStatus({ kind: 'info', text: 'Пользовательские настройки очищены — используются настройки сервера (.env).' })
      return
    }
    savePersistedJson(LLM_SETTINGS_COOKIE_KEY, cleaned, 30)
    onSettingsChanged(cleaned)
    setStatus({ kind: 'ok', text: 'Настройки сохранены в cookie браузера на 30 дней.' })
  }

  async function handleCheck() {
    setChecking(true)
    setStatus(null)
    try {
      const res = await api.chatStatus(form)
      if (res.available) {
        setStatus({ kind: 'ok', text: 'Конфигурация активна: провайдер готов к работе.' })
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
    clearPersistedJson(LLM_SETTINGS_COOKIE_KEY)
    setForm(EMPTY_CONFIG)
    onSettingsChanged(null)
    setStatus({ kind: 'info', text: 'Сброшено на конфигурацию сервера (.env).' })
  }

  async function handleLoadServerFile(item: ServerFileItem) {
    setFilesBusy(true)
    setStatus(null)
    try {
      const data = await api.readServerFile(item.folder, item.name)
      if (data.parsed_params && onApplyParams) {
        onApplyParams(data.parsed_params)
        setStatus({ kind: 'ok', text: `Параметры из «${item.name}» применены к модели.` })
      } else {
        setStatus({ kind: 'info', text: `Файл «${item.name}» прочитан (${data.text.length} симв.), но явные параметры не найдены.` })
      }
    } catch (err) {
      setStatus({ kind: 'err', text: err instanceof Error ? err.message : 'Не удалось прочитать файл' })
    } finally {
      setFilesBusy(false)
    }
  }

  return (
    <div
      className="tools-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <section className="tools-dialog settings-dialog design-1" role="dialog" aria-modal="true" aria-label="Настройки и файлы">
        <header className="tools-dialog-header">
          <div>
            <span className="eyebrow">КОНФИГУРАЦИЯ</span>
            <h2>Настройки API и хранилище</h2>
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
                Переопределите OpenAI-совместимую нейросеть прямо в интерфейсе (без правки <code>.env</code>).
                Данные сохраняются в <strong>cookie браузера на 30 дней</strong>. Пустые поля берут значения из настроек сервера.
              </p>

              <div className="rag-quick-topics">
                {PROVIDER_PRESETS.map((preset) => (
                  <button
                    key={preset.label}
                    type="button"
                    className="quick-chip"
                    onClick={() =>
                      setForm((prev) => ({
                        ...prev,
                        base_url: preset.base_url,
                        model: preset.model,
                      }))
                    }
                  >
                    {preset.label} ({preset.model})
                  </button>
                ))}
              </div>

              <label className="field-full">
                API Base URL
                <input
                  type="url"
                  value={form.base_url}
                  placeholder="Например: https://api.deepseek.com/v1"
                  onChange={(e) => setForm((prev) => ({ ...prev, base_url: e.target.value }))}
                />
              </label>

              <label className="field-full">
                Модель (LLM Model)
                <input
                  type="text"
                  value={form.model}
                  placeholder="Например: deepseek-chat, gpt-4o, qwen-plus"
                  onChange={(e) => setForm((prev) => ({ ...prev, model: e.target.value }))}
                />
              </label>

              <label className="field-full">
                API Key
                <div className="settings-key-row">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={form.api_key}
                    placeholder="sk-... (оставьте пустым для использования ключа сервера)"
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

              <div className="tool-actions">
                <button type="button" className="btn-primary-tool" onClick={handleSave}>
                  Сохранить в Cookie (30 дней)
                </button>
                <button type="button" className="btn-secondary-tool" disabled={checking} onClick={handleCheck}>
                  {checking ? 'Проверка...' : 'Проверить подключение'}
                </button>
                <button type="button" className="btn-secondary-tool" onClick={handleResetDefaults}>
                  Сбросить к серверу (.env)
                </button>
              </div>

              {onResetSession && (
                <div className="settings-danger-zone">
                  <span>Текущие параметры скважины и история чата тоже сохраняются на 30 дней.</span>
                  <button
                    type="button"
                    className="btn-secondary-tool"
                    onClick={() => {
                      onResetSession()
                      setStatus({ kind: 'info', text: 'Сохранённые параметры формы и история чата сброшены к эталону.' })
                    }}
                  >
                    Сбросить кэш формы и чата
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="tool-pane">
              <div className="settings-files-head">
                <p style={{ margin: 0 }}>
                  Загруженные файлы (PDF, таблицы, сканы) сохраняются на сервере — ассистент и MCP-сервер могут обращаться к ним повторно.
                </p>
                <button type="button" className="btn-secondary-tool" disabled={filesBusy} onClick={() => void loadFiles()}>
                  Обновить
                </button>
              </div>

              {files.length === 0 ? (
                <p className="settings-hint">На сервере пока нет сохранённых загрузок.</p>
              ) : (
                <div className="scanned-files-list">
                  {files.map((item) => (
                    <div key={`${item.folder}:${item.name}`} className="scanned-file-item">
                      <div style={{ minWidth: 0 }}>
                        <strong>{item.name}</strong>{' '}
                        <span className="status-pill muted">{item.folder}</span>{' '}
                        <small style={{ color: 'var(--muted)' }}>
                          {(item.size_bytes / 1024).toFixed(1)} КБ
                        </small>
                      </div>
                      {item.has_parsed_params && onApplyParams && (
                        <button
                          type="button"
                          className="btn-load-file"
                          disabled={filesBusy}
                          onClick={() => void handleLoadServerFile(item)}
                        >
                          Загрузить в модель
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {status && (
            <div
              className={status.kind === 'err' ? 'inline-error' : status.kind === 'ok' ? 'inline-success' : 'inline-info'}
              style={{ marginTop: 14 }}
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

import { useEffect, useState } from 'react'
import { loadAppSettings, saveAppSettings, type PdfOcrMode } from '../utils/storage'

export function PdfOcrModeSelect() {
  const [mode, setMode] = useState<PdfOcrMode>(() => loadAppSettings().pdf_ocr_mode)

  useEffect(() => {
    const sync = () => setMode(loadAppSettings().pdf_ocr_mode)
    window.addEventListener('wmb-settings-updated', sync)
    return () => window.removeEventListener('wmb-settings-updated', sync)
  }, [])

  function handleChange(nextMode: PdfOcrMode) {
    setMode(nextMode)
    const current = loadAppSettings()
    saveAppSettings({ ...current, pdf_ocr_mode: nextMode })
    window.dispatchEvent(new Event('wmb-settings-updated'))
  }

  return (
    <label className="field-full pdf-ocr-field">
      <span>Режим чтения PDF-сканов</span>
      <select value={mode} onChange={(e) => handleChange(e.target.value as PdfOcrMode)}>
        <option value="auto">Авто (PyMuPDF + Tesseract → Vision LLM)</option>
        <option value="tesseract">Только оффлайн Tesseract OCR (rus+eng)</option>
        <option value="vision">Мультимодальная Vision LLM + Tesseract</option>
      </select>
    </label>
  )
}

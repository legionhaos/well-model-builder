#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE_PATH="/home/scoof/Downloads/well-model-builder-submission.zip"

echo "=== 1. Получение последних изменений из Git ==="
cd "$REPO_DIR"
git pull origin main || true

echo "=== 2. Проверка сборки фронтенда ==="
cd "$REPO_DIR/frontend"
npm run build

echo "=== 3. Проверка тестов бэкенда ==="
cd "$REPO_DIR"
/home/scoof/.local/bin/uv run --with fastapi --with uvicorn --with pydantic --with pydantic-settings --with numpy --with scipy --with pytest --with pytest-asyncio --with httpx --with openpyxl --with python-multipart python3 -m pytest tests/ backend/tests/ -q

echo "=== 4. Сборка чистого архива решения ==="
rm -f "$ARCHIVE_PATH"
git archive --format=zip --prefix=well-model-builder/ -o "$ARCHIVE_PATH" HEAD

echo "=========================================================="
echo "✅ Архив успешно создан: $ARCHIVE_PATH"
echo "Размер: $(du -h "$ARCHIVE_PATH" | cut -f1)"
echo "В архиве нет .env, node_modules и мусора. Готов к сдаче!"
echo "=========================================================="

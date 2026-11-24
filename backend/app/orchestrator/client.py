import time
import asyncio
from typing import Dict, Any, Tuple, Optional
import httpx
from fastapi import HTTPException, status

from app.config import settings


class CalculationClient:
    """
    Асинхронный клиент для взаимодействия с микросервисами IPR, VLP и Nodal.
    """

    def __init__(self):
        self.ipr_url = settings.ipr_service_url.rstrip("/")
        self.vlp_url = settings.vlp_service_url.rstrip("/")
        self.nodal_url = settings.nodal_service_url.rstrip("/")

    async def check_dependencies(self) -> Dict[str, Any]:
        """
        Проверка доступности всех трех расчетных микросервисов.
        """
        results = {}
        async with httpx.AsyncClient(timeout=3.0) as client:
            for name, url, path in [
                ("ipr", self.ipr_url, "/ipr/health"),
                ("vlp", self.vlp_url, "/vlp/health"),
                ("nodal", self.nodal_url, "/nodal/health")
            ]:
                try:
                    resp = await client.get(f"{url}{path}")
                    results[name] = resp.status_code == 200
                except Exception:
                    results[name] = False
        return results

    async def run_full_calculation(
        self,
        ipr_payload: Dict[str, Any],
        vlp_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Параллельный расчет IPR и VLP, затем поиск точки пересечения через Nodal.
        """
        start_time = time.perf_counter()

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Параллельный вызов IPR и VLP через asyncio.gather
            task_ipr = client.post(f"{self.ipr_url}/ipr/calc", json=ipr_payload)
            task_vlp = client.post(f"{self.vlp_url}/vlp/calc", json=vlp_payload)

            resp_ipr, resp_vlp = await asyncio.gather(task_ipr, task_vlp, return_exceptions=True)

            # Проверка ошибок IPR
            if isinstance(resp_ipr, Exception):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Не удалось подключиться к сервису IPR ({self.ipr_url}): {str(resp_ipr)}"
                )
            if resp_ipr.status_code != 200:
                err_data = resp_ipr.json() if resp_ipr.headers.get("content-type", "").startswith("application/json") else {}
                desc = err_data.get("description") or err_data.get("detail") or resp_ipr.text
                raise HTTPException(
                    status_code=resp_ipr.status_code,
                    detail=f"Ошибка в сервисе IPR: {desc}"
                )

            # Проверка ошибок VLP
            if isinstance(resp_vlp, Exception):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Не удалось подключиться к сервису VLP ({self.vlp_url}): {str(resp_vlp)}"
                )
            if resp_vlp.status_code != 200:
                err_data = resp_vlp.json() if resp_vlp.headers.get("content-type", "").startswith("application/json") else {}
                desc = err_data.get("description") or err_data.get("detail") or resp_vlp.text
                raise HTTPException(
                    status_code=resp_vlp.status_code,
                    detail=f"Ошибка в сервисе VLP: {desc}"
                )

            ipr_data = resp_ipr.json()
            vlp_data = resp_vlp.json()

            # 2. Вызов сервиса Nodal
            nodal_payload = {
                "ipr": ipr_data,
                "vlp": vlp_data
            }

            try:
                resp_nodal = await client.post(f"{self.nodal_url}/nodal/calc", json=nodal_payload)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Не удалось подключиться к сервису Nodal ({self.nodal_url}): {str(e)}"
                )

            calc_time_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

            # Если Nodal вернул 422 (кривые не пересекаются) - не падаем, отдаем кривые с operating_point: null!
            if resp_nodal.status_code == 422:
                err_data = resp_nodal.json() if resp_nodal.headers.get("content-type", "").startswith("application/json") else {}
                desc = err_data.get("description") or err_data.get("detail") or "Точка пересечения не найдена"
                return {
                    "status": "no_intersection",
                    "ipr": ipr_data,
                    "vlp": vlp_data,
                    "operating_point": None,
                    "meta": {
                        "calc_time_ms": calc_time_ms,
                        "message": f"Рабочая точка не найдена: {desc}"
                    }
                }

            if resp_nodal.status_code != 200:
                err_data = resp_nodal.json() if resp_nodal.headers.get("content-type", "").startswith("application/json") else {}
                desc = err_data.get("description") or err_data.get("detail") or resp_nodal.text
                raise HTTPException(
                    status_code=resp_nodal.status_code,
                    detail=f"Ошибка в сервисе Nodal: {desc}"
                )

            nodal_points = resp_nodal.json()
            operating_point = nodal_points[0] if nodal_points else None

            return {
                "status": "success",
                "ipr": ipr_data,
                "vlp": vlp_data,
                "operating_point": operating_point,
                "meta": {
                    "calc_time_ms": calc_time_ms,
                    "message": "Расчет узлового анализа успешно выполнен"
                }
            }


calc_client = CalculationClient()

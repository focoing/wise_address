from collections import Counter
from typing import Any

import httpx
from fastapi import HTTPException

from app.config import Settings
from app.models import PoiItem, PoiSummary


AMAP_BASE = "https://restapi.amap.com/v3"


class AmapClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def reverse_geocode(self, lng: float, lat: float) -> dict[str, Any]:
        if not self.settings.amap_key:
            raise HTTPException(status_code=500, detail="AMAP_KEY is not configured")
        params = {
            "key": self.settings.amap_key,
            "location": f"{lng},{lat}",
            "extensions": "base",
            "radius": 1000,
            "output": "JSON",
        }
        data = await self._get("/geocode/regeo", params)
        regeocode = data.get("regeocode") or {}
        component = regeocode.get("addressComponent") or {}
        return {
            "address": regeocode.get("formatted_address", ""),
            "province": component.get("province", ""),
            "city": component.get("city", ""),
            "district": component.get("district", ""),
            "township": component.get("township", ""),
        }

    async def nearby_pois(
        self,
        lng: float,
        lat: float,
        radius: int,
        keywords: str | None = None,
        types: str | None = None,
        pages: int = 1,
    ) -> PoiSummary:
        if not self.settings.amap_key:
            raise HTTPException(status_code=500, detail="AMAP_KEY is not configured")
        collected: list[PoiItem] = []
        seen_ids: set[str] = set()
        for page in range(1, max(1, pages) + 1):
            params = {
                "key": self.settings.amap_key,
                "location": f"{lng},{lat}",
                "radius": radius,
                "offset": 25,
                "page": page,
                "extensions": "base",
                "output": "JSON",
            }
            if keywords:
                params["keywords"] = keywords
            if types:
                params["types"] = types
            data = await self._get("/place/around", params)
            raw_pois = data.get("pois") or []
            if not raw_pois:
                break
            for item in raw_pois:
                poi = PoiItem(
                    id=str(item.get("id", "")),
                    name=str(item.get("name", "")),
                    type=str(item.get("type", "")),
                    address=str(item.get("address", "")),
                    distance=_safe_int(item.get("distance")),
                    location=str(item.get("location", "")),
                )
                if poi.id:
                    if poi.id in seen_ids:
                        continue
                    seen_ids.add(poi.id)
                collected.append(poi)
            if len(raw_pois) < 25:
                break
        categories = Counter(_category_name(poi.type) for poi in collected)
        return PoiSummary(
            total=len(collected),
            byCategory=dict(categories),
            topPois=collected[:10],
            radius=radius,
            estimated=False,
        )

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=8) as client:
            try:
                response = await client.get(f"{AMAP_BASE}{path}", params=params)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=f"高德服务请求失败: {exc}") from exc
        data = response.json()
        if data.get("status") != "1":
            message = data.get("info") or "高德服务返回异常"
            raise HTTPException(status_code=502, detail=message)
        return data


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _category_name(type_text: str) -> str:
    if not type_text:
        return "其他"
    first = type_text.split(";")[0]
    if "餐饮" in first:
        return "餐饮"
    if "购物" in first:
        return "零售"
    if "交通" in first or "地铁" in first or "公交" in first:
        return "交通"
    if "商务" in first or "写字楼" in first:
        return "办公"
    if "住宅" in first or "生活" in first:
        return "社区生活"
    if "科教" in first or "学校" in first:
        return "教育"
    if "医疗" in first:
        return "医疗"
    return first[:12]


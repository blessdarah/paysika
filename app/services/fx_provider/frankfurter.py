import logging
from decimal import Decimal

import requests

from app.services.fx_provider import FxProvider, register_provider

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.frankfurter.dev/v2"


@register_provider("frankfurter")
class FrankfurterProvider(FxProvider):
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url

    def fetch_rate(self, source: str, target: str) -> Decimal | None:
        try:
            resp = requests.get(
                f"{self.base_url}/rate/{source}/{target}",
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            rate = Decimal(str(data["rate"]))
            logger.info("FX rate fetched from API: 1 %s = %s %s", source, rate, target)
            return rate
        except Exception:
            logger.warning(
                "FX API unavailable for %s->%s", source, target, exc_info=True
            )
            return None

"""数据来源与采集器的显式注册表。"""

from collectors.base import BaseCollector, CollectorError
from collectors.honor_club import HonorClubCollector
from collectors.jd import JDCollector


def get_collector(source_code: str) -> BaseCollector:
    if source_code == "HONOR_CLUB":
        return HonorClubCollector()
    if source_code == "JD":
        return JDCollector()
    raise CollectorError(f"Unsupported collector source: {source_code}", code="UNSUPPORTED_SOURCE")

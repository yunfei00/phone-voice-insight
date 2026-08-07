import pytest
from collectors.base import BaseCollector, CollectorTarget
from collectors.jd import JDCollector


@pytest.mark.parametrize("collector", [JDCollector()])
def test_jd_collector_rejects_unconfigured_target(collector: BaseCollector) -> None:
    target = CollectorTarget(source_code="JD", product_code="HONOR_POWER2", target_url="")
    result = collector.validate_target(target)
    assert not result.is_valid
    assert result.errors

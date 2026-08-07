import pytest
from collectors.base import BaseCollector, CollectorError, CollectorTarget
from collectors.jd import JDCollector


@pytest.mark.parametrize("collector", [JDCollector()])
def test_unimplemented_source_collectors_fail_explicitly(collector: BaseCollector) -> None:
    target = CollectorTarget(source_code="TEST", product_code="HONOR_POWER2", target_url="")

    with pytest.raises(CollectorError, match="not implemented") as exc_info:
        collector.validate_target(target)

    assert exc_info.value.code == "NOT_IMPLEMENTED"

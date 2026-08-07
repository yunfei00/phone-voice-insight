"""京东规格文本到通用版本属性的保守转换。"""

from __future__ import annotations

import re

_STORAGE_PATTERN = re.compile(r"(?<!\d)(\d+)\s*(GB|TB)", re.IGNORECASE)


def extract_variant_attributes(*, product_size: str, product_color: str) -> dict[str, str]:
    values = [f"{number.upper()}{unit.upper()}" for number, unit in _STORAGE_PATTERN.findall(product_size)]
    memory = ""
    storage = ""
    if values:
        memory = values[0]
    if len(values) >= 2:
        storage = values[1]
    elif "+" not in product_size and values:
        memory = ""
        storage = values[0]
    attributes = {
        "memory": memory,
        "storage": storage,
        "color": product_color.strip(),
    }
    return {key: value for key, value in attributes.items() if value}

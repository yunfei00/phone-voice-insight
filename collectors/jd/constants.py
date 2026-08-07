"""京东 PoC 的安全边界与已验证配置。"""

from typing import Final

PRODUCT_HOST: Final = "item.jd.com"
PRODUCT_PATH_TEMPLATE: Final = "/{product_id}.html"
PRODUCT_ID: Final = "100310496358"
EXPECTED_PRODUCT_MARKERS: Final = ("Power2",)
EXPECTED_BRAND_MARKERS: Final = ("HONOR", "荣耀")
EXPECTED_SHOP_NAME: Final = "荣耀京东自营旗舰店"

FIXED_USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
MIN_REQUEST_INTERVAL_SECONDS: Final = 4.0
REQUEST_TIMEOUT_SECONDS: Final = 15.0
MAX_PAGES: Final = 3
MAX_PAGE_SIZE: Final = 10
MAX_REVIEWS: Final = 30

# 2026-08-08 的正常浏览器访问被重定向到京东登录页。当前评论 host/path、参数和字段映射
# 均未获得真实响应验证, 因此必须保持为空; 禁止用历史接口补位。
VERIFIED_COMMENT_ENDPOINT: Final[str | None] = None
VERIFIED_COMMENT_HOSTS: Final[frozenset[str]] = frozenset()
VERIFIED_COMMENT_FIELD_MAP: Final[dict[str, str]] = {}

BLOCK_STATUS_CODES: Final = frozenset({403, 429})
BLOCK_MARKERS: Final = (
    "captcha",
    "passport.jd.com",
    "安全验证",
    "访问验证",
    "访问受限",
    "滑块",
    "验证码",
    "欢迎登录",
)

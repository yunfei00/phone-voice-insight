"""Deterministic product-experience signal and content-purpose detection."""

# ruff: noqa: RUF001

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.reviews.models import ContentPurpose
from apps.reviews.services.text_normalizer import normalize_text

ASPECT_SIGNAL_TERMS: dict[str, tuple[str, ...]] = {
    "BATTERY": ("续航", "掉电", "耗电", "电量", "电池", "待机", "一天一充", "两天一充", "亮屏", "省电"),
    "CHARGING": ("充电", "快充", "充不进", "充电器", "反向充电"),
    "HEATING": ("发热", "过热", "烫", "温度", "很热", "太热", "偏热", "热得"),
    "SIGNAL": ("信号", "4g", "5g", "网络", "断流", "wifi", "wi-fi", "蓝牙", "定位", "导航"),
    "PERFORMANCE": ("帧率", "游戏性能", "性能", "跑分", "应用启动", "多任务"),
    "SYSTEM_FLUENCY": ("流畅", "卡顿", "响应慢", "动画", "滑动卡", "很卡", "太卡", "卡死"),
    "SYSTEM_BUG": (
        "bug",
        "闪退",
        "死机",
        "重启",
        "异常",
        "功能没了",
        "功能消失",
        "功能缺失",
        "升级问题",
        "更新问题",
    ),
    "DISPLAY": ("屏幕", "亮度", "显示", "护眼", "触控"),
    "CAMERA": ("拍照", "摄像", "录像", "夜景", "长焦", "人像模式", "对焦", "成像", "拍出来"),
    "WEIGHT_AND_FEEL": ("重量", "手感", "握持", "太重", "很重", "偏重", "厚重", "机身厚", "机身薄", "轻薄"),
    "BUILD_QUALITY": ("做工", "外观", "机身", "按键", "缝隙", "后盖", "材质"),
    "AUDIO_AND_CALL": ("扬声器", "音质", "通话", "免提", "麦克风", "听筒"),
    "DURABILITY": ("抗摔", "防水", "耐用", "摔坏", "摔了", "耐磨"),
    "VALUE_FOR_MONEY": ("价格", "性价比", "太贵", "很贵", "便宜", "优惠"),
    "AFTER_SALES": ("售后", "维修", "客服", "换机", "退换", "质保"),
}

_CONTEXT_INHERITANCE = frozenset({"我也是", "确实", "同感", "我的也这样", "我的也是", "一样", "+1"})
_CONTEXT_INHERITANCE_PATTERN = re.compile(
    r"^(我也是|确实|同感|我的也这样|我的也是|一样|\+1)[，,。.!！].{0,24}$|"
    r"^我也(遇到|有|这样)|^(我都|都).*(试过|设置过)|^(真的|确实)(强悍|很好|不错|不行|很差)$|"
    r"^(不行|还是不行).*(停|断|卡|没)|^(看看|宣传).*(别当真|不可信)|"
    r"^而且我的.*(没有|没).*(升级|更新)|^(关|关闭)不了$"
)
_EDGE_PUNCTUATION = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)
_QUESTION = re.compile(r"[?？]|为什么|为啥|怎么|怎样|如何|是否|能不能|可不可以|支持.+吗|求问")
_PHOTO_SHARE = re.compile(
    r"摄影作品|照片分享|图片分享|分享.{0,4}(照片|图片|作品)|相册里的.*作品|"
    r"ai生成.{0,4}(图|作品)|作品.{0,8}ai生成|晒图|美图|随手拍"
)
_RESOURCE_SHARE = re.compile(r"壁纸|主题分享|资源分享|资源包|下载链接|安装包|求链接|去下载|下载试试")
_TUTORIAL = re.compile(r"教程|操作步骤|使用方法|教你|攻略|怎么设置")
_SOCIAL_MARKERS = (
    "支持",
    "感谢分享",
    "谢谢分享",
    "感谢大佬",
    "顶",
    "围观",
    "路过",
    "沙发",
    "哈哈",
    "666",
    "漂亮",
    "美女",
    "学习了",
    "收藏了",
    "不错不错",
)
_ACCESSORY_FOCUS = re.compile(r"荣耀亲选.{0,20}耳机|ai通话耳机|充电舱|通话手表")


@dataclass(frozen=True)
class ExperienceSignal:
    has_signal: bool
    candidate_aspects: tuple[str, ...]
    matched_terms: tuple[str, ...]
    context_required: bool = False


def _canonical_short_reply(value: str) -> str:
    compact = "".join(normalize_text(value).split()).casefold()
    if compact == "+1":
        return compact
    return _EDGE_PUNCTUATION.sub("", compact)


def is_context_inheritance_reply(value: str | None) -> bool:
    canonical = _canonical_short_reply(value or "")
    return canonical in _CONTEXT_INHERITANCE or bool(_CONTEXT_INHERITANCE_PATTERN.search(canonical))


def _direct_signal(value: str | None) -> ExperienceSignal:
    text = normalize_text(value).casefold()
    if is_non_phone_accessory_content(text):
        return ExperienceSignal(False, (), ())
    aspects: list[str] = []
    matched: list[str] = []
    for aspect, terms in ASPECT_SIGNAL_TERMS.items():
        hits = [term for term in terms if term.casefold() in text]
        if hits:
            aspects.append(aspect)
            matched.extend(f"{aspect}:{term}" for term in hits)
    if "掉帧" in text:
        frame_aspect = "PERFORMANCE" if any(marker in text for marker in ("游戏", "帧率")) else "SYSTEM_FLUENCY"
        if frame_aspect not in aspects:
            aspects.append(frame_aspect)
        matched.append(f"{frame_aspect}:掉帧")
    if re.search(r"(桌面|系统|滑动|动画).{0,8}卡|卡一下", text) and "SYSTEM_FLUENCY" not in aspects:
        aspects.append("SYSTEM_FLUENCY")
        matched.append("SYSTEM_FLUENCY:交互卡顿")
    if re.search(r"(拍的|拍出来的?)照片.{0,6}(清晰|模糊|好|差)|照片拍", text) and "CAMERA" not in aspects:
        aspects.append("CAMERA")
        matched.append("CAMERA:照片表现")
    if re.search(r"相机.{0,8}(好|差|模糊|清晰|打不开|无法|异常|拍|卡|慢)", text) and "CAMERA" not in aspects:
        aspects.append("CAMERA")
        matched.append("CAMERA:相机表现")
    if (
        re.search(
            r"(声音|音量)\s*(太|很|偏|过于)?(小|大|差|好|低|高)|"
            r"(声音|音量)(异常|断断续续)|没有声音|没声音",
            text,
        )
        and "AUDIO_AND_CALL" not in aspects
    ):
        aspects.append("AUDIO_AND_CALL")
        matched.append("AUDIO_AND_CALL:声音表现")
    return ExperienceSignal(bool(aspects), tuple(aspects), tuple(matched))


def is_non_phone_accessory_content(value: str | None) -> bool:
    text = normalize_text(value).casefold()
    if "ai通话耳机" in text or ("荣耀亲选" in text and text.count("耳机") >= 1):
        return True
    return bool(_ACCESSORY_FOCUS.search(text) and "手机" not in text and "power2" not in text)


def detect_product_experience_signal(
    current_text: str | None,
    *,
    parent_text: str | None = None,
    allow_context_inheritance: bool = False,
) -> ExperienceSignal:
    direct = _direct_signal(current_text)
    if direct.has_signal:
        return direct
    if allow_context_inheritance and is_context_inheritance_reply(current_text):
        inherited = _direct_signal(parent_text)
        if inherited.has_signal:
            return ExperienceSignal(
                True,
                inherited.candidate_aspects,
                tuple(f"CONTEXT:{term}" for term in inherited.matched_terms),
                context_required=True,
            )
    return direct


def classify_content_purpose(
    value: str | None,
    *,
    has_experience_signal: bool,
    promotional: bool = False,
) -> str:
    text = normalize_text(value).casefold()
    compact = "".join(text.split())
    if promotional:
        return ContentPurpose.PROMOTIONAL
    if not has_experience_signal and _PHOTO_SHARE.search(text):
        return ContentPurpose.PHOTO_SHARE
    if not has_experience_signal and _RESOURCE_SHARE.search(text):
        return ContentPurpose.RESOURCE_SHARE
    if not has_experience_signal and _TUTORIAL.search(text):
        return ContentPurpose.TUTORIAL
    if _QUESTION.search(text) or compact in {"在哪里", "求解答", "这啥意思", "什么意思"}:
        return ContentPurpose.QUESTION
    if not has_experience_signal and any(marker in compact for marker in _SOCIAL_MARKERS):
        return ContentPurpose.SOCIAL_INTERACTION
    if has_experience_signal:
        return ContentPurpose.PRODUCT_EXPERIENCE
    return ContentPurpose.OTHER

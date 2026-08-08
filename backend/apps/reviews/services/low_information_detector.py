"""Deterministic low-information detection with a deliberately small allowlist."""

# ruff: noqa: RUF001

from __future__ import annotations

import re

from apps.reviews.services.text_normalizer import normalize_text

_LOW_INFORMATION = frozenset(
    {
        "支持",
        "支持下",
        "强",
        "顶",
        "嗯",
        "哦",
        "牛",
        "哈哈",
        "哈哈哈",
        "呵呵",
        "路过",
        "不错",
        "可以",
        "厉害",
        "漂亮",
        "推荐",
        "加油",
        "是的",
        "正常",
        "够呛",
        "好",
        "好吧v",
        "好看",
        "好吃",
        "好拍",
        "好可爱",
        "好极了",
        "好帖子",
        "棒",
        "美",
        "美丽",
        "美拍",
        "美拍照",
        "美美哒",
        "漂亮的",
        "拍的好",
        "奈斯",
        "期待",
        "温暖",
        "农",
        "哇塞",
        "恭喜",
        "波哥",
        "中指",
        "表达",
        "美赞",
        "翠色",
        "雨润",
        "水冷杉",
        "大雪人",
        "您好",
        "100分",
        "求解答",
        "看一下",
        "解决吧",
        "多少钱",
        "还没有",
        "已更新",
        "沙发支持",
        "支持一下",
        "点赞支持",
        "鼓掌+1",
        "坐等发布",
        "这个允许",
        "不错呀",
        "不错不错",
        "厉害了",
        "这么强吗",
        "也是很牛",
        "真的强悍",
        "绿色食品",
        "绿色无污染",
        "关键是放心",
        "是的有了",
        "我下了",
        "官方回应了",
        "让心静下来",
        "熊猫玩闹",
        "茹茹回到家",
        "记得回电话",
        "啥也不是",
        "荣耀power2上手体验",
        "自家地里东西吃着放心",
        "静心读书，难得",
        "张牙舞爪的家伙",
        "今年受全球厄尔尼诺气候现象的影响,整个上半年天气都变幻无常",
        "又是暴雨的一天",
        "现场风景更美",
        "点赞点赞",
        "说了个寂寞",
        "好家伙、过万了",
        "0：24",
        "666",
        "沙发",
        "来了",
        "签到",
        "打卡",
        "感谢分享",
        "谢谢分享",
        "学习了",
        "围观",
        "占楼",
    }
)
_ONLY_PUNCTUATION = re.compile(r"^[\W_]+$", re.UNICODE)
_REPEATED_FILLER = re.compile(r"^(.)\1{1,5}$")
_EDGE_PUNCTUATION = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def is_low_information(value: str | None) -> bool:
    text = normalize_text(value)
    compact = "".join(text.split()).casefold()
    if not compact:
        return False
    canonical = _EDGE_PUNCTUATION.sub("", compact)
    if canonical in _LOW_INFORMATION:
        return True
    if len(compact) <= 6 and (_ONLY_PUNCTUATION.fullmatch(compact) or _REPEATED_FILLER.fullmatch(compact)):
        return True
    return False

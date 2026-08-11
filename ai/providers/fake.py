"""Deterministic network-free provider for tests and explicit local demos."""

from __future__ import annotations

import json

from ai.providers.base import AIConnectivityResponse, AIProvider, AIProviderResponse
from ai.schemas.review_analysis import ReviewAnalysisInput


class FakeAIProvider(AIProvider):
    provider_name = "fake"

    def __init__(self, *, model: str = "fake-review-v1") -> None:
        self.model = model

    def analyze_review(
        self,
        request: ReviewAnalysisInput,
        *,
        prompt: str,
        validation_feedback: str = "",
    ) -> AIProviderResponse:
        del prompt, validation_feedback
        aspects: list[dict[str, object]] = []
        content = request.content
        context_dependent = content.strip() in {"我也是", "我的也这样", "确实"}
        searchable = (
            f"{request.thread_title}\n{request.thread_content}\n{request.parent_content}"
            if context_dependent
            else content
        )
        evidence = content
        context_id = request.parent_review_id or request.thread_review_id
        context_text = request.parent_content or request.thread_content

        def add(aspect: str, sentiment: str, category: str, summary: str, scenario: str = "") -> None:
            aspects.append(
                {
                    "aspect": aspect,
                    "sentiment": sentiment,
                    "sentiment_score": 0.8 if sentiment == "POSITIVE" else (-0.8 if sentiment == "NEGATIVE" else 0),
                    "issue_category": category,
                    "issue_summary": summary,
                    "usage_scenario": scenario,
                    "evidence_text": evidence,
                    "context_dependent": context_dependent,
                    "context_evidence_text": context_text if context_dependent else "",
                    "context_evidence_review_id": context_id if context_dependent else "",
                    "confidence": 0.72 if context_dependent else 0.92,
                }
            )

        negative = any(marker in searchable for marker in ("差", "掉电", "耗电", "热", "烫", "卡", "断网", "打不开"))
        positive = any(marker in searchable for marker in ("很好", "不错", "流畅", "强"))
        if any(marker in searchable for marker in ("续航", "掉电", "耗电", "待机")):
            battery_negative = any(marker in searchable for marker in ("续航差", "掉电", "耗电"))
            add(
                "BATTERY",
                "NEGATIVE" if battery_negative else "POSITIVE",
                "待机耗电" if battery_negative else "续航表现",
                "反馈涉及续航",
                "夜间待机" if "晚上" in searchable or "待机" in searchable else "",
            )
        if any(marker in searchable for marker in ("热", "烫", "发热")):
            add(
                "HEATING",
                "NEGATIVE",
                "游戏发热" if "游戏" in searchable else "机身发热",
                "反馈涉及发热",
                "游戏" if "游戏" in searchable else "",
            )
        if any(marker in searchable for marker in ("桌面滑动", "卡顿", "响应", "流畅")):
            add(
                "SYSTEM_FLUENCY",
                "POSITIVE" if positive and not negative else "NEGATIVE",
                "系统流畅度",
                "反馈涉及系统流畅度",
            )
        if any(marker in searchable for marker in ("游戏掉帧", "帧率", "性能")):
            add("PERFORMANCE", "NEGATIVE" if negative else "NEUTRAL", "游戏掉帧", "反馈涉及性能", "游戏")
        if any(marker in searchable for marker in ("屏幕", "显示")):
            add(
                "DISPLAY",
                "POSITIVE" if positive else ("NEGATIVE" if negative else "NEUTRAL"),
                "屏幕显示",
                "反馈涉及屏幕",
            )
        if any(marker in searchable for marker in ("太重", "偏重", "很重", "重量")):
            add("WEIGHT_AND_FEEL", "NEGATIVE", "机身偏重", "反馈认为手机偏重")
        valid = bool(aspects)
        output = {
            "product_model": request.product_model,
            "is_valid_content": valid,
            "content_type": "COMMUNITY_THREAD" if request.record_type == "THREAD" else "COMMUNITY_REPLY",
            "aspects": aspects,
            "software_version": request.software_version,
            "usage_scenarios": sorted({str(item["usage_scenario"]) for item in aspects if item["usage_scenario"]}),
            "summary": "结构化测试结果" if valid else "",
            "confidence": (0.72 if context_dependent else 0.92) if aspects else 0.5,
            "warnings": [] if valid else ["未识别到支持的分析维度"],
        }
        return AIProviderResponse(
            provider=self.provider_name,
            model=self.model,
            content=json.dumps(output, ensure_ascii=False),
            latency_ms=0,
        )

    def check_connectivity(self) -> AIConnectivityResponse:
        return AIConnectivityResponse(
            provider=self.provider_name,
            model=self.model,
            status="ok",
            latency_ms=0,
        )

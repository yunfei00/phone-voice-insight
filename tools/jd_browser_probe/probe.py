"""用独立可视 Chrome profile 监听用户正常操作产生的京东 XHR/fetch。"""

# ruff: noqa: RUF001

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Error, Frame, Page, Request, Response, sync_playwright

from tools.jd_browser_probe.detector import (
    DetectionResult,
    build_network_entry,
    inspect_payload,
    is_jd_host,
    is_json_like_content_type,
    parse_json_body,
    query_parameter_schema,
    redact_url,
    sensitive_query_names,
)
from tools.jd_browser_probe.sanitizer import find_denied_keys, sanitize_value

PRODUCT_ID = "100310496358"
PRODUCT_URL = f"https://item.jd.com/{PRODUCT_ID}.html"
LIVE_ENV = "RUN_JD_BROWSER_LIVE_TEST"
GENERATED_FILES = (
    "network-index.json",
    "stage-a-candidates.json",
    "sanitized-sample.json",
    "discovery-report.json",
)


@dataclass
class AccessState:
    login_page_seen: bool = False
    captcha_page_seen: bool = False
    risk_page_seen: bool = False
    observed_urls: list[str] = field(default_factory=list)

    def observe(self, url: str) -> None:
        lowered = url.casefold()
        if "passport.jd.com" in lowered or "/login" in lowered:
            self.login_page_seen = True
        if "captcha" in lowered or "verify" in lowered:
            self.captcha_page_seen = True
        if "risk" in lowered or "safe" in lowered:
            self.risk_page_seen = True
        redacted = redact_url(url)
        if redacted not in self.observed_urls:
            self.observed_urls.append(redacted)


@dataclass(frozen=True)
class CandidateCapture:
    candidate_id: int
    network: dict[str, Any]
    detection: DetectionResult
    query_parameters: list[dict[str, str]]
    sensitive_parameter_names: tuple[str, ...]

    def stage_a_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            **self.network,
            **self.detection.stage_a_dict(),
            "query_parameters": self.query_parameters,
            "sensitive_parameter_names": self.sensitive_parameter_names,
        }


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def _clean_generated_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in GENERATED_FILES:
        (output_dir / name).unlink(missing_ok=True)


class ProbeRecorder:
    def __init__(self, *, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.network_index: list[dict[str, Any]] = []
        self.candidates: list[CandidateCapture] = []
        self.request_count = 0
        self.response_errors: list[str] = []

    def on_request(self, request: Request) -> None:
        parsed = urlparse(request.url)
        if request.resource_type in {"xhr", "fetch"} and is_jd_host(parsed.hostname or ""):
            self.request_count += 1

    def on_response(self, response: Response) -> None:
        request = response.request
        try:
            content_type = response.header_value("content-type") or ""
            entry = build_network_entry(
                method=request.method,
                url=request.url,
                status=response.status,
                content_type=content_type,
                resource_type=request.resource_type,
            )
            if entry is None:
                return
            self.network_index.append(entry)
            _write_json(self.output_dir / "network-index.json", self.network_index)
            if not is_json_like_content_type(content_type):
                return
            payload = parse_json_body(response.text())
            if payload is None:
                return
            detection = inspect_payload(payload, url=request.url)
            if not detection.candidate:
                return
            capture = CandidateCapture(
                candidate_id=len(self.candidates) + 1,
                network=entry,
                detection=detection,
                query_parameters=query_parameter_schema(request.url),
                sensitive_parameter_names=sensitive_query_names(request.url),
            )
            self.candidates.append(capture)
            _write_json(
                self.output_dir / "stage-a-candidates.json",
                [candidate.stage_a_dict() for candidate in self.candidates],
            )
        except Error as exc:
            self.response_errors.append(type(exc).__name__)


def _attach_page(page: Page, access: AccessState) -> None:
    def on_frame(frame: Frame) -> None:
        if frame == page.main_frame:
            access.observe(frame.url)

    page.on("framenavigated", on_frame)


def _active_page(context: BrowserContext, fallback: Page) -> Page | None:
    pages = [page for page in context.pages if not page.is_closed()]
    return pages[-1] if pages else (fallback if not fallback.is_closed() else None)


def _wait_for_enter(context: BrowserContext, initial_page: Page) -> None:
    if os.name == "nt":
        import msvcrt

        while True:
            page = _active_page(context, initial_page)
            if page is None:
                return
            if msvcrt.kbhit():
                character = msvcrt.getwch()
                if character in {"\r", "\n"}:
                    print()
                    return
            page.wait_for_timeout(250)
    else:
        import select

        while True:
            page = _active_page(context, initial_page)
            if page is None:
                return
            readable, _writable, _errors = select.select([sys.stdin], [], [], 0)
            if readable:
                sys.stdin.readline()
                return
            page.wait_for_timeout(250)


def _ask_yes_no(prompt: str, *, default: bool = False) -> bool:
    suffix = "[y/N]" if not default else "[Y/n]"
    while True:
        answer = input(f"{prompt} {suffix} ").strip().casefold()
        if not answer:
            return default
        if answer in {"y", "yes", "是"}:
            return True
        if answer in {"n", "no", "否"}:
            return False
        print("请输入 y 或 n。")


def _select_candidate(candidates: list[CandidateCapture]) -> CandidateCapture | None:
    if not candidates:
        print("没有检测到候选评价响应。")
        return None
    print("\nStage A 候选请求（仅结构元数据）：")
    for candidate in candidates:
        arrays = ", ".join(f"{item.path}={item.length}" for item in candidate.detection.arrays[:4])
        print(
            f"  {candidate.candidate_id}. {candidate.network['method']} {candidate.network['url']} "
            f"status={candidate.network['status']} keys={list(candidate.detection.top_level_keys)} arrays={arrays}"
        )
    while True:
        answer = input("请输入人工确认的评价请求编号；留空表示没有：").strip()
        if not answer:
            return None
        if answer.isdigit():
            selected = next(
                (candidate for candidate in candidates if candidate.candidate_id == int(answer)),
                None,
            )
            if selected is not None:
                return selected
        print("编号无效，请重新输入。")


def _safe_locator_text(page: Page, selectors: tuple[str, ...]) -> str:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible():
                text = " ".join(locator.inner_text(timeout=1_000).split())
                if text:
                    return text[:300]
        except Error:
            continue
    return "未确认"


def _product_metadata(page: Page | None) -> dict[str, str]:
    if page is None:
        return {"product_id": PRODUCT_ID, "product_name": "未确认", "shop": "未确认"}
    return {
        "product_id": PRODUCT_ID,
        "product_name": _safe_locator_text(
            page,
            ('[itemprop="name"]', "h1", ".sku-name", '[class*="skuName"]'),
        ),
        "shop": _safe_locator_text(
            page,
            ("[data-shop-name]", ".shop-name", '[class*="shopName"]', '[class*="shop-name"]'),
        ),
    }


def classify_result(
    *,
    selected: CandidateCapture | None,
    review_area_normal: bool,
    login_required: bool,
) -> str:
    if selected is None or not review_area_normal:
        return "C JD_REVIEW_ACCESS_BLOCKED"
    if login_required or selected.sensitive_parameter_names:
        return "B BROWSER_SESSION_REQUIRED"
    return "A PUBLIC_ENDPOINT_FOUND"


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    product = report["product"]
    access = report["browser_access"]
    selected = report.get("confirmed_request")
    lines = [
        "# 京东评价接口发现报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 结果：`{report['result']}`",
        "- 方法：独立可视 Chrome profile，用户人工操作，程序只监听 JD XHR/fetch。",
        "- 隐私：未读取或保存 Cookie、Authorization、请求头、Set-Cookie、POST 数据或 Storage。",
        "",
        "## 商品",
        "",
        f"- product_id：`{_markdown_cell(product['product_id'])}`",
        f"- 商品名称：{_markdown_cell(product['product_name'])}",
        f"- 店铺：{_markdown_cell(product['shop'])}",
        "",
        "## 浏览器访问",
        "",
        f"- 商品页正常：{access['product_page_normal']}",
        f"- 评价区域正常：{access['review_area_normal']}",
        f"- 需要登录：{access['login_required']}",
        f"- 出现验证码：{access['captcha_seen']}",
        f"- 出现风险验证：{access['risk_seen']}",
        "",
        "## 评价请求",
        "",
    ]
    if selected is None:
        lines.append("未人工确认任何评价请求。")
    else:
        lines.extend(
            [
                "| host | path | method | status | content-type |",
                "| --- | --- | --- | ---: | --- |",
                (
                    f"| {_markdown_cell(selected['host'])} | {_markdown_cell(selected['path'])} | "
                    f"{_markdown_cell(selected['method'])} | {selected['status']} | "
                    f"{_markdown_cell(selected['content_type'])} |"
                ),
                "",
                "### Query 参数",
                "",
                "| 名称 | 非敏感示例 | 含义 |",
                "| --- | --- | --- |",
            ]
        )
        for parameter in selected["query_parameters"]:
            lines.append(f"| {_markdown_cell(parameter['name'])} | {_markdown_cell(parameter['example'])} | 未确认 |")
        lines.extend(["", "## 响应结构", ""])
        lines.append(f"- 顶层 keys：`{json.dumps(selected['top_level_keys'], ensure_ascii=False)}`")
        for array in selected["arrays"]:
            lines.append(
                f"- `{_markdown_cell(array['path'])}`：长度 {array['length']}；"
                f"item keys `{json.dumps(array['item_keys'], ensure_ascii=False)}`；"
                f"启发式提示 `{json.dumps(array['semantic_hints'], ensure_ascii=False)}`"
            )
    lines.extend(
        [
            "",
            "## 样本与隐私",
            "",
            f"- Stage B 脱敏样本条数：{report['sanitized_sample_count']}（最多 3 条，仅位于 `.local/`）。",
            "- 未保存昵称、UID、GUID、头像、手机号、邮箱、Cookie、Token 或完整响应。",
            "- 字段含义只记录现场确认结果；启发式 key 不直接作为正式 JDCollector 字段映射。",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _finalize_reports(
    *,
    output_dir: Path,
    docs_path: Path,
    recorder: ProbeRecorder,
    selected: CandidateCapture | None,
    product: dict[str, str],
    access: dict[str, bool],
) -> dict[str, Any]:
    sanitized_samples: list[Any] = []
    if selected is not None:
        sanitized_samples = [sanitize_value(item) for item in selected.detection.sample_items[:3]]
        denied = find_denied_keys(sanitized_samples)
        if denied:
            raise RuntimeError(f"脱敏样本仍包含禁止字段路径: {denied}")
        _write_json(output_dir / "sanitized-sample.json", sanitized_samples)

    result = classify_result(
        selected=selected,
        review_area_normal=access["review_area_normal"],
        login_required=access["login_required"],
    )
    confirmed_request: dict[str, Any] | None = None
    if selected is not None:
        confirmed_request = {
            "host": selected.network["host"],
            "path": selected.network["path"],
            "method": selected.network["method"],
            "status": selected.network["status"],
            "content_type": selected.network["content_type"],
            "url": selected.network["url"],
            "query_parameters": selected.query_parameters,
            "sensitive_parameter_names": selected.sensitive_parameter_names,
            "top_level_keys": selected.detection.top_level_keys,
            "arrays": [asdict(item) for item in selected.detection.arrays],
        }
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "result": result,
        "product": product,
        "browser_access": access,
        "network_request_count": recorder.request_count,
        "network_response_count": len(recorder.network_index),
        "candidate_count": len(recorder.candidates),
        "confirmed_request": confirmed_request,
        "sanitized_sample_count": len(sanitized_samples),
        "response_errors": recorder.response_errors,
        "privacy": {
            "cookies_saved": False,
            "authorization_saved": False,
            "request_headers_saved": False,
            "response_headers_saved": False,
            "post_data_saved": False,
            "browser_storage_read": False,
        },
    }
    _write_json(output_dir / "discovery-report.json", report)
    _write_markdown_report(docs_path, report)
    return report


def live_probe_enabled() -> bool:
    return os.getenv(LIVE_ENV) == "1"


def run_probe(*, repo_root: Path) -> dict[str, Any]:
    profile_dir = repo_root / ".local" / "jd-browser-profile"
    output_dir = repo_root / ".local" / "jd-probe"
    docs_path = repo_root / "docs" / "jd-interface-discovery.md"
    _clean_generated_outputs(output_dir)
    recorder = ProbeRecorder(output_dir=output_dir)
    access_state = AccessState()

    print("将启动独立 Chrome profile：.local/jd-browser-profile/")
    print("程序不会读取现有 Chrome profile、Cookie、密码、Storage 或浏览历史。")
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel="chrome",
            headless=False,
            accept_downloads=False,
            locale="zh-CN",
            no_viewport=True,
        )
        context.on("request", recorder.on_request)
        context.on("response", recorder.on_response)
        context.on("page", lambda created_page: _attach_page(created_page, access_state))
        page = context.pages[0] if context.pages else context.new_page()
        _attach_page(page, access_state)
        try:
            page.goto(PRODUCT_URL, wait_until="domcontentloaded", timeout=45_000)
        except Error:
            print("商品页导航未在 45 秒内完成，请在已打开的浏览器中人工确认当前页面。")

        print("\n请在浏览器中正常打开商品评价区域。")
        print("可以点击：")
        print("1. 商品评价")
        print("2. 最新评价")
        print("3. 下一页")
        print("\n如需登录，只能由你本人在这个独立 profile 中正常完成。")
        print("如出现验证码或风险验证，程序不会处理或绕过。")
        print("完成后回到此终端按 Enter。")
        _wait_for_enter(context, page)

        current_page = _active_page(context, page)
        product = _product_metadata(current_page)
        selected = _select_candidate(recorder.candidates)
        product_page_normal = _ask_yes_no("商品页是否正常显示？")
        review_area_normal = _ask_yes_no("商品评价区域是否正常显示？")
        login_required = _ask_yes_no("当前独立 profile 是否登录后才能看到评价？")
        captcha_seen = _ask_yes_no("是否出现验证码？", default=access_state.captcha_page_seen)
        risk_seen = _ask_yes_no("是否出现风险验证？", default=access_state.risk_page_seen)
        access = {
            "product_page_normal": product_page_normal,
            "review_area_normal": review_area_normal,
            "login_required": login_required,
            "captcha_seen": captcha_seen,
            "risk_seen": risk_seen,
            "login_page_seen": access_state.login_page_seen,
        }
        report = _finalize_reports(
            output_dir=output_dir,
            docs_path=docs_path,
            recorder=recorder,
            selected=selected,
            product=product,
            access=access,
        )
        context.close()
    print(f"\n探测完成：{report['result']}")
    print(f"本地报告：{output_dir / 'discovery-report.json'}")
    print(f"文档报告：{docs_path}")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="京东浏览器辅助接口探测（人工操作、只监听网络）")
    parser.add_argument(
        "--product-id",
        default=PRODUCT_ID,
        choices=(PRODUCT_ID,),
        help="当前阶段只允许已审核的荣耀 Power2 商品 ID",
    )
    return parser


def main() -> int:
    build_parser().parse_args()
    if not live_probe_enabled():
        print(f"默认禁止启动真实浏览器。请显式设置 {LIVE_ENV}=1 后重试。", file=sys.stderr)
        return 2
    repo_root = Path(__file__).resolve().parents[2]
    try:
        run_probe(repo_root=repo_root)
    except Error as exc:
        print(f"无法启动或连接独立 Chrome：{type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

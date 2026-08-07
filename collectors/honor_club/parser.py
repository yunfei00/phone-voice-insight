"""荣耀俱乐部公开话题页与帖子页 HTML 解析。"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from collectors.base import RawRecord
from collectors.honor_club.date_parser import parse_honor_datetime
from collectors.honor_club.normalizer import build_fallback_external_id, safe_raw_data

_THREAD_PATH_PATTERN = re.compile(r"thread-(?P<thread_id>\d+)-(?:\d+)-(?:\d+)\.html")
_PID_PATTERN = re.compile(r"(?:pid|post_?)(?P<pid>\d+)")
_FULL_TIME_PATTERN = re.compile(r"\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?")
_PARTIAL_TIME_PATTERN = re.compile(r"(?<!\d)\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?")
_UI_TEXT = {
    "举报",
    "评论",
    "点赞",
    "赞",
    "评论图片",
    "图片下载",
    "收藏",
    "分享",
}


def _text(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def _direct_text(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(value.strip() for value in node.find_all(string=True, recursive=False) if value.strip())


def _extract_thread_id(href: str) -> str | None:
    path_match = _THREAD_PATH_PATTERN.search(href)
    if path_match:
        return path_match.group("thread_id")
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    if query.get("mod") == ["viewthread"] and query.get("tid"):
        thread_id = query["tid"][0]
        return thread_id if thread_id.isdigit() else None
    return None


def _canonical_thread_url(thread_id: str) -> str:
    return f"https://club.honor.com/cn/thread-{thread_id}-1-1.html"


def _extract_count(node: Tag, selector: str) -> str:
    return _direct_text(node.select_one(selector))


def parse_topic_page(html: str, *, topic_id: int) -> list[RawRecord]:
    soup = BeautifulSoup(html, "html.parser")
    containers: list[Tag] = list(soup.select("#threadlist .gm-hlink"))
    if not containers:
        containers = [
            anchor for anchor in soup.select("#threadlist a[href]") if _extract_thread_id(str(anchor.get("href", "")))
        ]

    records: list[RawRecord] = []
    seen_thread_ids: set[str] = set()
    for container in containers:
        anchor = container if container.name == "a" else container.find("a", href=True)
        if not isinstance(anchor, Tag):
            continue
        thread_id = _extract_thread_id(str(anchor.get("href", "")))
        if not thread_id or thread_id in seen_thread_ids:
            continue

        title_node = container.select_one("h3, a.s.xst, .thread-title")
        title = _text(title_node)
        if not title:
            title = str(anchor.get("title", "")).strip()
        if not title:
            continue

        seen_thread_ids.add(thread_id)
        topic_tags = [_text(tag) for tag in container.select(".protalTag2, .topic-tag") if _text(tag)]
        role_text = _text(container.select_one(".post-times, .author-role"))
        latest_reply_time = _text(container.select_one(".latest-reply-time, .lastpost"))
        records.append(
            RawRecord(
                external_id=f"thread_link:{thread_id}",
                record_type="THREAD_LINK",
                payload={
                    "thread_id": thread_id,
                    "thread_url": _canonical_thread_url(thread_id),
                    "title": title,
                    "author_role_text": role_text,
                    "latest_reply_time": latest_reply_time,
                    "view_count": _extract_count(container, ".hinew_eye, .view-count"),
                    "reply_count": _extract_count(container, ".comments-rcle, .reply-count"),
                    "like_count": _extract_count(container, ".like-rcle, .like-count"),
                    "forum_name": _text(container.select_one(".protalTag1, .forum-name")),
                    "topic_name": next(iter(topic_tags), f"topic:{topic_id}"),
                    "topic_tags": topic_tags,
                },
            )
        )
    return records


def extract_topic_page_count(html: str, *, topic_id: int) -> int:
    soup = BeautifulSoup(html, "html.parser")
    pages = {1}
    canonical_pattern = re.compile(rf"threadtopic-{topic_id}-(\d+)\.html")
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", ""))
        if match := canonical_pattern.search(href):
            pages.add(int(match.group(1)))
        parsed = urlparse(href)
        query = parse_qs(parsed.query)
        if query.get("topicid") == [str(topic_id)] and query.get("page", [""])[0].isdigit():
            pages.add(int(query["page"][0]))
    return max(pages)


def _find_time(value: str) -> str:
    if match := _FULL_TIME_PATTERN.search(value):
        return match.group(0)
    if match := _PARTIAL_TIME_PATTERN.search(value):
        return match.group(0)
    return ""


def _clean_content(node: Tag | None) -> tuple[str, int]:
    if node is None:
        return "", 0
    image_count = len(node.find_all("img"))
    clone_soup = BeautifulSoup(str(node), "html.parser")
    clone = clone_soup.find()
    if not isinstance(clone, Tag):
        return "", image_count

    for unwanted in clone.select(
        "script, style, noscript, .preview_img_box, .comment_box, .moreList, "
        ".hbt-au, .hbt-binf, .ui-control, .protalTag, .ordinary_eye_num, .ordinary_last_text, "
        ".grey.quote, blockquote"
    ):
        unwanted.decompose()
    for profile_link in clone.find_all("a", href=True):
        href = str(profile_link.get("href", ""))
        if "mod=space" in href and _text(profile_link).startswith("@"):
            profile_link.decompose()
    for image in clone.find_all("img"):
        image.decompose()

    lines: list[str] = []
    for value in clone.get_text("\n").splitlines():
        normalized = " ".join(value.split())
        if normalized and normalized not in _UI_TEXT:
            lines.append(normalized)
    return "\n".join(lines).strip(), image_count


def _topic_tags(soup: BeautifulSoup) -> list[str]:
    tags: list[str] = []
    for node in soup.select(".topic-tag, .protalTag2, a[href*='topicid=']"):
        value = _text(node)
        if value and value not in tags:
            tags.append(value)
    return tags


def _extract_op_metadata(soup: BeautifulSoup) -> tuple[str, str, str]:
    role_text = ""
    device_source = ""
    published_at_raw = ""

    metadata_groups = soup.select(".hbt-tinf.hbfTinf .hbt-tmg, .thread-author-meta")
    if metadata_groups:
        role_text = _text(metadata_groups[0].select_one("b, .author-role"))
        device_source = _text(metadata_groups[0].select_one(".newPhonetype, .device-source"))
        for group in metadata_groups:
            if candidate := _find_time(_text(group)):
                published_at_raw = candidate
                break

    desktop_meta = soup.select_one(".authi, .post-meta")
    if desktop_meta is not None:
        published_at_raw = published_at_raw or _find_time(_text(desktop_meta))
        role_text = role_text or str(desktop_meta.get("data-author-role", ""))
        device_source = device_source or str(desktop_meta.get("data-device-source", ""))
    return role_text, device_source, published_at_raw


def _reply_containers(soup: BeautifulSoup) -> Iterable[Tag]:
    yielded: set[int] = set()
    for container in soup.select(".hbt-pl[id^='pid']"):
        yielded.add(id(container))
        yield container
    for content in soup.select("[id^='postmessage_']"):
        parent_container = content.find_parent(id=re.compile(r"^post_?\d+$"))
        if isinstance(parent_container, Tag) and id(parent_container) not in yielded:
            yielded.add(id(parent_container))
            yield parent_container


def _extract_pid(container: Tag) -> str | None:
    identifier = str(container.get("id", ""))
    if match := _PID_PATTERN.search(identifier):
        return match.group("pid")
    content = container.select_one("[id^='postmessage_']")
    if content is not None and (match := re.search(r"postmessage_(\d+)", str(content.get("id", "")))):
        return match.group(1)
    return None


def _nested_records(
    container: Tag,
    *,
    thread_id: str,
    thread_url: str,
    parent_pid: str | None,
    thread_published_at: datetime | None,
) -> list[RawRecord]:
    records: list[RawRecord] = []
    nested_nodes = container.select(".comment-item, .nested-comment, [data-comment-id]")
    for index, node in enumerate(nested_nodes, start=1):
        comment_id = str(node.get("data-comment-id", ""))
        if not comment_id and (match := re.search(r"(?:comment|reply)_?(\d+)", str(node.get("id", "")))):
            comment_id = match.group(1)
        content_node = node.select_one(".comment-content, .content") or node
        content, image_count = _clean_content(content_node)
        if not content:
            continue
        role_text = str(node.get("data-author-role", "")) or _text(node.select_one(".author-role"))
        published_at_raw = str(node.get("data-published-at", "")) or _find_time(_text(node))
        published_at = parse_honor_datetime(published_at_raw, reference=thread_published_at)
        external_id = (
            f"honor_comment:{comment_id}"
            if comment_id
            else build_fallback_external_id(
                thread_id=thread_id,
                floor=f"nested:{parent_pid or 'thread'}:{index}",
                published_at_raw=published_at_raw,
                content=content,
            )
        )
        parent_external_id = f"honor_post:{parent_pid}" if parent_pid else f"thread:{thread_id}"
        records.append(
            RawRecord(
                external_id=external_id,
                record_type="REPLY",
                payload={
                    "parent_external_id": parent_external_id,
                    "content": content,
                    "published_at": published_at,
                    "author_role_text": role_text,
                    "source_url": f"{thread_url}#{external_id}",
                    "raw_data": safe_raw_data(
                        thread_id=thread_id,
                        comment_id=comment_id,
                        published_at_raw=published_at_raw,
                        has_image=image_count > 0,
                        image_count=image_count,
                        parent_resolution="post" if parent_pid else "thread_fallback",
                    ),
                },
            )
        )
    return records


def parse_thread_page(
    html: str, *, thread_id: str, thread_url: str, listing_data: dict[str, object]
) -> list[RawRecord]:
    soup = BeautifulSoup(html, "html.parser")
    title = _text(soup.select_one(".hbtTbox h1, h1.thread-title, #thread_subject"))
    content_node = soup.select_one(".wapFirstThread, [id^='postmessage_'], .thread-content")
    content, image_count = _clean_content(content_node)
    if not title:
        title = str(listing_data.get("title", ""))
    if not content:
        content = title

    role_text, device_source, published_at_raw = _extract_op_metadata(soup)
    published_at = parse_honor_datetime(published_at_raw)
    topic_tags = _topic_tags(soup)
    if not topic_tags:
        listing_tags = listing_data.get("topic_tags", [])
        if isinstance(listing_tags, list):
            topic_tags = [str(value) for value in listing_tags if str(value)]

    thread_record = RawRecord(
        external_id=f"thread:{thread_id}",
        record_type="THREAD",
        payload={
            "parent_external_id": None,
            "title": title,
            "content": content,
            "published_at": published_at,
            "author_role_text": role_text or str(listing_data.get("author_role_text", "")),
            "source_url": thread_url,
            "raw_data": safe_raw_data(
                thread_id=thread_id,
                published_at_raw=published_at_raw,
                device_source=device_source,
                topic_tags=topic_tags,
                forum_name=listing_data.get("forum_name"),
                topic_name=listing_data.get("topic_name"),
                view_count=listing_data.get("view_count"),
                reply_count=listing_data.get("reply_count"),
                like_count=listing_data.get("like_count"),
                has_image=image_count > 0,
                image_count=image_count,
            ),
        },
    )
    records = [thread_record]

    for index, container in enumerate(_reply_containers(soup), start=1):
        pid = _extract_pid(container)
        content_node = container.select_one(".viewContPl, [id^='postmessage_'], .reply-content")
        reply_content, reply_image_count = _clean_content(content_node)
        if not reply_content:
            continue
        role_text = _text(container.select_one(".hbt-binf b, .author-role"))
        published_at_raw = _text(container.select_one(".hbt-pltime, .published-at"))
        if not published_at_raw:
            published_at_raw = _find_time(_text(container.select_one(".authi, .post-meta")))
        reply_published_at = parse_honor_datetime(published_at_raw, reference=published_at)
        floor = _text(container.select_one(".hbt-fav, .floor")) or str(index)
        external_id = (
            f"honor_post:{pid}"
            if pid
            else build_fallback_external_id(
                thread_id=thread_id,
                floor=floor,
                published_at_raw=published_at_raw,
                content=reply_content,
            )
        )
        records.append(
            RawRecord(
                external_id=external_id,
                record_type="REPLY",
                payload={
                    "parent_external_id": f"thread:{thread_id}",
                    "content": reply_content,
                    "published_at": reply_published_at,
                    "author_role_text": role_text,
                    "source_url": f"{thread_url}#pid{pid}" if pid else thread_url,
                    "raw_data": safe_raw_data(
                        thread_id=thread_id,
                        post_id=pid,
                        floor=floor,
                        published_at_raw=published_at_raw,
                        device_source=_text(container.select_one(".hbt-fphone, .device-source")),
                        has_image=reply_image_count > 0,
                        image_count=reply_image_count,
                    ),
                },
            )
        )
        records.extend(
            _nested_records(
                container,
                thread_id=thread_id,
                thread_url=thread_url,
                parent_pid=pid,
                thread_published_at=published_at,
            )
        )
    return records


def content_fingerprint(value: str) -> str:
    return hashlib.sha256(" ".join(value.split()).encode("utf-8")).hexdigest()

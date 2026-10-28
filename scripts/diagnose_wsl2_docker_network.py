#!/usr/bin/env python3
"""Read-only DNS/proxy diagnostic for Windows -> WSL2 -> Docker deployments.

Run on WSL2 host and inside the backend container; compare with Windows Resolve-DnsName.
Does not fetch external pages or bypass SSRF restrictions.
"""
import json
import os
import platform
import socket
import ipaddress

HOST = "club.honor.com"


def main():
    result = {"hostname": HOST, "platform": platform.platform(), "environment": "WSL2" if "microsoft" in platform.release().lower() else "Linux/container"}
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as f:
            result["dns_nameservers"] = [x.split()[1] for x in f if x.strip().startswith("nameserver ") and len(x.split()) > 1]
    except OSError:
        result["dns_nameservers"] = []
    result["proxy_variables_present"] = [k for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy") if os.environ.get(k)]
    try:
        ips = sorted({x[4][0] for x in socket.getaddrinfo(HOST, 443, type=socket.SOCK_STREAM)})
        result["resolved_addresses"] = ips
        result["blocked_addresses"] = [ip for ip in ips if not ipaddress.ip_address(ip).is_global]
        result["status"] = "SSRF_BLOCKED" if result["blocked_addresses"] else "DNS_PUBLIC"
    except OSError as exc:
        result["status"] = "DNS_ERROR"
        result["error"] = type(exc).__name__
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] != "DNS_PUBLIC":
        print("检查 Windows/WSL2/Docker DNS 和经批准的企业代理；不要关闭 SSRF 防护。")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import re
import dns.resolver
import dns.edns
import dns.message
import dns.query
import dns.rdatatype
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import OrderedDict
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import yaml

CONFIG_FILE = Path("config.yaml")

# 行首 IPv4（http 通道强制只保留 IP）
IP_HEAD_RE = re.compile(r"^\s*(\d{1,3}(?:\.\d{1,3}){3})")


def get_beijing_time() -> str:
    """北京时间 MMDD·HHMM"""
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%m%d·%H%M")


def parse_dns_entry(entry: str) -> tuple[str, str | None]:
    """解析 8.8.8.8 或 https://... 以及可选 &ecs="""
    entry = str(entry).strip()
    if "&ecs=" in entry:
        server, ecs = entry.split("&ecs=", 1)
        server, ecs = server.strip(), ecs.strip()
        return server, ecs if ecs else None
    return entry, None


def resolve_one_classic(domain: str, dns_server: str, ecs: str | None) -> list[str]:
    """普通 DNS（UDP，失败则 TCP）"""
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [dns_server]
    resolver.timeout = 5
    resolver.lifetime = 10

    options = []
    if ecs:
        try:
            options.append(dns.edns.ECSOption.from_text(ecs))
        except Exception as e:
            print(f"    [{dns_server}] ECS 无效，忽略: {e}")

    try:
        resolver.use_edns(edns=True, options=options if options else None, payload=1232)
        try:
            answer = resolver.resolve(domain, "A")
            ips = [r.address for r in answer]
            if ips:
                return ips
        except Exception as e:
            print(f"    [{dns_server}] UDP 失败，改 TCP: {type(e).__name__}")
        answer = resolver.resolve(domain, "A", tcp=True)
        return [r.address for r in answer]
    except Exception as e:
        print(f"    [{dns_server}] 失败: {type(e).__name__}: {e}")
        return []


def resolve_one_doh(domain: str, doh_url: str, ecs: str | None) -> list[str]:
    """DNS over HTTPS"""
    try:
        q = dns.message.make_query(domain, dns.rdatatype.A)
        if ecs:
            try:
                ecs_opt = dns.edns.ECSOption.from_text(ecs)
                q.use_edns(edns=True, options=[ecs_opt], payload=1232)
            except Exception as e:
                print(f"    [{doh_url}] ECS 无效，忽略: {e}")
                q.use_edns(edns=True, payload=1232)
        else:
            q.use_edns(edns=True, payload=1232)

        r = dns.query.https(q, doh_url, timeout=10)
        ips = []
        for rrset in r.answer:
            if rrset.rdtype == dns.rdatatype.A:
                for item in rrset:
                    ips.append(item.address)
        return ips
    except Exception as e:
        print(f"    [{doh_url}] DoH 失败: {type(e).__name__}: {e}")
        return []


def resolve_dns_list(domain: str, dns_list) -> list[str]:
    """多 DNS/DoH 合并去重（保序）"""
    if isinstance(dns_list, str):
        dns_list = [dns_list]

    merged = OrderedDict()
    for entry in dns_list:
        server, ecs = parse_dns_entry(entry)
        tag = f"{server}" + (f" +ECS {ecs}" if ecs else " (无ECS)")
        print(f"  查询 {tag}")
        if server.lower().startswith("https://"):
            ips = resolve_one_doh(domain, server, ecs)
        else:
            ips = resolve_one_classic(domain, server, ecs)
        print(f"    → {len(ips)} 个: {ips}")
        for ip in ips:
            if ip not in merged:
                merged[ip] = None
    return list(merged.keys())


def fetch_http_ips(url: str, filter_pattern: str) -> list[str]:
    """HTTP 拉取 → 正则筛选 → 只保留行首纯 IP"""
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 config-auto-dns"})
        with urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except (URLError, HTTPError, TimeoutError, Exception) as e:
        print(f"  HTTP 请求失败: {type(e).__name__}: {e}")
        return []

    try:
        cre = re.compile(filter_pattern)
    except re.error as e:
        print(f"  filter 正则无效: {e}")
        return []

    merged = OrderedDict()
    for line in text.splitlines():
        line = line.strip()
        if not line or not cre.search(line):
            continue
        m = IP_HEAD_RE.match(line)
        if m:
            ip = m.group(1)
            if ip not in merged:
                merged[ip] = None
    return list(merged.keys())


def format_line(ip: str, prefix: str, suffix: str, time_str: str) -> str:
    """ip#前缀ip@时间后缀"""
    return f"{ip}#{prefix}{ip}@{time_str}{suffix}"


def process_route(route: dict, time_str: str) -> tuple[list[str], list[str]]:
    """
    处理单通道
    返回 (全量行含#name, 受count限制行含#name)
    """
    name = str(route.get("name", "unnamed"))
    enable = route.get("enable", True)
    rtype = str(route.get("type", "dns")).lower().strip()
    count = int(route.get("count", 2))
    prefix = str(route.get("additional-prefix", ""))
    suffix = str(route.get("additional-suffix", ""))
    fallback = str(route.get("fallback", "0.0.0.0#替补"))

    print(f"\n----- 通道: {name} (type={rtype}) -----")
    if not enable:
        print("已关闭，跳过")
        return [], []

    ips: list[str] = []

    if rtype == "dns":
        domain = str(route.get("domain", "")).strip()
        dns_list = route.get("dns", ["8.8.8.8"])
        print(f"域名: {domain}")
        ips = resolve_dns_list(domain, dns_list)

    elif rtype == "http":
        url = str(route.get("url", "")).strip()
        filt = str(route.get("filter", ".*"))
        print(f"URL: {url}")
        print(f"filter: {filt}")
        ips = fetch_http_ips(url, filt)

    else:
        print(f"未知 type: {rtype}，跳过")
        return [], []

    print(f"得到 {len(ips)} 个 IP: {ips}")

    if not ips:
        print("使用 fallback")
        block = [f"#{name}", fallback]
        return block, block

    selected = ips[:count]
    all_lines = [f"#{name}"] + [format_line(ip, prefix, suffix, time_str) for ip in ips]
    limited_lines = [f"#{name}"] + [format_line(ip, prefix, suffix, time_str) for ip in selected]
    print(f"全量 {len(ips)} 条，本文件写入 {len(selected)} 条")
    return all_lines, limited_lines


def main():
    if not CONFIG_FILE.exists():
        print(f"错误：找不到 {CONFIG_FILE}")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    all_output_name = config.get("all_output", "ips-all.txt")
    output_map = config.get("output") or {}

    if not output_map:
        print("配置中没有 output 结果文件")
        return

    time_str = get_beijing_time()
    print(f"北京时间标记: {time_str}")
    print(f"结果文件数: {len(output_map)}")
    print(f"全量文件: {all_output_name}")

    all_content: list[str] = []

    for file_name, file_cfg in output_map.items():
        print(f"\n========== 结果文件: {file_name} ==========")
        routes = (file_cfg or {}).get("routes") or []
        file_lines: list[str] = []

        for route in routes:
            full_block, limited_block = process_route(route, time_str)
            if limited_block:
                file_lines.extend(limited_block)
                file_lines.append("")
            if full_block:
                all_content.extend(full_block)
                all_content.append("")

        path = Path(str(file_name))
        path.write_text("\n".join(file_lines).rstrip() + "\n", encoding="utf-8")
        print(f"已写入: {path}")

    all_path = Path(all_output_name)
    all_path.write_text("\n".join(all_content).rstrip() + "\n", encoding="utf-8")
    print(f"\n已写入全量: {all_path}")
    print("全部完成")


if __name__ == "__main__":
    main()

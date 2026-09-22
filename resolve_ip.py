#!/usr/bin/env python3
import dns.resolver
import dns.edns
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import yaml
from collections import OrderedDict

CONFIG_FILE = Path("config.yaml")

def get_beijing_time() -> str:
    """返回北京时间，格式：MMDD·HHMM（例：0921·1703）"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%m%d·%H%M")

def parse_dns_entry(entry: str) -> tuple[str, str | None]:
    """
    解析 DNS 条目
    支持：
      - 8.8.8.8
      - 8.8.8.8&ecs=14.153.0.0/24
    返回 (dns_server, ecs_subnet 或 None)
    """
    entry = str(entry).strip()
    if "&ecs=" in entry:
        server, ecs = entry.split("&ecs=", 1)
        server = server.strip()
        ecs = ecs.strip()
        return server, ecs if ecs else None
    return entry, None

def resolve_one(domain: str, dns_server: str, ecs_subnet: str | None) -> list[str]:
    """向单个 DNS 解析，支持可选 ECS + TCP 回退"""
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [dns_server]
    resolver.timeout = 5
    resolver.lifetime = 10

    options = []
    if ecs_subnet:
        try:
            options.append(dns.edns.ECSOption.from_text(ecs_subnet))
        except Exception as e:
            print(f"  [{dns_server}] ECS 无效 ({ecs_subnet})，忽略: {e}")

    try:
        resolver.use_edns(edns=True, options=options if options else None, payload=1232)

        # 先 UDP
        try:
            answer = resolver.resolve(domain, "A")
            ips = [rdata.address for rdata in answer]
            if ips:
                return ips
        except Exception as e:
            print(f"  [{dns_server}] UDP 失败，尝试 TCP: {type(e).__name__}")

        # TCP 回退
        answer = resolver.resolve(domain, "A", tcp=True)
        return [rdata.address for rdata in answer]

    except Exception as e:
        print(f"  [{dns_server}] 解析失败: {type(e).__name__}: {e}")
        return []

def resolve_ips(domain: str, dns_list: list) -> list[str]:
    """
    多 DNS 解析并合并去重（保持先出现的顺序）
    """
    # 兼容旧写法：dns 直接写字符串
    if isinstance(dns_list, str):
        dns_list = [dns_list]

    all_ips = OrderedDict()  # 用 OrderedDict 去重并保序

    for entry in dns_list:
        server, ecs = parse_dns_entry(entry)
        ecs_info = f" + ECS {ecs}" if ecs else " (无ECS)"
        print(f"  查询 {server}{ecs_info} ...")

        ips = resolve_one(domain, server, ecs)
        print(f"    → 得到 {len(ips)} 个: {ips}")

        for ip in ips:
            if ip not in all_ips:
                all_ips[ip] = None

    return list(all_ips.keys())

def process_route(route: dict, time_str: str):
    """
    处理单个通道
    返回 (all_lines, limited_lines)
    """
    name = route["name"]
    enable = route.get("enable", True)
    domain = str(route["domain"]).strip()
    dns_list = route.get("dns", ["8.8.8.8"])
    count = int(route.get("count", 2))
    placeholder = route.get("placeholder", "emoji")
    fallback = route.get("fallback", f"{domain}#{domain}@{time_str}")

    print(f"\n===== 处理通道: {name} =====")
    if not enable:
        print("通道已关闭，跳过")
        return [], []

    print(f"域名: {domain}")
    print(f"count: {count} | 占位符: {placeholder}")
    print(f"替补字段: {fallback}")

    ips = resolve_ips(domain, dns_list)
    print(f"合并去重后共 {len(ips)} 个 IP: {ips}")

    if not ips:
        print("解析失败或 0 个 IP，使用替补字段")
        all_lines = [f"#{name}", fallback]
        limited_lines = [f"#{name}", fallback]
        return all_lines, limited_lines

    selected = ips[:count]

    # 全量（不受 count 限制）
    all_lines = [f"#{name}"]
    all_lines.extend([f"{ip}#{placeholder} {ip}@{time_str}" for ip in ips])

    # 受 count 限制
    limited_lines = [f"#{name}"]
    limited_lines.extend([f"{ip}#{placeholder} {ip}@{time_str}" for ip in selected])

    print(f"全量写入 {len(ips)} 个，受限制写入 {len(selected)} 个")
    return all_lines, limited_lines

def main():
    if not CONFIG_FILE.exists():
        print(f"错误：找不到配置文件 {CONFIG_FILE}")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    all_output_name = config.get("all_output", "ips-all.txt")
    limited_output_name = config.get("limited_output", "ips-limited.txt")
    routes = config.get("routes", [])

    if not routes:
        print("配置文件中没有定义任何通道")
        return

    time_str = get_beijing_time()
    print(f"当前北京时间标记: {time_str}")
    print(f"共加载 {len(routes)} 个通道配置")
    print(f"全量结果文件: {all_output_name}")
    print(f"受限制结果文件: {limited_output_name}")

    all_content_lines = []
    limited_content_lines = []

    for route in routes:
        all_lines, limited_lines = process_route(route, time_str)
        if all_lines:
            all_content_lines.extend(all_lines)
            all_content_lines.append("")

            limited_content_lines.extend(limited_lines)
            limited_content_lines.append("")

    # 写入全量结果
    all_file = Path(all_output_name)
    all_file.write_text("\n".join(all_content_lines).rstrip() + "\n", encoding="utf-8")
    print(f"\n已生成全量结果文件: {all_file}")

    # 写入受限制结果
    limited_file = Path(limited_output_name)
    limited_file.write_text("\n".join(limited_content_lines).rstrip() + "\n", encoding="utf-8")
    print(f"已生成受限制结果文件: {limited_file}")

    print("\n全部处理完成")

if __name__ == "__main__":
    main()

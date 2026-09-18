#!/usr/bin/env python3
import dns.resolver
import dns.edns
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import yaml

CONFIG_FILE = Path("config.yaml")
ALL_FILE = Path("ips-all.txt")

def get_beijing_time() -> str:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%m%d-%H%M")

def resolve_ips(domain: str, dns_server: str, ecs_subnet: str) -> list[str]:
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [dns_server]
    resolver.timeout = 5
    resolver.lifetime = 10

    try:
        ecs = dns.edns.ECSOption.from_text(ecs_subnet)
        resolver.use_edns(edns=True, options=[ecs])
        answer = resolver.resolve(domain, "A")
        return [rdata.address for rdata in answer]
    except Exception as e:
        print(f"[{domain}] 解析失败: {type(e).__name__}: {e}")
        return []

def process_route(route: dict, time_str: str) -> list[str]:
    """处理单路，返回用于 ips-all.txt 的行"""
    name = route["name"]
    domain = route["domain"]
    dns_server = route["dns"]
    ecs = route["ecs"]
    count = int(route.get("count", 2))

    output_file = Path(f"ips-{name}.txt")   # 强制带 .txt 后缀

    print(f"\n===== 处理通路: {name} =====")
    print(f"域名: {domain} | DNS: {dns_server} | ECS: {ecs} | 需要数量: {count}")

    ips = resolve_ips(domain, dns_server, ecs)
    print(f"实际解析到 {len(ips)} 个 IP: {ips}")

    # ---------- 单路结果文件 ----------
    if not ips:
        # 失败或 0 个 IP：只写一行保底
        content = f"{domain}#{domain}@{time_str}\n"
        output_file.write_text(content, encoding="utf-8")
        print(f"失败，已写入保底内容到 {output_file}")

        # 给汇总文件用
        return [f"# {domain}", f"{domain}#{domain}@{time_str}"]

    # 成功：按 count 限制写入单路文件
    selected = ips[:count]
    lines = [f"{ip}#{ip}@{time_str}" for ip in selected]
    content = "\n".join(lines) + "\n"
    output_file.write_text(content, encoding="utf-8")
    print(f"成功，已写入 {len(selected)} 个 IP 到 {output_file}")

    # 汇总文件：不受 count 限制，写全部 IP
    all_lines = [f"# {domain}"]
    all_lines.extend([f"{ip}#{ip}@{time_str}" for ip in ips])
    return all_lines

def main():
    if not CONFIG_FILE.exists():
        print(f"错误：找不到配置文件 {CONFIG_FILE}")
        return

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    routes = config.get("routes", [])
    if not routes:
        print("配置文件中没有定义任何通路")
        return

    time_str = get_beijing_time()
    print(f"当前北京时间标记: {time_str}")
    print(f"共加载 {len(routes)} 路配置")

    all_content_lines = []

    for route in routes:
        route_lines = process_route(route, time_str)
        all_content_lines.extend(route_lines)
        all_content_lines.append("")  # 通路之间空一行

    # 写入汇总文件
    all_content = "\n".join(all_content_lines).rstrip() + "\n"
    ALL_FILE.write_text(all_content, encoding="utf-8")
    print(f"\n已生成汇总文件: {ALL_FILE}")

    print("\n全部处理完成")

if __name__ == "__main__":
    main()

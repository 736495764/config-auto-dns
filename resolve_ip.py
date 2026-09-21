#!/usr/bin/env python3
import dns.resolver
import dns.edns
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import yaml

CONFIG_FILE = Path("config.yaml")

def get_beijing_time() -> str:
    """返回北京时间，格式：MMDD·HHMM（例：0921·1703）"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.strftime("%m%d·%H%M")

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

def process_route(route: dict, time_str: str):
    """
    处理单个通道
    返回两个列表：
    - all_lines: 全量结果（不受 count 限制）
    - limited_lines: 受 count 限制的结果
    """
    name = route["name"]
    enable = route.get("enable", True)
    domain = route["domain"]
    dns_server = route["dns"]
    ecs = route["ecs"]
    count = int(route.get("count", 2))
    output_name = route["output"]
    placeholder = route.get("placeholder", "emoji")
    fallback = route.get("fallback", f"{domain}#{domain}@{time_str}")

    output_file = Path(output_name)

    print(f"\n===== 处理通道: {name} =====")
    if not enable:
        print("通道已关闭，跳过")
        return [], []

    print(f"域名: {domain} | DNS: {dns_server} | ECS: {ecs} | 数量限制: {count}")
    print(f"输出文件: {output_file} | 占位符: {placeholder}")
    print(f"替补字段: {fallback}")

    ips = resolve_ips(domain, dns_server, ecs)
    print(f"实际解析到 {len(ips)} 个 IP: {ips}")

    # ---------- 单通道结果文件 ----------
    if not ips:
        # 失败：写一行替补
        output_file.write_text(fallback + "\n", encoding="utf-8")
        print(f"失败，已写入替补内容到 {output_file}")

        all_lines = [f"#{name}", fallback]
        limited_lines = [f"#{name}", fallback]
        return all_lines, limited_lines

    # 成功
    selected = ips[:count]          # 受 count 限制
    lines = [f"{ip}#{placeholder} {ip}@{time_str}" for ip in selected]
    content = "\n".join(lines) + "\n"
    output_file.write_text(content, encoding="utf-8")
    print(f"成功，已写入 {len(selected)} 个 IP 到 {output_file}")

    # 全量结果（不受 count 限制）
    all_lines = [f"#{name}"]
    all_lines.extend([f"{ip}#{placeholder} {ip}@{time_str}" for ip in ips])

    # 受 count 限制的结果
    limited_lines = [f"#{name}"]
    limited_lines.extend([f"{ip}#{placeholder} {ip}@{time_str}" for ip in selected])

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
            all_content_lines.append("")          # 通道之间空一行

            limited_content_lines.extend(limited_lines)
            limited_content_lines.append("")

    # 写入全量结果文件
    all_file = Path(all_output_name)
    all_content = "\n".join(all_content_lines).rstrip() + "\n"
    all_file.write_text(all_content, encoding="utf-8")
    print(f"\n已生成全量结果文件: {all_file}")

    # 写入受 count 限制的结果文件
    limited_file = Path(limited_output_name)
    limited_content = "\n".join(limited_content_lines).rstrip() + "\n"
    limited_file.write_text(limited_content, encoding="utf-8")
    print(f"已生成受限制结果文件: {limited_file}")

    print("\n全部处理完成")

if __name__ == "__main__":
    main()

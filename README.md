基于 GitHub Actions 的多通道 IP 自动解析 / 拉取工具。

支持：
- **DNS / DoH** 解析（可选 ECS）
- **HTTP** 从远程文本拉取并筛选 IP
- 以**结果文件**为主组织输出
- 全量汇总文件
- 第三方定时触发（推荐 cron-job.org，避免 GitHub 自带 schedule 不准时）

---

## 功能概览

| 功能 | 说明 |
|------|------|
| DNS 通道 | 向多个 DNS / DoH 查询 A 记录，合并去重 |
| ECS | 每个 DNS 可单独指定网段，例如 `8.8.8.8&ecs=14.153.0.0/24` |
| DoH | 支持 `https://dns.google/dns-query` 等形式 |
| HTTP 通道 | 请求 URL → 正则筛选 → **只保留行首纯 IP** |
| 结果文件 | 按配置生成多个文件，每个文件可包含多条通道 |
| 全量汇总 | `all_output` 汇总所有启用通道的完整结果（不受 count 限制） |
| 失败保底 | 解析/拉取失败或 0 条时，写入自定义 `fallback` 一行 |

成功时单行格式：

```text
ip#前缀ip@北京时间后缀
```

示例：

```text
123.123.123.123#🗺️qmsct-123.123.123.123@0923·2030-负载均衡
```

时间格式：北京时间 `MMDD·HHMM`（中间为中文点 `·`）。

---

## 快速开始

1. **Fork** 本仓库到你的账号  
2. 修改根目录 `config.yaml`（见下文）  
3. 在 Actions 中手动运行一次工作流，确认生成结果文件  
4. 配置 [cron-job.org](https://cron-job.org) 定时触发（见下文）  
5. 仓库 Settings → Actions → General → Workflow permissions 设为 **Read and write permissions**

---

## 配置说明：`config.yaml`

### 整体结构

```yaml
all_output: "ips-all.txt"    # 全量汇总文件名（可自定义后缀）

output:
  "ips-1.txt":               # 某个结果文件（受各通道 count 限制）
    routes:
      - name: "通道A"
        type: dns
        # ...
      - name: "通道B"
        type: http
        # ...
  "ips-2.txt":
    routes:
      - name: "通道C"
        # ...
```

- **以结果文件为主干**：先定义输出文件名，再在其下挂 `routes`。
- 每个结果文件只写入该文件下启用通道的结果（受各自 `count` 限制）。
- `all_output` 汇总**所有**结果文件里启用通道的**全部** IP（不受 count 限制）。

---

### 通道公共字段

| 字段 | 说明 |
|------|------|
| `name` | 通道名称；结果中以 `#名称` 作为分段标题 |
| `enable` | `true` / `false`，是否启用 |
| `type` | `dns` 或 `http` |
| `count` | 写入**该结果文件**时最多保留几条 |
| `additional-prefix` | 输出前缀 |
| `additional-suffix` | 输出后缀 |
| `fallback` | 失败或 0 条时写入的**一行**内容（原样写入） |

成功行格式：

```text
{ip}#{additional-prefix}{ip}@{时间}{additional-suffix}
```

---

### 类型一：`type: dns`

```yaml
- name: "qms_ct"
  enable: true
  type: dns
  domain: "ct.877774.xyz"
  dns:
    - "8.8.8.8&ecs=14.152.0.0/24"              # 普通 DNS + ECS
    - "1.1.1.1"                                 # 普通 DNS，无 ECS
    - "https://dns.google/dns-query&ecs=14.153.0.0/24"   # DoH + ECS
    - "https://cloudflare-dns.com/dns-query"    # DoH，无 ECS
  count: 2
  additional-prefix: "🗺️qmsct-"
  additional-suffix: "-负载均衡"
  fallback: "172.64.229.44#替补"
```

**`dns` 列表写法：**

| 写法 | 含义 |
|------|------|
| `8.8.8.8` | 普通 DNS，不带 ECS |
| `8.8.8.8&ecs=14.153.0.0/24` | 普通 DNS，强制按该网段查询 |
| `https://dns.google/dns-query` | DoH，不带 ECS |
| `https://dns.google/dns-query&ecs=14.153.0.0/24` | DoH + ECS |

- 多个 DNS/DoH 的结果会**合并去重**（保留先出现的顺序）。
- 带 `&ecs=` 时会在查询中附带 ECS，效果类似强制指定客户端网段。
- 建议给带特殊字符的项加上双引号。

常用 DoH 地址示例：

- `https://dns.google/dns-query`
- `https://cloudflare-dns.com/dns-query`
- `https://doh.pub/dns-query`
- `https://dns.alidns.com/dns-query`

---

### 类型二：`type: http`

```yaml
- name: "微测优选"
  enable: true
  type: http
  url: "https://bestcf.pages.dev/wetest/ipv4.txt"
  filter: "(?i)^(?=.*(关键词1|关键词2))(?!.*(排除1|排除2)).*$"
  count: 5
  additional-prefix: "🗺️微测优选-"
  additional-suffix: "-手动选择"
  fallback: "172.64.229.44#替补"
```

处理流程：

1. GET 请求 `url`，按行读取  
2. 用 `filter` 正则筛选行  
3. **只保留行首纯 IPv4**（去掉端口及后面所有内容）  
   - 例：`104.17.152.209:443#微测优选 | 移动 | HKG` → `104.17.152.209`  
4. 按 `count` 截取后写入结果文件  

`filter` 使用 Python 正则；不需要筛选时可写 `".*"`。

---

### 完整示例

```yaml
all_output: "ips-all.txt"

output:
  "ips-1.txt":
    routes:
      - name: "qms_ct"
        enable: true
        type: dns
        domain: "ct.877774.xyz"
        dns:
          - "8.8.8.8&ecs=14.152.0.0/24"
          - "https://dns.google/dns-query&ecs=14.153.0.0/24"
        count: 2
        additional-prefix: "🗺️qmsct-"
        additional-suffix: "-负载均衡"
        fallback: "172.64.229.44#替补"

      - name: "微测优选"
        enable: true
        type: http
        url: "https://bestcf.pages.dev/wetest/ipv4.txt"
        filter: ".*"
        count: 5
        additional-prefix: "🗺️微测优选-"
        additional-suffix: "-手动选择"
        fallback: "172.64.229.44#替补"

  "ips-2.txt":
    routes:
      - name: "backup"
        enable: true
        type: dns
        domain: "example.com"
        dns:
          - "1.1.1.1"
        count: 2
        additional-prefix: ""
        additional-suffix: ""
        fallback: "0.0.0.0#替补"
```

---

## Fork 后配置定时任务（cron-job.org）

GitHub 自带的 `schedule` 经常延迟，建议用 **cron-job.org** 调用 `workflow_dispatch`。

### 1. 打开仓库写权限

路径：**Settings → Actions → General → Workflow permissions**

选择：**Read and write permissions** → Save。

### 2. 创建 GitHub Token

1. 打开 [https://github.com/settings/tokens](https://github.com/settings/tokens)  
2. **Generate new token (classic)**  
3. 勾选至少：`repo`（或包含 workflow 相关权限）  
4. 生成后复制保存（只显示一次）

### 3. 在 cron-job.org 创建任务

1. 注册并登录 [https://cron-job.org](https://cron-job.org)  
2. 创建 Cronjob，按下面填写：

| 项目 | 内容 |
|------|------|
| **Title** | 随意，如 `config-auto-dns` |
| **URL** | `https://api.github.com/repos/<你的用户名>/<仓库名>/actions/workflows/resolve-ip.yml/dispatches` |
| **Request Method** | `POST` |
| **Schedule** | 自定义：`7,37 * * * *`（每小时的 07 分、37 分，避开整点） |

**Request Headers：**

```text
Authorization: token <你的GitHub_Token>
Accept: application/vnd.github.v3+json
Content-Type: application/json
```

**Request Body：**

```json
{"ref":"main"}
```

若默认分支不是 `main`，改成实际分支名（如 `master`）。

### 4. 示例 URL

若仓库为 `https://github.com/736495764/config-auto-dns`：

```text
https://api.github.com/repos/736495764/config-auto-dns/actions/workflows/resolve-ip.yml/dispatches
```

Fork 到自己账号后，把用户名和仓库名换成你的即可。

### 5. 测试

在 cron-job.org 里执行一次测试，到 GitHub 仓库的 **Actions** 页查看是否出现新的运行记录。成功后会自动提交更新后的结果文件。

---

## 手动运行

1. 打开仓库 **Actions**  
2. 选择工作流 **Resolve Cloudflare IPs**  
3. **Run workflow** → 确认运行  

日志中可看到每个 DNS/DoH/HTTP 的查询结果与合并数量。

---

## 输出示例

**某个结果文件（如 `ips-1.txt`，受 count 限制）：**

```text
#qms_ct
172.64.229.173#🗺️qmsct-172.64.229.173@0923·2030-负载均衡
172.64.229.217#🗺️qmsct-172.64.229.217@0923·2030-负载均衡

#微测优选
104.17.152.209#🗺️微测优选-104.17.152.209@0923·2030-手动选择
```

**全量 `ips-all.txt`（不受 count 限制）：**  
结构相同，但每个通道会写入解析到的全部 IP。

失败时：

```text
#qms_ct
172.64.229.44#替补
```

---

## 注意事项

1. **Cloudflare 域名**通过公共 DNS 往往只返回少量 A 记录（1～数个），这是正常现象；跨地域 ECS + 多 DNS/DoH 可适当增加去重后的数量，但很难达到扫描类网站的规模。  
2. HTTP 源站需可被 GitHub Actions 访问（公网可达）。  
3. Token 不要提交进仓库；只放在 cron-job.org 的请求头中。  
4. 修改 `config.yaml` 后建议先手动跑通，再依赖定时任务。

---

## 依赖

- Python 3  
- `dnspython`  
- `pyyaml`  

由 GitHub Actions 在运行时自动安装。

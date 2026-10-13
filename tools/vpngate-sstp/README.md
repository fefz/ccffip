# VPN Gate SSTP 节点筛选与发布

从 VPN Gate 官方 SSTP 列表筛选日本（JP）和韩国（KR）节点，完整连接 VPN 检查实际出口，并将结果发布到本仓库 `data/sstp.txt`。这是当前服务器上运行的代码，不是仅供展示的示例。

## 功能与筛选标准

- 每个地区最多选 3 个；不检测 US、TW。
- 优先兼顾在线会话数少、官方公布带宽高、列表延迟低，以及两轮 SSTP 握手的延迟和成功次数。
- JP 优先检查 IP2Location 入口定位为东京的候选；候选不足时可扩大日本候选范围，但最终发布的 JP **实际出口必须经两库判定为东京地区**。
- JP、KR 均完成 SSTP/PPP 登录后，通过隧道查询公网出口 IP，而不是把 SSTP 服务器入口 IP 当作出口。
- IP2Location 官方网页须将实际出口标记为 `Fixed Line ISP`，且不能是 `DCH` 或 `Data Center`。
- IPLocate 查询同一个实际出口，须明确满足 `privacy.is_hosting=false`、`company.type=isp`、`asn.type=isp`，两库国家必须匹配目标国家。
- JP 还须满足 IP2Location 城市或地区为 Tokyo，以及 IPLocate 城市或 subdivision 为 Tokyo。Shinjuku + Tokyo subdivision 可通过。
- 数据缺失、网站查询失败、国家或必需分类冲突均不通过，不会用未验证节点补足。
- 最多复核每个地区排名靠前的 12 个可达候选，取最先通过完整检查的 3 个；这不是全网最优或实测带宽前三名。

## 前置入口与输出格式

每次运行从 GitHub `fefz/ccffip` 的 `main` 分支读取最新 `data/ip.txt`：跳过空行及以 `#` 开头的注释，按文件顺序取前三条，截取旧 `#` 标签前的 `IP:port`。不重新测速、排序或去重；不足三条或格式错误时终止。

每个地区的 1、2、3 号 SSTP 节点分别配对入口文件的第 1、2、3 条；JP 和 KR 共用这三个入口。

格式：

```text
<入口IP>:<入口端口>#Mine-<JP或KR>-家宽-<1至3>$sstp://vpn:vpn@<SSTP主机名>:<SSTP端口>
```

`vpn:vpn` 是 VPN Gate 公共登录凭据。内部 `parse_hk`、`hk` 变量名是历史命名；实际前置来源由 `run.py` 中 `FRONT_SOURCE='data/ip.txt'` 指定，不读取 `hk.txt`。

## 文件说明

- `run.py`：官方列表抓取、候选检测、筛选、GitHub 发布及回读。
- `refresh.py`：列表/网页解析、评分、家宽交叉验证和输出格式校验。
- `egress.py`：隔离网络命名空间内的 SSTP/PPP 登录及真实出口检测。
- `test_refresh.py`：输出配对、国家范围、东京优先、网页解析及家宽校验测试。
- `requirements.txt`：Python 依赖。
- `vpngate-sstp-refresh.service` / `.timer`：生产定时任务示例。

## 安装与运行

需要有 root 和网络管理能力的 Linux，支持 PPP、veth 和 network namespace。普通受限容器可能无法运行完整检测。以下路径与所附 systemd 单元一致：

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends -y python3 python3-requests python3-bs4 ppp sstp-client iproute2 iptables curl gh git

git clone https://github.com/fefz/ccffip.git
sudo mkdir -p /opt/vpngate-sstp
sudo cp ccffip/tools/vpngate-sstp/* /opt/vpngate-sstp/

# 在实际运行任务的 root 账户下授权，切勿把 token 写入代码。
sudo -H gh auth login
sudo -H gh auth status

sudo -H python3 /opt/vpngate-sstp/test_refresh.py
sudo -H python3 /opt/vpngate-sstp/run.py
```

也可在虚拟环境中通过 `pip install -r requirements.txt` 安装 Python 依赖；若使用虚拟环境，须同步修改 service 的 `ExecStart`。提供的 service 使用 `/usr/bin/python3`，因此上面的系统包安装方案无需额外修改。

执行前确保 `net.ipv4.ip_forward=1`、`/dev/ppp` 可用，以及主机已有正常 IPv4 默认路由。脚本不会自动修改 IP 转发开关。

## 每两小时运行

```bash
sudo install -m 644 /opt/vpngate-sstp/vpngate-sstp-refresh.service /etc/systemd/system/
sudo install -m 644 /opt/vpngate-sstp/vpngate-sstp-refresh.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vpngate-sstp-refresh.timer

# 立即运行并查看本次结果
sudo systemctl start vpngate-sstp-refresh.service
sudo systemctl show vpngate-sstp-refresh.service -p Result -p ExecMainStatus
sudo journalctl -u vpngate-sstp-refresh.service -n 30 --no-pager
sudo systemctl list-timers vpngate-sstp-refresh.timer
```

定时器在**服务器时区**每逢偶数小时运行，例如 00:00、02:00、04:00；`Persistent=true` 支持开机补跑。部署主机当前采用北京时间。单次任务默认超时 15 分钟；网络极差时可通过 systemd override 调整，不能把超时当作成功。文件锁避免重复执行。

## GitHub 发布与检查

默认仓库 `fefz/ccffip`、分支 `main`、前置源 `data/ip.txt`、目标 `data/sstp.txt`，均在 `run.py` 顶部定义。更换仓库须同时修改相应常量和测试中的预期路径，并授权目标仓库写权限。

通过 GitHub Contents API 更新目标文件，明确指定分支及旧文件 SHA；提交后读取目标文件，与本地输出逐字节比较。仅更新 `data/sstp.txt`，不修改 `data/ip.txt` 或其他扫描结果。

本地生成 `latest-report.json`，记录本轮源文件 SHA、入口列表、候选、实际出口、两个数据库的分类、拒绝情况、缺额及 GitHub commit。日志中的 `VERIFIED` 才表示发布并回读完成；不要把历史日志的成功行当作本轮成功。

某地区不足 3 个时发布实际通过的数量并报告缺额；全部地区零结果时退出失败，不上传空文件，原文件会保留，但**不能因此称旧节点已通过本轮新检测**。

## 安全与限制

- 完整检测在临时网络命名空间中进行，只有命名空间默认路由走 PPP；主机默认路由不变。临时 veth 和窄范围 NAT/FORWARD 规则在检测结束后清理。
- 使用保留给脚本的命名空间 `sstp-egress-publisher`、veth `sstpubh/sstpubn`、子网 `10.254.98.0/30`；不要与其他服务复用。
- VPN Gate 自签名证书通过 `--cert-warn` 接受；这不等于证书可信验证。不要用这些公开 VPN 传输敏感信息。
- 官网公布的 Mbps 不等于本组合链路实测带宽。当前不做下载吞吐测量，也未验证“前置入口 + SSTP”组合链路的最终客户端效果；完整出口测试是直接连接 SSTP。
- “家宽”是两个数据库共同支持的固定线路 ISP / 非 hosting 分类，**不是物理住宅证明**。公共 VPN 标记可能仍为 true，脚本不会把 `is_vpn` 等同于机房。
- IP 定位有误差；东京是统一数据库判定口径，不能保证其他查询网站完全一致。
- IP2Location 使用官方 demo 网页，IPLocate 使用无 Key 查询入口；当前可用不代表永久免费或无限配额。限流、服务变更或网页结构变化会导致候选被拒绝，不绕过验证码或访问限制。
- 不提交 `source.html`、GeoIP 缓存、`latest-report.json`、运行日志、锁文件、生成结果副本或 GitHub 凭据。

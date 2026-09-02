# ASN → CFData → CF NRT 扫描流程

这套脚本固化当前使用的三阶段流程：

1. 生成 CIDR 内全部 IPv4 地址。
2. Masscan 全量 TCP `1-65535`，只记录 TCP 开放端口。
3. 直接对 masscan 开放端口做 HTTPS `/cdn-cgi/trace` 校验，只保留 `colo=NRT` 的端点。
4. 用 `github_append.py` 从 GitHub Contents API 读取现有文件，去重后每 20 条追加，任务结束时补传不足 20 条的余数。

## 文件

- `scan_pipeline.sh`：隔离目录、全端口扫描和 NRT 筛选的串行入口。
- `nrt_filter.py`：直接解析 masscan 输出，使用 `speed.cloudflare.com` SNI 检查真实 `colo=NRT`。
- `github_append.py`：安全读取 SHA、批量追加并回读所需的发布工具。

## 运行示例

在已安装 Masscan、Python 3 和现有 CFData fork 的扫描机上：

```bash
cd /path/to/asn-cfdata-nrt-scan
export WORKDIR=/tmp/cfscan-gm
export CIDRS='14.137.229.0/24 103.112.1.0/24'
export MASSCAN_RATE=10000
nohup ./scan_pipeline.sh > "$WORKDIR.console.log" 2>&1 &
```

扫描结束后，从运行机把 `nrt-validated.txt` 复制到有持久化 `gh` 授权的发布机，再执行：

```bash
python3 github_append.py /tmp/cfscan-gm/nrt-validated.txt \
  --repo fefz/ccffip --path gm_jp.txt
```

若发布机直接可读扫描机文件，可由外层 SSH/同步脚本先完成复制；脚本本身不保存密码，也不依赖 `sshpass`。

## 关键参数

- `MASSCAN_RATE`：默认 `10000`。这是发包速率，不是线程并发。
- `NRT_WORKERS`：默认 `256`，用于 HTTPS trace 校验。
- `NRT_FILTER`：默认当前目录的 `nrt_filter.py`。

## 产物和判断边界

```text
targets.txt                 输入地址
masscan.list                TCP 开放端口
nrt-validated.txt           HTTPS trace 明确报告 colo=NRT
run.log                     MASSCAN_FINISHED / NRT_FINISHED
```

TCP 开放和 NRT trace 成功不是速度测试，也不代表 VLESS、SS、WS 或其他代理协议可用。本流程不执行下载测速，不把这些结果标记为 Mbps。

## 安全和发布约束

- 不要把密码、Token、`~/.config/gh/hosts.yml` 或含凭据的 SSH 配置提交到仓库。
- `github_append.py` 使用 GitHub Contents API 的当前 SHA，PUT 后输出 commit SHA；发布前后应保留 API 回读结果。
- 发布目标必须显式指定，例如 `--path gm_jp.txt`；不会修改 `ip.txt` 或 `sb.txt`。
- 大范围扫描应使用独立 `WORKDIR`、日志、锁和完成标记，禁止多个 masscan 写同一个结果文件。
- 大规模任务建议使用 `nohup` 或 systemd/cron，并通过 `run.log` 的终态标记判断完成，而不是根据 SSH 会话是否退出判断。

# OpenWrt 部署说明

这套程序在 OpenWrt 上按原生 Python 方式运行，不需要交叉编译。

## 支持条件

- OpenWrt 22.03/23.05/24.10（建议 64 MB 以上可用内存）
- 已启用官方软件源
- 建议使用 extroot 或 USB 存储，将程序放在 `/opt/cfnb`
- 需要 Python 3、requests、aiohttp、curl 和 CA 证书

## 安装

把完整项目目录上传到路由器后执行：

```sh
cd /tmp/cfnb
sh openwrt/install.sh
```

安装脚本会：

1. 使用 `opkg` 安装运行依赖；
2. 安装到 `/opt/cfnb`；
3. 安装 `/etc/init.d/cfnb`；
4. 写入每 5 分钟执行的 OpenWrt cron；
5. 创建 `/var/log/cfnb/cron.log`。

## 配置

编辑：

```text
/opt/cfnb/config.json
```

建议在 OpenWrt 上降低并发，避免占满路由器资源：

```json
{
  "MAX_WORKERS": 32,
  "AVAILABILITY_WORKERS": 8,
  "HTTP_TEST_WORKERS": 8,
  "BANDWIDTH_WORKERS": 1,
  "BANDWIDTH_CANDIDATES": 30
}
```

如果不需要 Cloudflare DNS 更新，设置：

```json
"CF_ENABLED": false
```

## 管理

```sh
/etc/init.d/cfnb start
/etc/init.d/cfnb stop
/etc/init.d/cfnb restart
/etc/init.d/cfnb enable
logread -f
 tail -f /var/log/cfnb/cron.log
```

## 注意

OpenWrt 通常没有 systemd、完整 pip 或 Docker，因此不要运行原来的 `setup.sh`。使用本目录的 `install.sh`。如果固件软件源没有 `python3-aiohttp`，需要换用带 Python 包的固件源或在外部构建对应 OpenWrt package；程序不会假装以缺少依赖的状态运行。

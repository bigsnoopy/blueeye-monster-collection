# ZipForge · 无广告 · 本地优先的压缩软件

> 子项目归属：本目录为 [blueeye-monster](https://github.com/bigsnoopy/blueeye-monster-collection) 整理/改造。
> 开源合规声明见仓库根目录 **NOTICE** 与 **LICENSE**。

## 这是什么

ZipForge 是一个用 Python + tkinter 编写的**开源压缩软件图形外壳**，底层调用
[mcmilk/7-Zip-zstd](https://github.com/mcmilk/7-Zip-zstd) 的预编译 7z 引擎（LGPL-2.1+ / BSD）。
它把官方 7-Zip 没有、但越来越常用的现代压缩格式带到桌面 GUI 里。

### 与官方 7-Zip 的核心差异

| 能力 | 官方 7-Zip | ZipForge |
|---|---|---|
| zstd (.zst) 压缩/解压 | ❌ | ✅ |
| brotli (.br) | ❌ | ✅ |
| lz4 (.lz4) | ❌ | ✅ |
| 无广告 / 无推广弹窗 | ❌（安装器有捆绑） | ✅ |
| 本地优先，无联网上报 | ⚠️ | ✅ |

> RAR 格式**仅作只读解压**，未启用 RAR 创建，以规避 unRAR 许可限制。

## 目录结构

```
zipforge/
├── zipforge.py              # 程序入口
├── 运行说明.txt             # 详细使用说明（中文）
├── src/                     # 全部 Python 源码（gui / engine / cli 等）
├── assets/                  # 图标资源
├── tools/                   # QA 测试脚本
├── vendor/
│   └── engine-x64/          # 7-Zip-ZS 引擎（7z.exe / 7z.dll）+ 7ZIP-ZS-LICENSE.txt
├── ZipForge.spec            # PyInstaller 打包配置
└── build_exe.bat            # 一键打包成 exe
```

## 如何运行（源码模式）

```bash
pip install tkinter  # Windows 自带；Linux/macOS 需自行安装
python zipforge.py
```

程序会自动在 `vendor/engine-x64/` 定位 7z 引擎；若未找到，也可使用系统已安装的官方 7-Zip。

## 如何打包成 exe

```bash
build_exe.bat
```

## 许可证与署名（重要）

- **ZipForge 自研代码**：MIT，版权归 blueeye-monster（详见仓库根 LICENSE）。
- **7-Zip-ZS 引擎**：LGPL-2.1-or-later / BSD-3-Clause，版权归 Igor Pavlov、Tino Reichardt 等原作者。
- **PeaZip / NanaZip**：仅 GUI 与交互设计参考，未复制代码（分别 LGPL-3.0 / MIT）。
- 本软件**仅供学习交流，不售卖**。所有第三方权利归原作者，使用须遵守其各自许可证。

完整第三方致谢与源码获取链接见仓库根目录 **NOTICE**。

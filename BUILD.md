# Codex-DS 桌面版构建指南

## 环境要求（在你的 Mac 上）

- macOS 12+（Monterey 或更新版本）
- Xcode 15+（从 App Store 安装，或 `xcode-select --install`）
- Rust 工具链
- Node.js 18+

## 第一步：安装前提工具

### 1. Xcode Command Line Tools

```bash
xcode-select --install
```

### 2. 安装 Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
rustc --version   # 应显示 1.70+
cargo --version
```

**国内加速：** 创建 `~/.cargo/config.toml`：
```toml
[source.crates-io]
replace-with = "tuna"

[source.tuna]
registry = "https://mirrors.tuna.tsinghua.edu.cn/git/crates.io-index.git"
```

### 3. Node.js

从 https://nodejs.org 下载 v18+ 或通过 Homebrew 安装：
```bash
brew install node
node --version   # 应显示 v18+
```

**国内加速：**
```bash
npm config set registry https://registry.npmmirror.com
```

## 第二步：构建

```bash
# 1. 进入项目
cd codex-ds

# 2. 安装前端依赖
make desktop-setup

# 3. 构建（推荐 -- 仅 .app，不会报 bundle_dmg.sh 错误）
make desktop-build-app

# .app 文件在：
# desktop-app/src-tauri/target/release/bundle/macos/Codex-DS 代理.app
```

或者构建完整 .dmg：
```bash
make desktop-build
```

## 安装

- **.app 方式**：直接把 `Codex-DS 代理.app` 拖入 Applications 文件夹
- **.dmg 方式**：双击打开 → 拖入 Applications

首次打开未签名应用：**右键点击 → 打开**，然后确认「仍要打开」。

## 开发模式

```bash
make desktop-dev
```

窗口打开后按 `Cmd+Option+I` 打开 DevTools 查看控制台错误。

## 常见问题

### bundle_dmg.sh 错误

AppleScript 在 macOS 安全限制下可能失败。使用 `make desktop-build-app` 跳过 dmg 构建，只生成 .app。

### 应用白屏/卡加载中

1. 按 `Cmd+Option+I` 打开 DevTools 查看错误
2. 清理旧缓存并重新编译：
   ```bash
   rm -rf ~/Library/Application\ Support/com.codex-ds.proxy
   make desktop-build-app
   ```

### 代理启动失败 "unrecognized arguments: --no-browser"

旧版脚本缓存导致。先清理缓存再重新编译：
```bash
rm -rf ~/Library/Application\ Support/com.codex-ds.proxy/proxy
make desktop-build-app
```

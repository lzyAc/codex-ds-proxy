use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::process::Command;
use tokio::sync::broadcast;

use crate::AppState;

static PROXY_RUNNING: AtomicBool = AtomicBool::new(false);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyStatus {
    pub running: bool,
    pub port: u16,
    pub uptime_seconds: u64,
    pub total_requests: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogEntry {
    pub time: String,
    pub message: String,
    pub level: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyLogResponse {
    pub logs: Vec<LogEntry>,
}

// ── 启动代理 ──

#[tauri::command]
pub async fn start_proxy(
    app_handle: AppHandle,
    state: State<'_, AppState>,
    api_key: String,
    port: Option<u16>,
) -> Result<String, String> {
    if PROXY_RUNNING.load(Ordering::SeqCst) {
        return Err("代理已在运行中".into());
    }

    let proxy_port = port.unwrap_or(8787);
    let python_path = find_python();

    // 生成临时 config.json（与 config_manager.py 的格式一致）
    let config_dir = app_handle
        .path()
        .app_config_dir()
        .map_err(|e| e.to_string())?;
    std::fs::create_dir_all(&config_dir).ok();
    let config = serde_json::json!({
        "provider": "deepseek",
        "deepseek_api_key": api_key,
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-v4-pro",
        "proxy_host": "127.0.0.1",
        "proxy_port": proxy_port,
        "auto_start": false,
        "model_mapping": {
            "claude-opus-4.6": "deepseek-v4-pro",
            "claude-opus-4.6-1m": "deepseek-v4-pro",
            "claude-haiku-4.6": "deepseek-v4-flash",
            "gpt-5.5": "deepseek-v4-pro"
        },
        "providers": {
            "deepseek": {
                "name": "DeepSeek",
                "api_key": api_key,
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-pro"
            }
        },
        "available_models": [
            {"id": "deepseek-v4-pro", "name": "DeepSeek V4 Pro"},
            {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash"},
            {"id": "deepseek-chat", "name": "DeepSeek Chat (V3)"},
            {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (R1)"}
        ]
    });
    let config_path = config_dir.join("config.json");
    std::fs::write(
        &config_path,
        serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;

    // 找到代理 python 脚本
    let proxy_script = find_proxy_script(&app_handle)?;

    // 启动 Python 代理进程（设置工作目录为脚本所在目录）
    let proxy_dir = std::path::Path::new(&proxy_script)
        .parent()
        .unwrap_or(std::path::Path::new("."))
        .to_path_buf();
    let mut child = Command::new(&python_path)
        .arg(&proxy_script)
        .arg("--no-tray")
        .arg("--proxy-port")
        .arg(proxy_port.to_string())
        .current_dir(&proxy_dir)
        .env("HOME", std::env::var("HOME").unwrap_or_default())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("启动代理失败: {}", e))?;

    PROXY_RUNNING.store(true, Ordering::SeqCst);

    // 更新状态
    {
        let mut running = state.proxy_running.lock().map_err(|e| e.to_string())?;
        *running = true;
    }

    // 启动后台任务监控代理进程
    let (tx, _) = broadcast::channel::<()>(1);
    {
        let mut stop_tx = state.proxy_stop_tx.lock().map_err(|e| e.to_string())?;
        *stop_tx = Some(tx.clone());
    }

    let app_clone = app_handle.clone();
    tauri::async_runtime::spawn(async move {
        let status = child.wait().await;
        PROXY_RUNNING.store(false, Ordering::SeqCst);
        let _ = tx.send(());
        let _ = app_clone.emit("proxy-stopped", serde_json::json!({
            "code": status.map(|s| s.code().unwrap_or(-1)).unwrap_or(-1)
        }));
    });

    // 等待代理就绪
    wait_for_proxy(proxy_port).await;

    let _ = app_handle.emit("proxy-started", serde_json::json!({
        "port": proxy_port
    }));

    Ok(format!("代理已启动，端口: {}", proxy_port))
}

// ── 停止代理 ──

#[tauri::command]
pub async fn stop_proxy(state: State<'_, AppState>) -> Result<String, String> {
    if !PROXY_RUNNING.load(Ordering::SeqCst) {
        return Err("代理未在运行".into());
    }

    let stop_tx = {
        let mut tx = state.proxy_stop_tx.lock().map_err(|e| e.to_string())?;
        tx.take()
    };

    if let Some(tx) = stop_tx {
        let _ = tx.send(());
    }

    // 尝试优雅关闭
    let client = reqwest::Client::new();
    let _ = client
        .post("http://127.0.0.1:8788/api/proxy/stop")
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await;

    PROXY_RUNNING.store(false, Ordering::SeqCst);
    {
        let mut running = state.proxy_running.lock().map_err(|e| e.to_string())?;
        *running = false;
    }

    Ok("代理已停止".into())
}

// ── 状态查询 ──

#[tauri::command]
pub async fn get_proxy_status() -> Result<ProxyStatus, String> {
    let running = PROXY_RUNNING.load(Ordering::SeqCst);
    if running {
        // 从 Web UI 获取状态
        let client = reqwest::Client::new();
        let resp = client
            .get("http://127.0.0.1:8788/api/proxy/status")
            .timeout(std::time::Duration::from_secs(2))
            .send()
            .await;

        match resp {
            Ok(r) if r.status().is_success() => {
                let data: serde_json::Value = r.json().await.unwrap_or_default();
                Ok(ProxyStatus {
                    running: true,
                    port: 8787,
                    uptime_seconds: data["uptime_seconds"].as_u64().unwrap_or(0),
                    total_requests: data["total_requests"].as_u64().unwrap_or(0),
                })
            }
            _ => Ok(ProxyStatus {
                running: true,
                port: 8787,
                uptime_seconds: 0,
                total_requests: 0,
            }),
        }
    } else {
        Ok(ProxyStatus {
            running: false,
            port: 8787,
            uptime_seconds: 0,
            total_requests: 0,
        })
    }
}

// ── 日志查询 ──

#[tauri::command]
pub async fn get_logs(limit: Option<u32>) -> Result<ProxyLogResponse, String> {
    let client = reqwest::Client::new();
    let limit = limit.unwrap_or(50);
    let resp = client
        .get(format!("http://127.0.0.1:8788/api/logs?limit={}", limit))
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
        .map_err(|e| format!("获取日志失败: {}", e))?;

    let data: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
    let logs: Vec<LogEntry> = data["logs"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .map(|v| LogEntry {
                    time: v["time"].as_str().unwrap_or("").to_string(),
                    message: format!(
                        "{} → {}",
                        v["model_original"].as_str().unwrap_or("?"),
                        v["model_mapped"].as_str().unwrap_or("?")
                    ),
                    level: match v["status"].as_str() {
                        Some("error") => "error".into(),
                        _ => "info".into(),
                    },
                })
                .collect()
        })
        .unwrap_or_default();

    Ok(ProxyLogResponse { logs })
}

// ── API Key 检查 ──

#[tauri::command]
pub async fn check_api_key(key: String) -> Result<bool, String> {
    let client = reqwest::Client::new();
    let resp = client
        .post("https://api.deepseek.com/v1/chat/completions")
        .header("Authorization", format!("Bearer {}", key))
        .json(&serde_json::json!({
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": "test"}],
            "max_tokens": 1
        }))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("API 测试失败: {}", e))?;

    Ok(resp.status().is_success())
}

// ── 系统托盘事件 ──

pub fn handle_tray_event(
    tray: &tauri::tray::TrayIcon,
    event: tauri::tray::TrayIconEvent,
) {
    use tauri::tray::MouseButton;
    use tauri::tray::MouseButtonState;

    if let tauri::tray::TrayIconEvent::Click {
        button: MouseButton::Left,
        button_state: MouseButtonState::Up,
        ..
    } = event
    {
        if let Some(window) = tray.app_handle().get_webview_window("main") {
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

// ── 辅助函数 ──

fn find_python() -> String {
    for name in &["python3", "python"] {
        let output = std::process::Command::new(name)
            .arg("--version")
            .output();
        if output.is_ok() {
            return name.to_string();
        }
    }
    "python3".to_string()
}

fn find_proxy_script(app_handle: &AppHandle) -> Result<String, String> {
    // 1. Tauri resource 目录（bundle 后文件直接展平在资源根目录）
    let resource_dir = app_handle
        .path()
        .resource_dir()
        .map_err(|e| e.to_string())?;

    // 尝试多种路径：直接 app.py / proxy/app.py / resources/app.py
    let candidates = &[
        resource_dir.join("app.py"),              // 展平在资源根目录
        resource_dir.join("proxy").join("app.py"), // proxy 子目录
        resource_dir.join("resources").join("app.py"), // resources 子目录
    ];
    for c in candidates {
        if c.exists() {
            return Ok(c.to_string_lossy().to_string());
        }
    }

    // 2. 可执行文件同级目录（开发环境，target/release/ 下）
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            let manual = [
                parent.join("proxy").join("app.py"),
                parent.join("../../../proxy/app.py"),
            ];
            for c in &manual {
                if c.exists() {
                    return Ok(c.to_string_lossy().to_string());
                }
            }
        }
    }

    // 3. 从源码根目录查找（开发模式：desktop-app/ 下）
    let dev_paths = [
        "../app.py",                      // 从 src-tauri/ 到 desktop-app/
        "../../app.py",                   // 到 codex-ds 根目录
    ];
    for p in &dev_paths {
        let pp = std::path::Path::new(p);
        if pp.exists() {
            return Ok(pp.canonicalize().unwrap_or(pp.to_path_buf()).to_string_lossy().to_string());
        }
    }

    Err(format!("找不到代理脚本 app.py\n请确保:\n1. Python 已安装 (python3 --version)\n2. 应用安装包完整\n3. 或手动启动: cd codex-ds && python3 app.py\n\n查找路径:\n  resource_dir={:?}\n  exe_dir={:?}",
        resource_dir,
        std::env::current_exe().map(|e| e.to_string()).unwrap_or_default()))
}

async fn wait_for_proxy(port: u16) {
    let client = reqwest::Client::new();
    for _ in 0..30 {
        let resp = client
            .get(format!("http://127.0.0.1:{}/health", port))
            .timeout(std::time::Duration::from_secs(1))
            .send()
            .await;
        if resp.is_ok() {
            return;
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
}

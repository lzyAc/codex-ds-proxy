use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, Ordering};
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

    // 1. 部署 Python 代理到应用数据目录
    let proxy_dir = deploy_proxy_scripts(&app_handle)?;

    // 2. 生成 config.json
    let config_dir = app_handle
        .path()
        .app_config_dir()
        .map_err(|e| format!("获取配置目录失败: {}", e))?;
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
    .map_err(|e| format!("保存配置失败: {}", e))?;

    // 3. 启动 Python 代理
    let python_path = find_python();
    let app_script = proxy_dir.join("app.py");

    if !app_script.exists() {
        return Err(format!(
            "启动失败：找不到代理脚本\n\
             ----------------------------------------\n\
             已部署目录: {}\n\
             请尝试重新安装本应用",
            proxy_dir.display()
        ));
    }

    let mut child = Command::new(&python_path)
        .arg(app_script.to_string_lossy().to_string())
        .arg("--no-tray")
        .arg("--proxy-port")
        .arg(proxy_port.to_string())
        .current_dir(&proxy_dir)
        .env("HOME", std::env::var("HOME").unwrap_or_default())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("启动代理失败: {}\n请确保已安装 Python：python3 --version", e))?;

    PROXY_RUNNING.store(true, Ordering::SeqCst);
    {
        let mut running = state.proxy_running.lock().map_err(|e| e.to_string())?;
        *running = true;
    }

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

    wait_for_proxy(proxy_port).await;
    let _ = app_handle.emit("proxy-started", serde_json::json!({"port": proxy_port}));

    Ok(format!("代理已启动，端口: {}", proxy_port))
}

// ── 部署代理脚本 ──

fn deploy_proxy_scripts(app_handle: &AppHandle) -> Result<std::path::PathBuf, String> {
    let data_dir = app_handle.path().app_data_dir().map_err(|e| e.to_string())?;
    let proxy_dir = data_dir.join("proxy");

    // 已经部署过，直接返回
    if proxy_dir.join("app.py").exists() {
        return Ok(proxy_dir);
    }

    // 编译时嵌入的 Python 脚本（通过 include_str!）
    // 这些文件在编译时被嵌入到二进制中，运行时写出
    static EMBEDDED_FILES: &[(&str, &str)] = &[
        ("app.py", include_str!("../../proxy/app.py")),
        ("proxy.py", include_str!("../../proxy/proxy.py")),
        ("config_manager.py", include_str!("../../proxy/config_manager.py")),
        ("web_ui.py", include_str!("../../proxy/web_ui.py")),
        ("anthropic_adapter.py", include_str!("../../proxy/anthropic_adapter.py")),
        ("providers/__init__.py", include_str!("../../proxy/providers/__init__.py")),
        ("providers/base.py", include_str!("../../proxy/providers/base.py")),
        ("providers/deepseek.py", include_str!("../../proxy/providers/deepseek.py")),
        ("templates/index.html", include_str!("../../proxy/templates/index.html")),
        ("static/css/style.css", include_str!("../../proxy/static/css/style.css")),
        ("static/js/app.js", include_str!("../../proxy/static/js/app.js")),
    ];

    // 写出所有嵌入的文件
    for (rel_path, content) in EMBEDDED_FILES {
        let full_path = proxy_dir.join(rel_path);
        if let Some(parent) = full_path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("创建目录失败 {}: {}", parent.display(), e))?;
        }
        std::fs::write(&full_path, content).map_err(|e| format!("写入文件失败 {}: {}", full_path.display(), e))?;
    }

    if proxy_dir.join("app.py").exists() {
        Ok(proxy_dir)
    } else {
        Err("部署代理脚本失败，请重新安装本应用".into())
    }
}

fn copy_dir_recursive(src: &std::path::Path, dst: &std::path::Path) -> Result<(), String> {
    fn copy_dir(src: &std::path::Path, dst: &std::path::Path) -> std::io::Result<()> {
        if !dst.exists() {
            std::fs::create_dir_all(dst)?;
        }
        for entry in std::fs::read_dir(src)? {
            let entry = entry?;
            let src_path = entry.path();
            let dst_path = dst.join(entry.file_name());
            if src_path.is_dir() {
                copy_dir(&src_path, &dst_path)?;
            } else {
                std::fs::copy(&src_path, &dst_path)?;
            }
        }
        Ok(())
    }
    copy_dir(src, dst).map_err(|e| format!("复制代理文件失败: {}", e))
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

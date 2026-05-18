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

    // 0. 检查端口是否被占用
    if is_port_in_use(proxy_port).await {
        return Err(format!(
            "端口 {} 已被占用，请检查：\n\
             1. 是否有终端在运行 python3 app.py 或 make start\n\
             2. 是否已经打开了一个桌面版\n\
             3. 在终端执行 lsof -i :{} 查看占用进程",
            proxy_port, proxy_port
        ));
    }

    // 1. 部署 Python 代理
    let proxy_dir = deploy_proxy_scripts(&app_handle)?;
    let app_script = proxy_dir.join("app.py");
    if !app_script.exists() {
        return Err(format!("找不到代理脚本，请重新安装应用\n路径: {}", proxy_dir.display()));
    }

    // 2. 准备日志目录
    let data_dir = app_handle.path().app_data_dir().map_err(|e| e.to_string())?;
    let log_dir = data_dir.join("logs");
    std::fs::create_dir_all(&log_dir).ok();
    let proxy_log_path = log_dir.join("proxy.log");
    let config_dir = app_handle.path().app_config_dir().map_err(|e| e.to_string())?;

    // 3. 写入启动日志
    use std::io::Write;
    let mut log_file = std::fs::OpenOptions::new()
        .create(true).append(true).open(&proxy_log_path)
        .map_err(|e| format!("创建日志文件失败: {}", e))?;
    writeln!(log_file, "\n=== {} 启动 ===", chrono::Local::now().format("%Y-%m-%d %H:%M:%S"))
        .ok();

    // 4. 生成 config.json
    std::fs::create_dir_all(&config_dir).ok();
    let config = serde_json::json!({
        "provider": "deepseek",
        "deepseek_api_key": api_key,
        "proxy_port": proxy_port,
        "model_mapping": {
            "claude-opus-4.6": "deepseek-v4-pro",
            "claude-opus-4.6-1m": "deepseek-v4-pro",
            "claude-haiku-4.6": "deepseek-v4-flash",
            "gpt-5.5": "deepseek-v4-pro"
        }
    });
    let config_path = config_dir.join("config.json");
    std::fs::write(&config_path, serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?)
        .map_err(|e| format!("保存配置失败: {}", e))?;

    // 5. 启动 Python 代理
    let python_path = find_python();
    let mut child = Command::new(&python_path)
        .arg(app_script.to_string_lossy().to_string())
        .arg("--no-tray")
        .arg("--proxy-port")
        .arg(proxy_port.to_string())
        .current_dir(&proxy_dir)
        .env("HOME", std::env::var("HOME").unwrap_or_default())
        .stderr(std::process::Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("启动失败: {}\n请确保已安装 Python (python3 --version)", e))?;

    // 写 PID
    writeln!(log_file, "PID: {:?}", child.id()).ok();

    // 6. 等待一小段时间，检查进程是否存活，并收集启动日志
    tokio::time::sleep(std::time::Duration::from_millis(1500)).await;

    // 读 stderr（Python 的启动日志输出到这里）
    let mut startup_logs = String::new();
    if let Some(stderr) = child.stderr.take() {
        use tokio::io::AsyncBufReadExt;
        let mut reader = tokio::io::BufReader::new(stderr).lines();
        let mut count = 0;
        while let Ok(Some(line)) = reader.next_line().await {
            if count < 30 {
                startup_logs.push_str(&line);
                startup_logs.push('\n');
            }
            writeln!(log_file, "  {}", line).ok();
            count += 1;
        }
    }

    // 7. 检查进程是否还在运行
    let is_alive = child.try_wait().ok().flatten().is_none();
    if !is_alive {
        let exit_code = child.wait().await.ok().and_then(|s| s.code()).unwrap_or(-1);
        PROXY_RUNNING.store(false, Ordering::SeqCst);
        let err_msg = format!(
            "代理进程意外退出 (代码: {})\n\n--- 启动日志 ---\n{}",
            exit_code, startup_logs
        );
        writeln!(log_file, "进程退出, 代码: {}", exit_code).ok();
        return Err(err_msg);
    }

    // 8. 标记为运行中
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

    // 后台：等进程退出
    let app_clone = app_handle.clone();
    let log_path = proxy_log_path.clone();
    tauri::async_runtime::spawn(async move {
        let status = child.wait().await;
        let exit_code = status.as_ref().ok().and_then(|s| s.code()).unwrap_or(-1);
        PROXY_RUNNING.store(false, Ordering::SeqCst);
        let _ = tx.send(());
        if let Ok(mut lf) = std::fs::OpenOptions::new().create(true).append(true).open(&log_path) {
            let _ = writeln!(lf, "进程退出, 代码: {}", exit_code);
        }
        let _ = app_clone.emit("proxy-stopped", serde_json::json!({"code": exit_code}));
    });

    // 9. 等待 health endpoint 就绪
    let ready = wait_for_proxy(proxy_port).await;
    let _ = app_handle.emit("proxy-started", serde_json::json!({"port": proxy_port}));

    if ready {
        Ok(format!(
            "代理已启动 (端口 {})\n\n启动日志路径:\n{}",
            proxy_port, proxy_log_path.display()
        ))
    } else {
        Ok(format!(
            "代理进程已启动，但 health check 超时。\n可能仍在启动中，可查看日志:\n{}",
            proxy_log_path.display()
        ))
    }
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

// ── 端口检测 ──

async fn is_port_in_use(port: u16) -> bool {
    reqwest::Client::new()
        .get(format!("http://127.0.0.1:{}/health", port))
        .timeout(std::time::Duration::from_secs(1))
        .send()
        .await
        .is_ok()
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

async fn wait_for_proxy(port: u16) -> bool {
    let client = reqwest::Client::new();
    for _ in 0..10 {
        let resp = client
            .get(format!("http://127.0.0.1:{}/health", port))
            .timeout(std::time::Duration::from_secs(1))
            .send()
            .await;
        if resp.is_ok() {
            return true;
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
    false
}

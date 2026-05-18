use serde::{Deserialize, Serialize};
use std::io::Write;
use std::sync::atomic::{AtomicBool, AtomicU16, AtomicU64, Ordering};
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::process::Command;
use tokio::sync::broadcast;

use crate::AppState;

static PROXY_RUNNING: AtomicBool = AtomicBool::new(false);
static PROXY_STOPPING: AtomicBool = AtomicBool::new(false);
static PROXY_PORT: AtomicU16 = AtomicU16::new(8787);
static PROXY_START_TIME: AtomicU64 = AtomicU64::new(0);
static PROXY_TOTAL_REQUESTS: AtomicU64 = AtomicU64::new(0);

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
    let web_port = 8788;

    // 准备日志目录
    let data_dir = app_handle.path().app_data_dir().map_err(|e| e.to_string())?;
    let log_dir = data_dir.join("logs");
    std::fs::create_dir_all(&log_dir).ok();
    let proxy_log_path = log_dir.join("proxy.log");
    let config_dir = app_handle.path().app_config_dir().map_err(|e| e.to_string())?;

    // 打开日志文件
    let mut log_file = std::fs::OpenOptions::new()
        .create(true).append(true).open(&proxy_log_path)
        .map_err(|e| format!("创建日志文件失败: {}", e))?;
    writeln!(log_file, "\n=== {} 启动 ===", chrono::Local::now().format("%Y-%m-%d %H:%M:%S"))
        .ok();

    // 如果端口已被占用，说明已有外部代理在运行，直接复用
    if is_port_in_use(proxy_port).await {
        writeln!(log_file, "检测到端口 {} 已有代理在运行，直接复用", proxy_port).ok();
        PROXY_RUNNING.store(true, Ordering::SeqCst);
        PROXY_PORT.store(proxy_port, Ordering::SeqCst);
        PROXY_START_TIME.store(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs(),
            Ordering::SeqCst,
        );
        PROXY_TOTAL_REQUESTS.store(0, Ordering::SeqCst);
        {
            let mut running = state.proxy_running.lock().map_err(|e| e.to_string())?;
            *running = true;
        }
        let _ = app_handle.emit("proxy-started", serde_json::json!({"port": proxy_port}));
        return Ok(format!("代理已存在 (端口 {})", proxy_port));
    }

    // 部署 Python 代理
    let proxy_dir = deploy_proxy_scripts(&app_handle)?;
    let app_script = proxy_dir.join("app.py");
    if !app_script.exists() {
        return Err(format!("找不到代理脚本，请重新安装应用\n路径: {}", proxy_dir.display()));
    }

    // 生成 config.json
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

    // 检查 Python 和依赖
    let python_path = find_python();
    writeln!(log_file, "检查 Python 依赖...").ok();

    let check_tornado = Command::new(&python_path)
        .args(&["-c", "import tornado; print(tornado.version)"])
        .output()
        .await;

    match check_tornado {
        Ok(output) if output.status.success() => {
            let ver = String::from_utf8_lossy(&output.stdout).trim().to_string();
            writeln!(log_file, "Tornado 已安装 (v{})", ver).ok();
        }
        _ => {
            writeln!(log_file, "安装 tornado/requests...").ok();
            let pip_result = Command::new(&python_path)
                .args(&["-m", "pip", "install", "tornado", "requests", "--quiet", "--break-system-packages"])
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::piped())
                .output()
                .await;
            match pip_result {
                Ok(output) if output.status.success() => {
                    writeln!(log_file, "依赖安装成功").ok();
                }
                Ok(output) => {
                    let err = String::from_utf8_lossy(&output.stderr);
                    writeln!(log_file, "pip 安装失败: {}", err).ok();
                    return Err(format!(
                        "Python 依赖安装失败\npip stderr: {}\n\n可手动执行:\n{} -m pip install tornado requests --break-system-packages",
                        err, python_path
                    ));
                }
                Err(e) => {
                    writeln!(log_file, "pip 执行失败: {}", e).ok();
                    return Err(format!("pip 命令执行失败: {}", e));
                }
            }
        }
    }

    // 启动 Python 代理
    writeln!(log_file, "启动 Python 代理...").ok();
    let mut child = Command::new(&python_path)
        .arg(app_script.to_string_lossy().to_string())
        .arg("--no-tray")
        .arg("--no-browser")
        .arg("--proxy-port")
        .arg(proxy_port.to_string())
        .current_dir(&proxy_dir)
        .env("HOME", std::env::var("HOME").unwrap_or_default())
        // 不接管 stdout/stderr，让 Python 进程自由输出
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| format!("启动失败: {}\n请确保已安装 Python (python3 --version)", e))?;

    writeln!(log_file, "PID: {:?}", child.id()).ok();

    // 等待进程启动
    tokio::time::sleep(std::time::Duration::from_millis(2000)).await;

    // 检查进程是否还在运行
    let is_alive = child.try_wait().ok().flatten().is_none();
    if !is_alive {
        let exit_code = child.wait().await.ok().and_then(|s| s.code()).unwrap_or(-1);
        let err_msg = format!("代理进程意外退出 (代码: {})", exit_code);
        writeln!(log_file, "进程退出, 代码: {}", exit_code).ok();
        return Err(err_msg);
    }

    // 标记为运行中
    PROXY_RUNNING.store(true, Ordering::SeqCst);
    PROXY_PORT.store(proxy_port, Ordering::SeqCst);
    PROXY_START_TIME.store(
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
        Ordering::SeqCst,
    );
    PROXY_TOTAL_REQUESTS.store(0, Ordering::SeqCst);
    {
        let mut running = state.proxy_running.lock().map_err(|e| e.to_string())?;
        *running = true;
    }

    let (tx, _) = broadcast::channel::<()>(1);
    {
        let mut stop_tx = state.proxy_stop_tx.lock().map_err(|e| e.to_string())?;
        *stop_tx = Some(tx.clone());
    }

    // 后台：等进程退出（只 emit 事件，不设置状态 — 状态由 stop_proxy 管理）
    let app_clone = app_handle.clone();
    let log_path = proxy_log_path.clone();
    tauri::async_runtime::spawn(async move {
        let status = child.wait().await;
        let exit_code = status.as_ref().ok().and_then(|s| s.code()).unwrap_or(-1);
        if let Ok(mut lf) = std::fs::OpenOptions::new().create(true).append(true).open(&log_path) {
            let _ = writeln!(lf, "进程退出, 代码: {}", exit_code);
        }
        // 只要进程真的退出了（不是因为崩溃重启），才 emit
        // stop_proxy 已经在 kill 后设好了状态，
        // 这个分支只有在进程意外崩溃或 stop_proxy 的 kill 导致 wait 返回时才会走到
        let _ = app_clone.emit("proxy-stopped", serde_json::json!({"code": exit_code}));
    });

    // 等待 health endpoint 就绪
    let ready = wait_for_proxy(proxy_port).await;
    let _ = app_handle.emit("proxy-started", serde_json::json!({"port": proxy_port}));

    if ready {
        Ok(format!("代理已启动 (端口 {})", proxy_port))
    } else {
        Ok("代理进程已启动".into())
    }
}

// ── 部署代理脚本 ──

fn deploy_proxy_scripts(app_handle: &AppHandle) -> Result<std::path::PathBuf, String> {
    let data_dir = app_handle.path().app_data_dir().map_err(|e| e.to_string())?;
    let proxy_dir = data_dir.join("proxy");

    // 编译时嵌入的 Python 脚本（通过 include_str!）
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

    for (rel_path, content) in EMBEDDED_FILES {
        let full_path = proxy_dir.join(rel_path);
        if let Some(parent) = full_path.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("创建目录失败 {}: {}", parent.display(), e))?;
        }
        // 总是覆盖写出，确保脚本是最新版本
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

    // 设置 stopping 标志（get_proxy_status 会检查此标志，返回 running=false）
    PROXY_STOPPING.store(true, Ordering::SeqCst);

    // 先通知 Rust 侧的监控线程（如果有），避免重复状态重置
    let stop_tx = {
        let mut tx = state.proxy_stop_tx.lock().map_err(|e| e.to_string())?;
        tx.take()
    };
    if let Some(tx) = stop_tx {
        let _ = tx.send(());
    }

    // 实际 kill Python 进程：通过 pkill 杀掉所有 python3 的 app.py 实例
    let port = PROXY_PORT.load(Ordering::SeqCst);
    let _ = Command::new("sh")
        .args(&["-c", &format!("pkill -f 'python3.*app.py' 2>/dev/null; pkill -f 'python.*app.py' 2>/dev/null")])
        .output()
        .await;

    // 再 kill 端口上的进程，确保清理干净
    for p in [port, 8788] {
        let _ = Command::new("sh")
            .args(&["-c", &format!("lsof -ti :{} | xargs kill -9 2>/dev/null", p)])
            .output()
            .await;
    }

    // 等待进程真正退出
    tokio::time::sleep(std::time::Duration::from_millis(1500)).await;

    // 重置状态（后台监控线程可能因 wait() 返回而再次设置，但这里先设为主状态）
    PROXY_RUNNING.store(false, Ordering::SeqCst);
    PROXY_START_TIME.store(0, Ordering::SeqCst);
    PROXY_TOTAL_REQUESTS.store(0, Ordering::SeqCst);
    {
        let mut running = state.proxy_running.lock().map_err(|e| e.to_string())?;
        *running = false;
    }
    PROXY_STOPPING.store(false, Ordering::SeqCst);

    Ok("代理已停止".into())
}

// ── 状态查询 ──

#[tauri::command]
pub async fn get_proxy_status() -> Result<ProxyStatus, String> {
    let running = PROXY_RUNNING.load(Ordering::SeqCst);
    let stopping = PROXY_STOPPING.load(Ordering::SeqCst);
    let port = PROXY_PORT.load(Ordering::SeqCst);

    // 正在停止过程中 —— 直接返回未运行，不再检查 health
    if !running || stopping {
        return Ok(ProxyStatus { running: false, port, uptime_seconds: 0, total_requests: 0 });
    }

    // 计算运行时长
    let start_time = PROXY_START_TIME.load(Ordering::SeqCst);
    let uptime = if start_time > 0 {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        now.saturating_sub(start_time)
    } else {
        0
    };

    // 从 Python WebUI 获取总请求数
    let mut total_requests = PROXY_TOTAL_REQUESTS.load(Ordering::SeqCst);
    let client = reqwest::Client::new();
    if let Ok(resp) = client
        .get(format!("http://127.0.0.1:{}/api/proxy/status", 8788))
        .timeout(std::time::Duration::from_secs(2))
        .send()
        .await
    {
        if let Ok(data) = resp.json::<serde_json::Value>().await {
            if let Some(req_count) = data["total_requests"].as_u64() {
                total_requests = req_count;
                PROXY_TOTAL_REQUESTS.store(req_count, Ordering::SeqCst);
            }
        }
    }

    Ok(ProxyStatus { running: true, port, uptime_seconds: uptime, total_requests })
}

// ── 请求日志查询（直接解析 HTTP 响应体文本） ──

#[tauri::command]
pub async fn get_logs(limit: Option<u32>) -> Result<ProxyLogResponse, String> {
    let limit = limit.unwrap_or(100);
    let url = format!("http://127.0.0.1:8788/api/logs?limit={}", limit);

    // 直接发送 HTTP GET（等价于 curl）
    let client = reqwest::Client::new();
    let resp = client.get(&url)
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
        .map_err(|e| format!("curl失败: {}", e))?;

    // 读取响应体文本
    let body_text = resp.text().await.map_err(|e| format!("读响应失败: {}", e))?;

    // 解析 JSON
    let parsed: serde_json::Value = serde_json::from_str(&body_text)
        .map_err(|e| format!("JSON解析失败 (原始内容前200字: {}): {}", &body_text[..body_text.len().min(200)], e))?;

    // 提取 logs 数组
    let logs_arr = parsed.get("logs")
        .and_then(|v| v.as_array())
        .ok_or_else(|| format!("响应中没有 logs 数组 (原始内容: {})", &body_text[..body_text.len().min(200)]))?;

    let logs: Vec<LogEntry> = logs_arr.iter()
        .map(|v| LogEntry {
            time: v.get("time").and_then(|t| t.as_str()).unwrap_or("").to_string(),
            message: format!(
                "{} → {}",
                v.get("model_original").and_then(|t| t.as_str()).unwrap_or("?"),
                v.get("model_mapped").and_then(|t| t.as_str()).unwrap_or("?")
            ),
            level: match v.get("status").and_then(|s| s.as_str()) {
                Some("error") => "error".into(),
                _ => "info".into(),
            },
        })
        .collect();

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

// ── 获取运行日志（完整进程日志，用于调试） ──

#[tauri::command]
pub async fn get_run_logs(app_handle: AppHandle) -> Result<String, String> {
    let data_dir = app_handle.path().app_data_dir().map_err(|e| e.to_string())?;
    let log_path = data_dir.join("logs").join("proxy.log");
    if log_path.exists() {
        std::fs::read_to_string(&log_path).map_err(|e| format!("读取日志失败: {}", e))
    } else {
        Ok("暂无运行日志".into())
    }
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
        if std::process::Command::new(name).arg("--version").output().is_ok() {
            return name.to_string();
        }
    }
    "python3".to_string()
}

async fn wait_for_proxy(port: u16) -> bool {
    let client = reqwest::Client::new();
    for _ in 0..20 {
        if client
            .get(format!("http://127.0.0.1:{}/health", port))
            .timeout(std::time::Duration::from_secs(1))
            .send()
            .await
            .is_ok()
        {
            return true;
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
    false
}

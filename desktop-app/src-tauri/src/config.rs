use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::Manager;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyConfig {
    pub api_key: String,
    pub proxy_port: u16,
    pub web_port: u16,
    pub auto_start: bool,
    pub dark_mode: bool,
    pub model_mapping: std::collections::HashMap<String, String>,
}

impl Default for ProxyConfig {
    fn default() -> Self {
        Self {
            api_key: String::new(),
            proxy_port: 8787,
            web_port: 8788,
            auto_start: true,
            dark_mode: true,
            model_mapping: {
                let mut m = std::collections::HashMap::new();
                m.insert("claude-opus-4.6".into(), "deepseek-v4-pro".into());
                m.insert("claude-opus-4.6-1m".into(), "deepseek-v4-pro".into());
                m.insert("claude-haiku-4.6".into(), "deepseek-v4-flash".into());
                m.insert("gpt-5.5".into(), "deepseek-v4-pro".into());
                m
            },
        }
    }
}

fn config_path(app_handle: &tauri::AppHandle) -> PathBuf {
    let app_dir = app_handle
        .path()
        .app_config_dir()
        .expect("failed to get app config dir");
    fs::create_dir_all(&app_dir).ok();
    app_dir.join("config.json")
}

#[tauri::command]
pub fn get_config(app_handle: tauri::AppHandle) -> Result<ProxyConfig, String> {
    let path = config_path(&app_handle);
    if path.exists() {
        let content = fs::read_to_string(&path).map_err(|e| e.to_string())?;
        serde_json::from_str(&content).map_err(|e| e.to_string())
    } else {
        let config = ProxyConfig::default();
        let content = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
        fs::write(&path, content).map_err(|e| e.to_string())?;
        Ok(config)
    }
}

#[tauri::command]
pub fn save_config(app_handle: tauri::AppHandle, config: ProxyConfig) -> Result<(), String> {
    let path = config_path(&app_handle);
    let content = serde_json::to_string_pretty(&config).map_err(|e| e.to_string())?;
    fs::write(&path, content).map_err(|e| e.to_string())?;
    Ok(())
}

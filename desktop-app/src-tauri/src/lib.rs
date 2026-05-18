use std::sync::Mutex;
use tauri::State;
use serde::{Deserialize, Serialize};
use tokio::process::Command;
use tokio::sync::broadcast;

mod proxy_manager;
mod config;

#[derive(Default)]
pub struct AppState {
    pub proxy_running: Mutex<bool>,
    pub proxy_stop_tx: Mutex<Option<broadcast::Sender<()>>>,
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            proxy_manager::start_proxy,
            proxy_manager::stop_proxy,
            proxy_manager::get_proxy_status,
            proxy_manager::get_logs,
            proxy_manager::check_api_key,
            config::get_config,
            config::save_config,
        ])
        .setup(|app| {
            #[cfg(all(desktop, not(target_os = "windows")))]
            {
                let handle = app.handle().clone();
                app.on_tray_icon_event(move |tray, event| {
                    proxy_manager::handle_tray_event(tray, event, &handle);
                });
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

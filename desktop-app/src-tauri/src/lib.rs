use std::sync::Mutex;
use tauri::Manager;
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
            // 系统托盘：点击图标显示窗口
            #[cfg(all(desktop, not(target_os = "windows")))]
            {
                app.on_tray_icon_event(|_tray_icon, event| {
                    if let Some(window) = _tray_icon.app_handle().get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                });
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

mod oauth_listener;

use oauth_listener::ListenerState;
use std::sync::Mutex;

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(Mutex::new(ListenerState::new()))
        .invoke_handler(tauri::generate_handler![
            greet,
            oauth_listener::start_oauth_callback_listener,
            oauth_listener::cancel_oauth_callback_listener
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

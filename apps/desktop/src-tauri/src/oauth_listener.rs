use serde::Serialize;
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, State};

const OAUTH_PORT: u16 = 8765;
const OAUTH_TIMEOUT_SEC: u64 = 600;

#[derive(Clone, Serialize)]
struct OAuthCallbackPayload {
    provider: String,
    code: Option<String>,
    state: Option<String>,
    error: Option<String>,
    error_description: Option<String>,
}

pub struct ListenerState {
    active: Arc<AtomicBool>,
    cancel: Arc<AtomicBool>,
}

impl ListenerState {
    pub fn new() -> Self {
        Self {
            active: Arc::new(AtomicBool::new(false)),
            cancel: Arc::new(AtomicBool::new(false)),
        }
    }
}

fn parse_query(query: &str) -> HashMap<String, String> {
    query
        .split('&')
        .filter_map(|pair| {
            let mut parts = pair.splitn(2, '=');
            let key = parts.next()?;
            let value = parts.next().unwrap_or("");
            let decoded = urlencoding::decode(value)
                .map(|cow| cow.into_owned())
                .unwrap_or_else(|_| value.to_string());
            Some((key.to_string(), decoded))
        })
        .collect()
}

fn expected_callback_path(provider: &str) -> String {
    format!("/oauth/{provider}/callback")
}

fn success_html() -> &'static str {
    r#"<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>PersonalOps</title></head>
<body style="font-family: system-ui, sans-serif; text-align: center; padding: 48px;">
  <h1>Sign-in successful</h1>
  <p>You can close this tab and return to PersonalOps.</p>
</body>
</html>"#
}

fn error_html(message: &str) -> String {
    format!(
        r#"<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>PersonalOps</title></head>
<body style="font-family: system-ui, sans-serif; text-align: center; padding: 48px;">
  <h1>Sign-in failed</h1>
  <p>{message}</p>
  <p>Return to PersonalOps and try again.</p>
</body>
</html>"#
    )
}

fn emit_oauth_result(app: &AppHandle, payload: OAuthCallbackPayload) {
    let _ = app.emit("oauth-callback", payload);
}

#[tauri::command]
pub fn start_oauth_callback_listener(
    app: AppHandle,
    provider: String,
    listener_state: State<'_, Mutex<ListenerState>>,
) -> Result<(), String> {
    let state = listener_state
        .lock()
        .map_err(|_| "OAuth listener state lock poisoned".to_string())?;
    let active = state.active.clone();
    let cancel = state.cancel.clone();
    drop(state);

    if active
        .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
        .is_err()
    {
        return Err(
            "OAuth listener is already active. Finish or cancel the current sign-in.".to_string(),
        );
    }

    cancel.store(false, Ordering::SeqCst);

    let expected_path = expected_callback_path(&provider);
    let app_handle = app.clone();
    let provider_for_thread = provider.clone();
    let active_for_thread = active.clone();
    let cancel_for_thread = cancel.clone();

    thread::spawn(move || {
        let _reset = ActiveGuard(active_for_thread);

        let server = match tiny_http::Server::http(format!("127.0.0.1:{OAUTH_PORT}")) {
            Ok(server) => server,
            Err(err) => {
                emit_oauth_result(
                    &app_handle,
                    OAuthCallbackPayload {
                        provider: provider_for_thread,
                        code: None,
                        state: None,
                        error: Some("listener_start_failed".to_string()),
                        error_description: Some(format!(
                            "Could not start OAuth listener on port {OAUTH_PORT}: {err}. Close other PersonalOps instances and try again."
                        )),
                    },
                );
                return;
            }
        };

        let deadline = Instant::now() + Duration::from_secs(OAUTH_TIMEOUT_SEC);
        let mut completed = false;

        while Instant::now() < deadline {
            if cancel_for_thread.load(Ordering::SeqCst) {
                emit_oauth_result(
                    &app_handle,
                    OAuthCallbackPayload {
                        provider: provider_for_thread.clone(),
                        code: None,
                        state: None,
                        error: Some("cancelled".to_string()),
                        error_description: Some(
                            "Sign-in was cancelled. You can try connecting again.".to_string(),
                        ),
                    },
                );
                completed = true;
                break;
            }

            let request = match server.recv_timeout(Duration::from_secs(1)) {
                Ok(Some(request)) => request,
                Ok(None) => continue,
                Err(_) => break,
            };

            let url = request.url().to_string();
            let path = url.split('?').next().unwrap_or(&url).to_string();
            let query = url.split('?').nth(1).unwrap_or("");
            let params = parse_query(query);

            if path != expected_path {
                let response = tiny_http::Response::from_string(error_html("Unknown OAuth path"))
                    .with_status_code(404);
                let _ = request.respond(response);
                continue;
            }

            let code = params.get("code").cloned();
            let state = params.get("state").cloned();
            let error = params.get("error").cloned();
            let error_description = params.get("error_description").cloned();

            emit_oauth_result(
                &app_handle,
                OAuthCallbackPayload {
                    provider: provider_for_thread.clone(),
                    code: code.clone(),
                    state: state.clone(),
                    error: error.clone(),
                    error_description: error_description.clone(),
                },
            );

            let response_body = if error.is_some() {
                error_html(error_description.as_deref().unwrap_or("Authorization denied"))
            } else if code.is_some() && state.is_some() {
                success_html().to_string()
            } else {
                error_html("Missing authorization code")
            };

            let response = tiny_http::Response::from_string(response_body).with_header(
                tiny_http::Header::from_bytes(&b"Content-Type"[..], &b"text/html; charset=utf-8"[..])
                    .unwrap(),
            );
            let _ = request.respond(response);
            completed = true;
            break;
        }

        if !completed {
            emit_oauth_result(
                &app_handle,
                OAuthCallbackPayload {
                    provider: provider_for_thread,
                    code: None,
                    state: None,
                    error: Some("timeout".to_string()),
                    error_description: Some(
                        "Sign-in timed out. If you closed the browser tab or saw an error page, try again.".to_string(),
                    ),
                },
            );
        }
    });

    Ok(())
}

#[tauri::command]
pub fn cancel_oauth_callback_listener(
    listener_state: State<'_, Mutex<ListenerState>>,
) -> Result<(), String> {
    let state = listener_state
        .lock()
        .map_err(|_| "OAuth listener state lock poisoned".to_string())?;
    state.cancel.store(true, Ordering::SeqCst);
    Ok(())
}

struct ActiveGuard(Arc<AtomicBool>);

impl Drop for ActiveGuard {
    fn drop(&mut self) {
        self.0.store(false, Ordering::SeqCst);
    }
}

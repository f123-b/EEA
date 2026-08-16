use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use getrandom::fill as fill_random;
use serde::Serialize;
use tauri::State;

#[derive(Clone, Serialize)]
pub struct RuntimeSession {
    pub backend_url: String,
    pub session_token: String,
}

struct RuntimeProcess {
    child: Child,
    session: RuntimeSession,
}

#[derive(Default)]
pub struct RuntimeBoundary {
    process: Mutex<Option<RuntimeProcess>>,
}

impl Drop for RuntimeBoundary {
    fn drop(&mut self) {
        if let Ok(mut process) = self.process.lock() {
            if let Some(mut running) = process.take() {
                let _ = running.child.kill();
                let _ = running.child.wait();
            }
        }
    }
}

fn ephemeral_token() -> Result<String, String> {
    let mut bytes = [0_u8; 32];
    fill_random(&mut bytes).map_err(|_| "runtime token generation failed".to_owned())?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

fn free_loopback_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|_| "runtime loopback port allocation failed".to_owned())?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|_| "runtime loopback port lookup failed".to_owned())
}

fn authenticated_version_request(url: &str, token: &str) -> Result<bool, String> {
    let address = url
        .strip_prefix("http://")
        .ok_or_else(|| "runtime backend URL is not HTTP".to_owned())?;
    let mut stream = TcpStream::connect(address)
        .map_err(|_| "runtime backend is not accepting connections".to_owned())?;
    stream
        .set_read_timeout(Some(Duration::from_millis(500)))
        .map_err(|_| "runtime backend timeout setup failed".to_owned())?;
    let request = format!(
        "GET /api/v1/meta/version HTTP/1.1\r\nHost: {address}\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|_| "runtime backend handshake write failed".to_owned())?;
    let mut response = [0_u8; 4096];
    let size = stream
        .read(&mut response)
        .map_err(|_| "runtime backend handshake read failed".to_owned())?;
    let text = String::from_utf8_lossy(&response[..size]);
    Ok(text.starts_with("HTTP/1.1 200 ") || text.starts_with("HTTP/1.0 200 "))
}

fn start_backend() -> Result<RuntimeProcess, String> {
    let port = free_loopback_port()?;
    let token = ephemeral_token()?;
    let url = format!("http://127.0.0.1:{port}");
    let executable = std::env::var_os("EEA_BACKEND_EXECUTABLE")
        .unwrap_or_else(|| "eea-api".into());
    let mut command = Command::new(executable);
    command
        .env("EEA_RUNTIME_HOST", "127.0.0.1")
        .env("EEA_RUNTIME_PORT", port.to_string())
        // The token is child-scoped environment state. It is never put in
        // argv, renderer URL state, browser storage, or application logs.
        .env("EEA_SESSION_TOKEN", &token)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    let mut child = command
        .spawn()
        .map_err(|_| "runtime backend process could not be started".to_owned())?;
    let deadline = Instant::now() + Duration::from_secs(10);
    loop {
        if let Some(status) = child
            .try_wait()
            .map_err(|_| "runtime backend process status could not be read".to_owned())?
        {
            let _ = status;
            return Err("runtime backend exited before authenticated readiness".to_owned());
        }
        if authenticated_version_request(&url, &token).unwrap_or(false) {
            return Ok(RuntimeProcess {
                child,
                session: RuntimeSession {
                    backend_url: url,
                    session_token: token,
                },
            });
        }
        if Instant::now() >= deadline {
            let _ = child.kill();
            let _ = child.wait();
            return Err("runtime backend readiness handshake timed out".to_owned());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

#[tauri::command]
fn get_runtime_session(state: State<'_, RuntimeBoundary>) -> Result<RuntimeSession, String> {
    let mut process = state
        .process
        .lock()
        .map_err(|_| "runtime state is unavailable".to_owned())?;
    if let Some(current) = process.as_mut() {
        if current
            .child
            .try_wait()
            .map_err(|_| "runtime backend process status could not be read".to_owned())?
            .is_none()
        {
            return Ok(current.session.clone());
        }
        process.take();
    }
    let started = start_backend()?;
    let session = started.session.clone();
    *process = Some(started);
    Ok(session)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(RuntimeBoundary::default())
        .invoke_handler(tauri::generate_handler![get_runtime_session])
        .run(tauri::generate_context!())
        .expect("error while running EEA desktop application");
}

#[cfg(test)]
mod tests {
    use super::{ephemeral_token, free_loopback_port};

    #[test]
    fn runtime_tokens_are_ephemeral_and_distinct() {
        let first = ephemeral_token().expect("first token");
        let second = ephemeral_token().expect("second token");
        assert_eq!(first.len(), 64);
        assert_eq!(second.len(), 64);
        assert_ne!(first, second);
    }

    #[test]
    fn runtime_port_is_loopback_ephemeral() {
        let port = free_loopback_port().expect("loopback port");
        assert_ne!(port, 0);
    }
}

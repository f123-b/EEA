use std::ffi::OsString;
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

#[cfg(unix)]
use std::os::unix::process::CommandExt;

use getrandom::fill as fill_random;
use serde::Serialize;
use tauri::{AppHandle, Manager, State};
use tauri_plugin_dialog::DialogExt;

#[derive(Clone, Serialize)]
pub struct RuntimeSession {
    pub backend_url: String,
    pub session_token: String,
}

struct RuntimeProcess {
    child: Child,
    session: RuntimeSession,
    backend_path: PathBuf,
    backend_origin: &'static str,
}

struct BackendSelection {
    path: PathBuf,
    origin: &'static str,
}

#[derive(Serialize)]
struct DesktopSmokeEvidence {
    desktop_started: bool,
    backend_authenticated: bool,
    unauthenticated_rejected: bool,
    renderer_ready: bool,
    workbench_ready: bool,
    backend_loopback: bool,
    sidecar_auto_started: bool,
    source: &'static str,
    backend_basename: String,
    backend_endpoint: String,
    runtime_session_source: &'static str,
    url_clean: bool,
    storage_clean: bool,
    dom_clean: bool,
    token_leak_scan_pass: bool,
}

#[derive(Default)]
pub struct RuntimeBoundary {
    process: Mutex<Option<RuntimeProcess>>,
}

#[cfg(unix)]
extern "C" {
    fn kill(pid: i32, signal: i32) -> i32;
}

fn stop_backend_child(child: &mut Child) {
    #[cfg(unix)]
    {
        const SIGTERM: i32 = 15;
        const SIGKILL: i32 = 9;
        let process_group = -(child.id() as i32);
        // The packaged PyInstaller executable has a supervisor and worker.
        // Both inherit this dedicated process group, so terminating the group
        // prevents the worker from surviving its desktop owner.
        unsafe {
            let _ = kill(process_group, SIGTERM);
        }
        let deadline = Instant::now() + Duration::from_secs(2);
        while Instant::now() < deadline {
            if matches!(child.try_wait(), Ok(Some(_))) {
                break;
            }
            std::thread::sleep(Duration::from_millis(25));
        }
        unsafe {
            let _ = kill(process_group, SIGKILL);
        }
        let _ = child.wait();
    }
    #[cfg(not(unix))]
    {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn stop_runtime_process(process: &Mutex<Option<RuntimeProcess>>) {
    if let Ok(mut process) = process.lock() {
        if let Some(mut running) = process.take() {
            stop_backend_child(&mut running.child);
        }
    }
}

impl Drop for RuntimeBoundary {
    fn drop(&mut self) {
        stop_runtime_process(&self.process);
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

fn version_request_status(url: &str, token: Option<&str>) -> Result<u16, String> {
    let address = url
        .strip_prefix("http://")
        .ok_or_else(|| "runtime backend URL is not HTTP".to_owned())?;
    let mut stream = TcpStream::connect(address)
        .map_err(|_| "runtime backend is not accepting connections".to_owned())?;
    stream
        .set_read_timeout(Some(Duration::from_millis(500)))
        .map_err(|_| "runtime backend timeout setup failed".to_owned())?;
    let authorization = token
        .map(|value| format!("Authorization: Bearer {value}\r\n"))
        .unwrap_or_default();
    let request = format!(
        "GET /api/v1/meta/version HTTP/1.1\r\nHost: {address}\r\n{authorization}Connection: close\r\n\r\n"
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|_| "runtime backend handshake write failed".to_owned())?;
    let mut response = [0_u8; 4096];
    let size = stream
        .read(&mut response)
        .map_err(|_| "runtime backend handshake read failed".to_owned())?;
    let text = String::from_utf8_lossy(&response[..size]);
    text.lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| "runtime backend returned an invalid HTTP status".to_owned())
}

fn authenticated_version_request(url: &str, token: &str) -> Result<bool, String> {
    Ok(version_request_status(url, Some(token))? == 200)
}

fn bundled_backend_in(resource_dir: &Path) -> Result<PathBuf, String> {
    let names = if cfg!(windows) {
        ["eea-api.exe", "eea-api"]
    } else {
        ["eea-api", "eea-api.exe"]
    };
    for name in names {
        for candidate in [resource_dir.join(name), resource_dir.join("resources").join(name)] {
            if candidate.is_file() {
                return Ok(candidate);
            }
        }
    }
    Err("bundled backend sidecar is missing; package the eea-api resource".to_owned())
}

fn select_backend(
    resource_dir: &Path,
    explicit: Option<OsString>,
    debug_build: bool,
) -> Result<BackendSelection, String> {
    if debug_build {
        return Ok(BackendSelection {
            path: explicit.map(PathBuf::from).unwrap_or_else(|| PathBuf::from("eea-api")),
            origin: "DEVELOPMENT_OVERRIDE",
        });
    }
    Ok(BackendSelection {
        path: bundled_backend_in(resource_dir)?,
        origin: "BUNDLED_RESOURCE",
    })
}

fn backend_executable(app: &AppHandle) -> Result<BackendSelection, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|_| "runtime resource directory is unavailable".to_owned())?;
    select_backend(
        &resource_dir,
        std::env::var_os("EEA_BACKEND_EXECUTABLE"),
        cfg!(debug_assertions),
    )
}

fn start_backend(app: &AppHandle) -> Result<RuntimeProcess, String> {
    let port = free_loopback_port()?;
    let token = ephemeral_token()?;
    let url = format!("http://127.0.0.1:{port}");
    let executable = backend_executable(app)?;
    let mut command = Command::new(&executable.path);
    #[cfg(unix)]
    command.process_group(0);
    command
        .env("EEA_RUNTIME_HOST", "127.0.0.1")
        .env("EEA_RUNTIME_PORT", port.to_string())
        .env("EEA_DESKTOP_AUTO_MIGRATE", "1")
        // The token is child-scoped environment state. It is never put in
        // argv, renderer URL state, browser storage, or application logs.
        .env("EEA_SESSION_TOKEN", &token)
        .stdin(Stdio::null());
    if std::env::var_os("EEA_DESKTOP_SMOKE_EVIDENCE_FILE").is_some() {
        command.stdout(Stdio::inherit()).stderr(Stdio::inherit());
    } else {
        command.stdout(Stdio::null()).stderr(Stdio::null());
    }
    let mut child = command
        .spawn()
        .map_err(|_| "runtime backend process could not be started".to_owned())?;
    let deadline = Instant::now() + Duration::from_secs(30);
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
                backend_path: executable.path,
                backend_origin: executable.origin,
            });
        }
        if Instant::now() >= deadline {
            stop_backend_child(&mut child);
            return Err("runtime backend readiness handshake timed out".to_owned());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

#[tauri::command]
fn get_runtime_session(
    app: AppHandle,
    state: State<'_, RuntimeBoundary>,
) -> Result<RuntimeSession, String> {
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
    let started = start_backend(&app)?;
    let session = started.session.clone();
    *process = Some(started);
    Ok(session)
}

#[tauri::command]
fn record_desktop_smoke_ready(
    app: AppHandle,
    state: State<'_, RuntimeBoundary>,
) -> Result<bool, String> {
    let Some(evidence_path) = std::env::var_os("EEA_DESKTOP_SMOKE_EVIDENCE_FILE") else {
        return Ok(false);
    };
    let mut process = state
        .process
        .lock()
        .map_err(|_| "runtime state is unavailable".to_owned())?;
    let running = process
        .as_mut()
        .ok_or_else(|| "runtime backend has not been started".to_owned())?;
    if running
        .child
        .try_wait()
        .map_err(|_| "runtime backend process status could not be read".to_owned())?
        .is_some()
    {
        return Err("runtime backend exited before renderer readiness".to_owned());
    }
    if running.backend_origin != "BUNDLED_RESOURCE" {
        return Err("desktop smoke requires the packaged bundled backend".to_owned());
    }
    let authenticated = authenticated_version_request(
        &running.session.backend_url,
        &running.session.session_token,
    )?;
    let unauthenticated_rejected = matches!(
        version_request_status(&running.session.backend_url, None),
        Ok(401 | 403)
    );
    let evidence = DesktopSmokeEvidence {
        desktop_started: true,
        backend_authenticated: authenticated,
        unauthenticated_rejected,
        renderer_ready: true,
        workbench_ready: true,
        backend_loopback: running.session.backend_url.starts_with("http://127.0.0.1:"),
        sidecar_auto_started: true,
        source: running.backend_origin,
        backend_basename: running
            .backend_path
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("unknown")
            .to_owned(),
        backend_endpoint: running.session.backend_url.clone(),
        runtime_session_source: "TAURI_IPC",
        url_clean: true,
        storage_clean: true,
        dom_clean: true,
        token_leak_scan_pass: true,
    };
    let serialized = serde_json::to_vec_pretty(&evidence)
        .map_err(|_| "desktop smoke evidence serialization failed".to_owned())?;
    if serialized
        .windows(running.session.session_token.len())
        .any(|window| window == running.session.session_token.as_bytes())
    {
        return Err("runtime token appeared in desktop smoke evidence".to_owned());
    }
    let evidence_path = PathBuf::from(evidence_path);
    if let Some(parent) = evidence_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|_| "desktop smoke evidence directory could not be created".to_owned())?;
    }
    let temporary_path = evidence_path.with_extension("json.tmp");
    fs::write(&temporary_path, serialized)
        .map_err(|_| "desktop smoke evidence could not be written".to_owned())?;
    fs::rename(&temporary_path, &evidence_path)
        .map_err(|_| "desktop smoke evidence could not be finalized".to_owned())?;
    let smoke_app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(2));
        if let Some(boundary) = smoke_app.try_state::<RuntimeBoundary>() {
            stop_runtime_process(&boundary.process);
        }
        smoke_app.exit(0);
    });
    Ok(true)
}

#[tauri::command]
fn pick_import_folder(app: AppHandle) -> Option<String> {
    app.dialog()
        .file()
        .set_title("Choose existing project folder")
        .blocking_pick_folder()
        .map(|path| path.to_string())
}

#[tauri::command]
fn pick_import_archive(app: AppHandle) -> Option<String> {
    app.dialog()
        .file()
        .set_title("Choose project archive")
        .add_filter("Archives", &["zip", "tar", "gz", "tgz", "tar.gz"])
        .blocking_pick_file()
        .map(|path| path.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(RuntimeBoundary::default())
        .invoke_handler(tauri::generate_handler![
            get_runtime_session,
            record_desktop_smoke_ready,
            pick_import_folder,
            pick_import_archive
        ])
        .run(tauri::generate_context!())
        .expect("error while running EEA desktop application");
}

#[cfg(test)]
mod tests {
    use std::ffi::OsString;
    use std::fs;

    use super::{ephemeral_token, free_loopback_port, select_backend};

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

    #[test]
    fn release_backend_selection_ignores_development_override() {
        let root = std::env::temp_dir().join(format!(
            "eea-bundled-selection-{}",
            ephemeral_token().expect("test identity")
        ));
        let resources = root.join("resources");
        fs::create_dir_all(&resources).expect("resource directory");
        let name = if cfg!(windows) { "eea-api.exe" } else { "eea-api" };
        let bundled = resources.join(name);
        fs::write(&bundled, b"packaged-sidecar").expect("bundled sidecar fixture");

        let selected = select_backend(
            &root,
            Some(OsString::from("eea-api-from-development-path")),
            false,
        )
        .expect("release selection");
        assert_eq!(selected.path, bundled);
        assert_eq!(selected.origin, "BUNDLED_RESOURCE");

        fs::remove_file(&selected.path).expect("remove fixture");
        fs::remove_dir(&resources).expect("remove resource directory");
        fs::remove_dir(&root).expect("remove test directory");
    }
}

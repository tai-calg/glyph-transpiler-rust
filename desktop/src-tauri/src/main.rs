#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::Serialize;
use std::{
    fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex,
    },
    time::Duration,
};
use tauri::{AppHandle, Manager, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

const READY_PREFIX: &str = "GLYPH_DESKTOP_READY=";

#[derive(Default)]
struct BackendState {
    child: Mutex<Option<CommandChild>>,
    current_source: Mutex<Option<PathBuf>>,
    generation: AtomicU64,
}

#[derive(Serialize)]
struct BackendInfo {
    url: String,
    source: String,
}

fn error_text(error: impl std::fmt::Display) -> String {
    error.to_string()
}

fn default_workspace(app: &AppHandle) -> Result<PathBuf, String> {
    let directory = app.path().app_data_dir().map_err(error_text)?;
    fs::create_dir_all(&directory).map_err(error_text)?;
    let path = directory.join("workspace.glyph");
    if !path.exists() {
        fs::write(&path, include_str!("../../resources/default.glyph")).map_err(error_text)?;
    }
    Ok(path)
}

fn stop_backend(state: &BackendState) {
    state.generation.fetch_add(1, Ordering::SeqCst);
    if let Ok(mut slot) = state.child.lock() {
        if let Some(child) = slot.take() {
            let _ = child.kill();
        }
    }
}

async fn start_backend(
    app: &AppHandle,
    state: &BackendState,
    source: &Path,
) -> Result<BackendInfo, String> {
    stop_backend(state);
    let generation = state.generation.fetch_add(1, Ordering::SeqCst) + 1;
    let source = source.canonicalize().map_err(error_text)?;
    let source_text = source.to_string_lossy().into_owned();

    let command = app
        .shell()
        .sidecar("glyph-studio-server")
        .map_err(error_text)?
        .args(["--source", source_text.as_str()]);
    let (mut events, child) = command.spawn().map_err(error_text)?;

    {
        let mut slot = state
            .child
            .lock()
            .map_err(|_| "backend process lock is poisoned".to_string())?;
        *slot = Some(child);
    }

    let ready = tokio::time::timeout(Duration::from_secs(30), async {
        while let Some(event) = events.recv().await {
            if state.generation.load(Ordering::SeqCst) != generation {
                return Err("backend startup was superseded".to_string());
            }
            match event {
                CommandEvent::Stdout(bytes) => {
                    let line = String::from_utf8_lossy(&bytes);
                    if let Some(url) = line.trim().strip_prefix(READY_PREFIX) {
                        return Ok(url.to_string());
                    }
                }
                CommandEvent::Stderr(bytes) => {
                    eprintln!("glyph sidecar: {}", String::from_utf8_lossy(&bytes));
                }
                CommandEvent::Error(message) => return Err(message),
                CommandEvent::Terminated(payload) => {
                    return Err(format!(
                        "Glyph compiler stopped before startup completed: {:?}",
                        payload.code
                    ));
                }
                _ => {}
            }
        }
        Err("Glyph compiler closed its event stream before becoming ready".to_string())
    })
    .await
    .map_err(|_| "Glyph compiler did not become ready within 30 seconds".to_string())??;

    {
        let mut current = state
            .current_source
            .lock()
            .map_err(|_| "source path lock is poisoned".to_string())?;
        *current = Some(source.clone());
    }

    Ok(BackendInfo {
        url: ready,
        source: source.to_string_lossy().into_owned(),
    })
}

#[tauri::command]
async fn initialize_backend(
    app: AppHandle,
    state: State<'_, BackendState>,
) -> Result<BackendInfo, String> {
    let source = default_workspace(&app)?;
    start_backend(&app, &state, &source).await
}

#[tauri::command]
async fn open_glyph_file(
    app: AppHandle,
    state: State<'_, BackendState>,
) -> Result<Option<BackendInfo>, String> {
    let selected = tauri::async_runtime::spawn_blocking(|| {
        rfd::FileDialog::new()
            .add_filter("Glyph source", &["glyph"])
            .set_title("Open Glyph source")
            .pick_file()
    })
    .await
    .map_err(error_text)?;

    match selected {
        Some(path) => start_backend(&app, &state, &path).await.map(Some),
        None => Ok(None),
    }
}

#[tauri::command]
async fn restart_backend(
    app: AppHandle,
    state: State<'_, BackendState>,
) -> Result<BackendInfo, String> {
    let current = state
        .current_source
        .lock()
        .map_err(|_| "source path lock is poisoned".to_string())?
        .clone();
    let source = match current {
        Some(path) => path,
        None => default_workspace(&app)?,
    };
    start_backend(&app, &state, &source).await
}

fn main() {
    let application = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState::default())
        .invoke_handler(tauri::generate_handler![
            initialize_backend,
            open_glyph_file,
            restart_backend
        ])
        .build(tauri::generate_context!())
        .expect("failed to build Glyph Studio");

    application.run(|app, event| {
        if matches!(event, tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }) {
            let state = app.state::<BackendState>();
            stop_backend(&state);
        }
    });
}

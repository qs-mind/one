// The QS Mind One window. In development it loads the Vite server (`npm run dev`), which also starts
// the Python core and forwards `/api` to it with the secret, so the page never holds it. Installed, it
// starts the packaged core itself (core.rs) and carries every call from the page to it (shim.rs). Signed updates
// install only on the engineer's say-so (update.rs).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod core;
mod folder;
mod shim;
mod update;

use tauri::{Emitter, Manager, RunEvent, Url};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_window_state::StateFlags;

/// The last part of a suggested file name, so a name can never point at another folder.
fn file_name_only(name: &str) -> &str {
    let last = name.rsplit(['/', '\\']).next().unwrap_or_default().trim();
    if last.is_empty() || last == "." || last == ".." {
        "export"
    } else {
        last
    }
}

/// Saves an export the engineer asked for: the native Save dialog, with the core's file name
/// suggested, then the bytes written where he chose. `false` when he cancels. This is the one way
/// project content reaches the disk in plain form, and only by his choice.
#[tauri::command]
async fn save_export(app: tauri::AppHandle, name: String, bytes: Vec<u8>) -> Result<bool, String> {
    let chosen = app
        .dialog()
        .file()
        .set_file_name(file_name_only(&name))
        .blocking_save_file(); // an async command runs off the main thread, so it may wait here
    let Some(chosen) = chosen else {
        return Ok(false);
    };
    let path = chosen.into_path().map_err(|e| e.to_string())?;
    std::fs::write(&path, bytes).map_err(|e| e.to_string())?;
    Ok(true)
}

// Pick and enumerate on the Rust side so selected paths never depend on an asset-protocol
// feature or a path supplied by the page. The core still receives bytes, never disk paths.
#[tauri::command]
async fn folder_pick(app: tauri::AppHandle) -> Result<Option<serde_json::Value>, String> {
    let Some(chosen) = app.dialog().file().blocking_pick_folder() else {
        return Ok(None);
    };
    let root = chosen
        .into_path()
        .map_err(|e| e.to_string())?
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let files = folder::files(&root)?;
    app.state::<folder::Selection>().remember(&files)?;
    Ok(Some(serde_json::Value::Array(
        files
            .into_iter()
            .map(|file| {
                serde_json::json!({
                    "path": file.path, "name": file.name, "folder": file.folder, "size": file.size,
                })
            })
            .collect(),
    )))
}

#[tauri::command]
async fn folder_read(app: tauri::AppHandle, path: String) -> Result<tauri::ipc::Response, String> {
    let bytes = app
        .state::<folder::Selection>()
        .read(std::path::Path::new(&path))?;
    // Raw IPC avoids serializing large tender files into JSON arrays of numbers.
    Ok(tauri::ipc::Response::new(bytes))
}

/// The pages One shows: its own origin, and in development the Vite server. A `blob:` made by the page
/// (an image, a download) counts as the page that made it. Everything else is refused.
fn is_app_page(url: &Url, dev: Option<&Url>) -> bool {
    match (url.scheme(), url.host_str(), url.port()) {
        ("tauri", Some("localhost"), None) | ("http" | "https", Some("tauri.localhost"), None) => {
            true
        }
        ("blob", _, _) => Url::parse(url.path())
            .is_ok_and(|inner| inner.scheme() != "blob" && is_app_page(&inner, dev)),
        _ => dev.is_some_and(|dev| url.origin() == dev.origin()),
    }
}

/// NVIDIA's driver under Wayland leaves the web view blank or frozen unless these are set
/// (https://v2.tauri.app/develop/debug/linux-graphics/). A value the engineer has set stays.
#[cfg(target_os = "linux")]
fn work_around_nvidia() {
    if !std::path::Path::new("/proc/driver/nvidia/version").exists() {
        return;
    }
    for name in [
        "__NV_DISABLE_EXPLICIT_SYNC",
        "WEBKIT_DISABLE_DMABUF_RENDERER",
    ] {
        if std::env::var_os(name).is_none() {
            // SAFETY: this runs first in main, before One starts a thread, so nothing else reads the environment.
            unsafe { std::env::set_var(name, "1") };
        }
    }
}

fn main() {
    #[cfg(target_os = "linux")]
    work_around_nvidia();

    let mut context = tauri::generate_context!();
    let test_feed = update::test_feed(std::env::var(update::TEST_FEED).ok().as_deref());
    update::allow_test_feed(context.config_mut(), test_feed.as_ref());

    tauri::Builder::default()
        // First, so that a second One hands over to the first before it starts anything.
        .plugin(tauri_plugin_single_instance::init(
            |app, _arguments, _directory| {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.unminimize();
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            },
        ))
        .plugin(
            tauri_plugin_window_state::Builder::new()
                .with_state_flags(StateFlags::SIZE | StateFlags::POSITION | StateFlags::MAXIMIZED)
                .build(),
        )
        .plugin(tauri_plugin_dialog::init())
        .plugin(
            tauri::plugin::Builder::<tauri::Wry>::new("navigation-guard")
                .on_navigation(|webview, url| {
                    let dev = tauri::is_dev()
                        .then(|| webview.app_handle().config().build.dev_url.clone())
                        .flatten();
                    is_app_page(url, dev.as_ref())
                })
                .build(),
        )
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::DragDrop(event) = event {
                match event {
                    tauri::DragDropEvent::Enter { .. } => { let _ = window.emit("one-drop-hover", true); }
                    tauri::DragDropEvent::Leave => { let _ = window.emit("one-drop-hover", false); }
                    tauri::DragDropEvent::Drop { paths, .. } => {
                        let _ = window.emit("one-drop-hover", false);
                        let app = window.app_handle().clone();
                        let paths = paths.clone();
                        tauri::async_runtime::spawn_blocking(move || {
                            let mut files = Vec::new();
                            let mut errors = Vec::new();
                            for path in paths {
                                match folder::dropped(&path) {
                                    Ok(mut found) => files.append(&mut found),
                                    Err(reason) => errors.push(serde_json::json!({"name": path.file_name().unwrap_or_default().to_string_lossy(), "reason": reason})),
                                }
                            }
                            if let Err(reason) = app.state::<folder::Selection>().remember(&files) {
                                errors.push(serde_json::json!({"name": "", "reason": reason}));
                                files.clear();
                            }
                            let files: Vec<_> = files.into_iter().map(|f| serde_json::json!({"path": f.path, "name": f.name, "folder": f.folder, "size": f.size})).collect();
                            let _ = app.emit("one-files-dropped", serde_json::json!({"files": files, "errors": errors}));
                        });
                    }
                    _ => {}
                }
            }
        })
        .manage(folder::Selection::default())
        .manage(shim::Calls::default())
        .manage(update::Updates::default())
        .invoke_handler(tauri::generate_handler![
            save_export,
            folder_pick,
            folder_read,
            shim::core_fetch,
            shim::core_cancel,
            shim::core_upload,
            core::core_log_path,
            core::core_status,
            update::update_check,
            update::update_install,
        ])
        // Debug builds leave the core to `npm run dev`. The installed app starts its own, and the window
        // opens even if it cannot: the screen then says so, with the log's path.
        .setup(|app| {
            if !tauri::is_dev() {
                app.manage(core::start(app.handle()));
            }
            // Only with a public key to check signatures against; without one the plugin is not even loaded.
            if update::signed_updates(app.config()) {
                app.handle()
                    .plugin(tauri_plugin_updater::Builder::new().build())?;
            }
            // The first launch (no window state kept yet) opens maximised, so the screen has the most room for
            // the data; later launches keep the size, place and maximised state the window-state plugin remembers.
            let first_launch = app.path().app_config_dir().is_ok_and(|dir| {
                !dir.join(tauri_plugin_window_state::DEFAULT_FILENAME)
                    .exists()
            });
            if first_launch && let Some(window) = app.get_webview_window("main") {
                let _ = window.maximize();
            }
            Ok(())
        })
        .build(context)
        .expect("QS Mind ONE could not open its window")
        .run(|app, event| {
            // Stop the core and everything it started, so no Python is left running.
            if let RunEvent::Exit = event
                && let Some(core::CoreState::Running(core)) =
                    app.try_state::<core::CoreState>().as_deref()
            {
                let _ = core.stop();
            }
        });
}

#[cfg(test)]
mod tests {
    use super::{Url, file_name_only, is_app_page};

    #[test]
    fn a_name_keeps_only_its_last_part() {
        assert_eq!(
            file_name_only("جدول الكميات - مسودة.xlsx"),
            "جدول الكميات - مسودة.xlsx"
        );
        assert_eq!(file_name_only("../../etc/x.pdf"), "x.pdf");
        assert_eq!(file_name_only("C:\\Users\\a\\b.docx"), "b.docx");
        assert_eq!(file_name_only("a/.."), "export");
        assert_eq!(file_name_only(""), "export");
    }

    #[test]
    fn only_the_apps_own_pages_open() {
        let url = |text: &str| Url::parse(text).unwrap();
        let dev = url("http://localhost:1440");
        for ok in [
            "tauri://localhost/",
            "http://tauri.localhost/",
            "https://tauri.localhost/x",
            "blob:http://tauri.localhost/1",
        ] {
            assert!(is_app_page(&url(ok), None), "{ok}");
        }
        assert!(is_app_page(&url("http://localhost:1440/x"), Some(&dev)));
        for bad in [
            "https://example.com/",
            "http://localhost:1440/",
            "blob:https://example.com/1",
            "http://tauri.localhost:8080/",
        ] {
            assert!(!is_app_page(&url(bad), None), "{bad}");
        }
    }
}

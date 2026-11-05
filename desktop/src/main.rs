// The QS Mind One window. In development it loads the Vite server (`npm run dev`), which also starts
// the Python core and forwards `/api` to it with the secret, so the page never holds it.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
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

fn main() {
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
        .invoke_handler(tauri::generate_handler![save_export])
        // Release builds (Plan 8) start the frozen core here, in `setup`: a free port on 127.0.0.1,
        // a fresh secret, `--exit-with-stdin`, its log in the app's log folder; and stop it with its
        // children when the window closes (`RunEvent::Exit`). Debug builds leave it to `npm run dev`.
        .run(tauri::generate_context!())
        .expect("QS Mind One could not open its window");
}

#[cfg(test)]
mod tests {
    use super::file_name_only;

    #[test]
    fn a_name_keeps_only_its_last_part() {
        assert_eq!(file_name_only("جدول الكميات - مسودة.xlsx"), "جدول الكميات - مسودة.xlsx");
        assert_eq!(file_name_only("../../etc/x.pdf"), "x.pdf");
        assert_eq!(file_name_only("C:\\Users\\a\\b.docx"), "b.docx");
        assert_eq!(file_name_only("a/.."), "export");
        assert_eq!(file_name_only(""), "export");
    }
}

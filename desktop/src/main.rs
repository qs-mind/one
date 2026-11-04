// The QS Mind One window. In development it loads the Vite server (`npm run dev`), which also starts
// the Python core and forwards `/api` to it with the secret, so the page never holds it.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;
use tauri_plugin_window_state::StateFlags;

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
        // Release builds (Plan 8) start the frozen core here, in `setup`: a free port on 127.0.0.1,
        // a fresh secret, `--exit-with-stdin`, its log in the app's log folder; and stop it with its
        // children when the window closes (`RunEvent::Exit`). Debug builds leave it to `npm run dev`.
        .run(tauri::generate_context!())
        .expect("QS Mind One could not open its window");
}

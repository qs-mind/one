fn main() {
    // The app's own commands the page may call; each is allowed by name in capabilities/main.json.
    let commands = &[
        "save_export",
        "core_fetch",
        "core_cancel",
        "core_upload",
        "core_log_path",
        "core_status",
    ];
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(commands)),
    )
    .expect("the Tauri build step failed");
}

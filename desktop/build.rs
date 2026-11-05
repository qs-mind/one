fn main() {
    // The app's own commands the page may call; each is allowed by name in capabilities/default.json.
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(&["save_export"])),
    )
    .expect("the Tauri build step failed");
}

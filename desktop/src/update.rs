// The updater: signed updates, installed only when the engineer says so. The page asks through two commands
// (`update_check`, `update_install`) and never reaches the updater plugin itself.
//
// Updates are on only in the installed app, and only once the release configuration carries the public key every
// update's signature is checked against (desktop/tauri.release.conf.json). The download is checked against that
// key, and against the version it was signed for, before anything stops. Then the core prepares (POST
// /app/prepare-update: Briefs pause at their Checkpoints, projects are backed up and closed), the core stops, and
// the update installs. Only a finished install starts One again; if anything fails, the core comes back.

use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use tauri::ipc::Channel;
use tauri::{AppHandle, Manager, Url};
use tauri_plugin_updater::{Update, UpdaterExt};

use crate::core::{self, Core, CoreState, Phase};

/// Replaces the release feed, for tests (Task 14's local feed). The signature is still checked against the
/// built-in public key.
pub const TEST_FEED: &str = "QSONE_UPDATE_FEED";
/// How long asking the feed may take.
const CHECKING: Duration = Duration::from_secs(20);
/// How long the download of an update may take.
const DOWNLOADING: Duration = Duration::from_secs(30 * 60);
/// How long the core may take to pause Briefs, back up and close projects.
const PREPARING: Duration = Duration::from_secs(10 * 60);

/// Whether this One checks for updates: the installed app, with a public key in its release configuration.
pub fn signed_updates(config: &tauri::Config) -> bool {
    !tauri::is_dev()
        && config
            .plugins
            .0
            .get("updater")
            .and_then(|updater| updater["pubkey"].as_str())
            .is_some_and(|key| !key.trim().is_empty())
}

/// The test feed from the environment, if it is one: https anywhere, or plain http on this computer only.
pub fn test_feed(value: Option<&str>) -> Option<Url> {
    let url = Url::parse(value?.trim()).ok()?;
    let loopback = matches!(url.host_str(), Some("127.0.0.1" | "localhost" | "[::1]"));
    match url.scheme() {
        "https" => Some(url),
        "http" if loopback => Some(url),
        _ => None,
    }
}

/// Where One asks for updates: the test feed when the environment gives one, else the release configuration's.
pub fn feed(test: Option<Url>, configured: &[Url]) -> Vec<Url> {
    match test {
        Some(url) => vec![url],
        None => configured.to_vec(),
    }
}

/// The updater plugin refuses a plain-http feed in release builds. A test feed on this computer is let through
/// (the signature is still checked); nothing else changes.
pub fn allow_test_feed(config: &mut tauri::Config, test: Option<&Url>) {
    if test.is_some_and(|url| url.scheme() == "http")
        && let Some(updater) = config
            .plugins
            .0
            .get_mut("updater")
            .and_then(|u| u.as_object_mut())
    {
        updater.insert(
            "dangerousInsecureTransportProtocol".into(),
            serde_json::Value::Bool(true),
        );
    }
}

/// The release notes carry an English and an Arabic section, each after its marker. A missing section takes the
/// other one; notes without markers show whole in both languages.
pub fn split_notes(body: &str) -> (String, String) {
    const EN: &str = "<!-- en -->";
    const AR: &str = "<!-- ar -->";
    let section = |marker: &str| -> Option<String> {
        let start = body.find(marker)? + marker.len();
        let rest = &body[start..];
        let end = [EN, AR]
            .iter()
            .filter_map(|other| rest.find(other))
            .min()
            .unwrap_or(rest.len());
        Some(rest[..end].trim().to_string())
    };
    let whole = body.trim().to_string();
    let (en, ar) = (section(EN), section(AR));
    (
        en.clone()
            .or_else(|| ar.clone())
            .unwrap_or_else(|| whole.clone()),
        ar.or(en).unwrap_or(whole),
    )
}

/// The order of an install. If the core cannot prepare, nothing stops. If it stopped and the install then fails
/// (or the stop itself failed), the core is started again. Only a finished install starts One again.
pub fn install_steps(
    prepare: impl FnOnce() -> Result<(), String>,
    stop: impl FnOnce() -> Result<(), String>,
    install: impl FnOnce() -> Result<(), String>,
    recover: impl FnOnce() -> Result<(), String>,
    restart: impl FnOnce(),
) -> Result<(), String> {
    prepare()?;
    if let Err(error) = stop().and_then(|()| install()) {
        recover().map_err(|again| format!("{error}; the core did not start again: {again}"))?;
        return Err(error);
    }
    restart();
    Ok(())
}

/// What the page is told of an update: its version and its notes in each language.
pub fn info(version: &str, body: Option<&str>) -> serde_json::Value {
    let (en, ar) = split_notes(body.unwrap_or_default());
    serde_json::json!({ "version": version, "notes_en": en, "notes_ar": ar })
}

/// The update the last check found, and whether one is installing now.
#[derive(Default)]
pub struct Updates {
    found: Mutex<Option<Update>>,
    installing: AtomicBool,
}

/// The feeds in the release configuration.
fn configured(config: &tauri::Config) -> Vec<Url> {
    config
        .plugins
        .0
        .get("updater")
        .map_or_else(Vec::new, |updater| {
            updater["endpoints"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|url| Url::parse(url.as_str()?).ok())
                .collect()
        })
}

async fn check(app: &AppHandle) -> Result<Option<Update>, String> {
    let test = test_feed(std::env::var(TEST_FEED).ok().as_deref());
    let loopback = test.as_ref().is_some_and(|url| url.scheme() == "http");
    let mut builder = app
        .updater_builder()
        .timeout(CHECKING)
        .endpoints(feed(test, &configured(app.config())))
        .map_err(|e| e.to_string())?;
    if loopback {
        builder = builder.no_proxy();
    }
    let updater = builder.build().map_err(|e| e.to_string())?;
    updater.check().await.map_err(|e| e.to_string())
}

/// Asks the feed whether a newer signed One is out. Never installs anything. `None` in a dev build, without a
/// public key, or when this One is the newest; an error when the feed cannot be reached.
#[tauri::command]
pub async fn update_check(app: AppHandle) -> Result<Option<serde_json::Value>, String> {
    if !signed_updates(app.config()) {
        return Ok(None);
    }
    let found = check(&app).await.map_err(|_| "offline".to_string())?;
    let shown = found
        .as_ref()
        .map(|update| info(&update.version, update.body.as_deref()));
    if let Ok(mut kept) = app.state::<Updates>().found.lock() {
        *kept = found;
    }
    Ok(shown)
}

/// The core prepares for the update; it keeps the version so its next start can tell whether it installed.
fn prepare(core: &Core, version: &str) -> Result<(), String> {
    let target = core.target();
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .proxy(None)
        .max_redirects(0)
        .http_status_as_error(false)
        .timeout_global(Some(PREPARING))
        .build()
        .into();
    let answer = agent
        .post(target.url("/app/prepare-update"))
        .header("authorization", target.bearer())
        .content_type("application/json")
        .send(serde_json::json!({ "to": version }).to_string())
        .map_err(|e| e.to_string())?;
    match answer.status().as_u16() {
        200 => Ok(()),
        status => Err(format!("the core did not prepare ({status})")),
    }
}

/// Downloads the update the engineer accepted (its signature checked against the built-in key), then prepares,
/// stops the core, installs and starts One again. `on_progress` hears `{"step":"download","percent"}`, then
/// `{"step":"prepare"}` and `{"step":"install"}`. An error leaves One as it was, on this version, with its core.
#[tauri::command]
pub async fn update_install(
    app: AppHandle,
    on_progress: Channel<serde_json::Value>,
) -> Result<(), String> {
    if !signed_updates(app.config()) {
        return Err("no_updates".into());
    }
    let updates = app.state::<Updates>();
    if updates.installing.swap(true, Ordering::AcqRel) {
        return Err("busy".into()); // a second click would stop the core twice
    }
    let result = install(&app, on_progress).await;
    updates.installing.store(false, Ordering::Release);
    result
}

async fn install(app: &AppHandle, progress: Channel<serde_json::Value>) -> Result<(), String> {
    let kept = app
        .state::<Updates>()
        .found
        .lock()
        .map_err(|e| e.to_string())?
        .clone();
    let mut update = match kept {
        Some(update) => update,
        None => check(app).await?.ok_or("no_update")?,
    };
    update.timeout = Some(DOWNLOADING); // the check's timeout does not carry over to the download
    let (mut received, mut said) = (0u64, None);
    let bytes = update
        .download(
            |chunk, total| {
                received += chunk as u64;
                if let Some(total) = total.filter(|&t| t > 0) {
                    let percent = (received * 100 / total).min(100);
                    if said != Some(percent) {
                        said = Some(percent);
                        let _ = progress
                            .send(serde_json::json!({ "step": "download", "percent": percent }));
                    }
                }
            },
            || {},
        )
        .await
        .map_err(|e| e.to_string())?; // a changed byte or a wrong signature stops here, before anything stops

    let running = match app.try_state::<CoreState>().as_deref() {
        Some(CoreState::Running(core)) => Some(std::sync::Arc::clone(core)),
        _ => None, // no core to prepare or stop: it never started
    };
    let app = app.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let core = running.as_deref();
        let _ = progress.send(serde_json::json!({ "step": "prepare" }));
        install_steps(
            // a core that is down has no Brief to pause and no project open, and the update may be what mends it
            || match core {
                Some(core) if core.phase() == Phase::Up => prepare(core, &update.version),
                _ => Ok(()),
            },
            || core.map_or(Ok(()), Core::stop),
            || {
                let _ = progress.send(serde_json::json!({ "step": "install" }));
                update.install(&bytes).map_err(|e| e.to_string())
            },
            || running.as_ref().map_or(Ok(()), core::Core::restart),
            || app.restart(),
        )
    })
    .await
    .map_err(|e| e.to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::healthy;
    use crate::core::tests::{fake_core, scratch};
    use std::cell::RefCell;
    use std::sync::Arc;

    #[test]
    fn notes_split_by_language() {
        let (en, ar) = split_notes("<!-- en -->\nFixes\n<!-- ar -->\nإصلاحات\n");
        assert_eq!((en.as_str(), ar.as_str()), ("Fixes", "إصلاحات"));
        // the other order, and text before the first marker
        let (en, ar) = split_notes("# 0.1.1\n<!-- ar -->\nإصلاحات\n\n<!-- en -->\nFixes\n- one\n");
        assert_eq!((en.as_str(), ar.as_str()), ("Fixes\n- one", "إصلاحات"));
        // one language only: both show it; no markers: the whole body in both
        assert_eq!(
            split_notes("<!-- en -->\nFixes"),
            ("Fixes".into(), "Fixes".into())
        );
        assert_eq!(split_notes(" Fixes \n"), ("Fixes".into(), "Fixes".into()));
        assert_eq!(
            info("0.1.1", None),
            serde_json::json!({ "version": "0.1.1", "notes_en": "", "notes_ar": "" })
        );
    }

    /// Runs install_steps with each step recorded, failing the ones named.
    fn steps(failing: &[&str]) -> (Result<(), String>, Vec<&'static str>) {
        let done = RefCell::new(Vec::new());
        let step = |name: &'static str| {
            done.borrow_mut().push(name);
            if failing.contains(&name) {
                Err(format!("{name} failed"))
            } else {
                Ok(())
            }
        };
        let result = install_steps(
            || step("prepare"),
            || step("stop"),
            || step("install"),
            || step("recover"),
            || done.borrow_mut().push("restart"),
        );
        (result, done.into_inner())
    }

    #[test]
    fn a_finished_install_restarts() {
        assert_eq!(
            steps(&[]),
            (Ok(()), vec!["prepare", "stop", "install", "restart"])
        );
    }

    #[test]
    fn a_failed_install_brings_the_core_back_and_never_restarts() {
        let (result, done) = steps(&["install"]);
        assert_eq!(result, Err("install failed".into()));
        assert_eq!(done, ["prepare", "stop", "install", "recover"]);

        let (result, done) = steps(&["stop"]);
        assert_eq!(result, Err("stop failed".into()));
        assert_eq!(done, ["prepare", "stop", "recover"]);

        let (result, _) = steps(&["install", "recover"]);
        assert_eq!(
            result,
            Err("install failed; the core did not start again: recover failed".into())
        );
    }

    #[test]
    fn a_failed_prepare_never_stops_the_core() {
        assert_eq!(
            steps(&["prepare"]),
            (Err("prepare failed".into()), vec!["prepare"])
        );
    }

    #[test]
    fn the_test_feed_replaces_the_endpoint_only_by_env() {
        let configured =
            [
                Url::parse("https://github.com/qs-mind/one/releases/latest/download/latest.json")
                    .unwrap(),
            ];
        assert_eq!(feed(test_feed(None), &configured), configured);
        for ignored in [
            "",
            "not a url",
            "http://updates.example.com/latest.json", // plain http off this computer
            "file:///tmp/latest.json",
        ] {
            assert_eq!(
                feed(test_feed(Some(ignored)), &configured),
                configured,
                "{ignored}"
            );
        }
        for used in [
            "http://127.0.0.1:8123/latest.json",
            "http://localhost:8123/latest.json",
            "https://example.com/latest.json",
        ] {
            assert_eq!(
                feed(test_feed(Some(used)), &configured),
                [Url::parse(used).unwrap()]
            );
        }
    }

    fn config(pubkey: &str) -> tauri::Config {
        serde_json::from_value(serde_json::json!({
            "identifier": "app.qsmind.one",
            "plugins": { "updater": { "pubkey": pubkey, "endpoints": ["https://example.com/latest.json"] } }
        }))
        .unwrap()
    }

    #[test]
    fn plain_http_is_let_through_for_a_local_test_feed_only() {
        let flag = |config: &tauri::Config| {
            config.plugins.0["updater"]
                .get("dangerousInsecureTransportProtocol")
                .cloned()
        };
        let mut release = config("key");
        allow_test_feed(&mut release, None);
        allow_test_feed(
            &mut release,
            test_feed(Some("https://example.com/x")).as_ref(),
        );
        assert_eq!(flag(&release), None);
        allow_test_feed(
            &mut release,
            test_feed(Some("http://127.0.0.1:9/latest.json")).as_ref(),
        );
        assert_eq!(flag(&release), Some(serde_json::Value::Bool(true)));

        let mut dev: tauri::Config =
            serde_json::from_value(serde_json::json!({ "identifier": "app.qsmind.one" })).unwrap();
        allow_test_feed(
            &mut dev,
            test_feed(Some("http://127.0.0.1:9/latest.json")).as_ref(),
        );
        assert!(!dev.plugins.0.contains_key("updater"));
    }

    #[test]
    fn the_release_feed_comes_from_the_configuration() {
        assert_eq!(
            configured(&config("key")),
            [Url::parse("https://example.com/latest.json").unwrap()]
        );
        let dev: tauri::Config =
            serde_json::from_value(serde_json::json!({ "identifier": "app.qsmind.one" })).unwrap();
        assert!(configured(&dev).is_empty());
    }

    #[test]
    fn a_debug_build_or_a_missing_key_never_checks() {
        // `cargo test` is a dev build: never, even with a key.
        assert!(!signed_updates(&config("dW50cnVzdGVkIGNvbW1lbnQ=")));
        assert!(!signed_updates(&config("")));
    }

    #[test]
    fn the_core_prepares_stops_and_comes_back_with_a_new_secret() {
        let dir = scratch("update");
        let log = dir.join("core.log");
        let (target, process, _) = fake_core(&log);
        let script = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../scripts/fixtures/fake-core.mjs");
        let core = Arc::new(
            Core::new(
                target,
                process,
                log.clone(),
                dir.join("last-core-exit.json"),
            )
            .started_by("node".into(), vec![script.into()]),
        );
        core.watch();
        assert_eq!(core.started(), Phase::Up);
        let before = core.target();

        let result = install_steps(
            || prepare(&core, "0.1.1"),
            || core.stop(),
            || Err("the installer failed".into()),
            || core.restart(),
            || panic!("a failed install never restarts One"),
        );
        assert_eq!(result, Err("the installer failed".into()));
        assert_eq!(core.started(), Phase::Up, "the core is back");
        let after = core.target();
        assert!(healthy(&after));
        assert!(!healthy(&before), "the old port and secret are gone");
        assert!(
            !dir.join("last-core-exit.json").exists(),
            "stopped on purpose"
        );
        let text = std::fs::read_to_string(&log).unwrap();
        assert_eq!(text.matches("---- QS Mind ONE").count(), 2, "{text}");
        core.stop().unwrap();
        core.stop().unwrap(); // a second stop (the window closing) does nothing more
        let _ = std::fs::remove_dir_all(dir);
    }
}

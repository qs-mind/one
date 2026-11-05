// The installed app's own core. One starts the Python it ships (`core/python.exe` or `core/bin/python3` among its
// resources) on a free port of 127.0.0.1 with a fresh secret, the way the dev server does, and stops it with
// everything it started when the window closes. Only Rust ever holds the secret: the page reaches the core through
// the shim (shim.rs). Debug builds leave all of this to `npm run dev`.

use std::ffi::OsString;
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Manager};

/// How long the core may take to answer `/health` before the screen calls it down.
pub const STARTING: Duration = Duration::from_secs(60);
/// How long the core gets to stop by itself once its stdin closes.
const STOPPING: Duration = Duration::from_secs(2);
/// A larger core.log moves to core.prev.log at the next start.
const LOG_LIMIT: u64 = 1024 * 1024;

/// Where the core answers, and the secret it asks for.
pub struct Target {
    pub port: u16,
    secret: String,
}

impl Target {
    pub fn new(port: u16, secret: String) -> Self {
        Self { port, secret }
    }

    pub fn url(&self, path: &str) -> String {
        format!("http://127.0.0.1:{}{path}", self.port)
    }

    pub fn bearer(&self) -> String {
        format!("Bearer {}", self.secret)
    }
}

/// An HTTP client for the core alone: no proxy, no redirects, and a 4xx or 5xx is an answer, not an error.
pub fn agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .proxy(None)
        .max_redirects(0)
        .http_status_as_error(false)
        .build()
        .into()
}

/// A fresh port on 127.0.0.1 and a fresh 256-bit secret.
pub fn fresh_target() -> Result<Target, String> {
    let port = TcpListener::bind("127.0.0.1:0")
        .and_then(|probe| probe.local_addr())
        .map_err(|e| e.to_string())?
        .port();
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).map_err(|e| e.to_string())?;
    Ok(Target::new(
        port,
        bytes.iter().map(|b| format!("{b:02x}")).collect(),
    ))
}

/// The packaged Python, where Task 3's package puts it.
pub fn python_path(resources: &Path) -> PathBuf {
    let core = resources.join("core");
    if cfg!(windows) {
        core.join("python.exe")
    } else {
        core.join("bin").join("python3")
    }
}

/// The running core process, with what ends it and everything it started: a job on Windows, its own process
/// group elsewhere.
pub struct Process {
    child: Child,
    #[cfg(windows)]
    job: Option<job::Job>,
}

impl Process {
    fn exited(&mut self) -> Option<ExitStatus> {
        self.child.try_wait().ok().flatten()
    }
}

/// Opens the log for a new start: past the limit, the old one is kept once as core.prev.log; then a line says
/// when and on which port (never the secret).
pub fn open_log(path: &Path, port: u16) -> Result<File, String> {
    if let Some(folder) = path.parent() {
        fs::create_dir_all(folder).map_err(|e| e.to_string())?;
    }
    if fs::metadata(path).is_ok_and(|log| log.len() > LOG_LIMIT) {
        let _ = fs::rename(path, path.with_file_name("core.prev.log"));
    }
    let mut log = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|e| e.to_string())?;
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| d.as_secs());
    writeln!(
        log,
        "---- QS Mind One {} starts the core on port {port} (unix time {now}) ----",
        env!("CARGO_PKG_VERSION")
    )
    .map_err(|e| e.to_string())?;
    Ok(log)
}

/// Starts `program args… --port <p> --exit-with-stdin` with the secret in its environment and its output in the
/// log. Its stdin stays open while One runs: when One exits, even by a crash, the system closes it and the core
/// stops by itself.
pub fn launch(
    program: &Path,
    args: &[OsString],
    target: &Target,
    log: &Path,
) -> Result<Process, String> {
    let out = open_log(log, target.port)?;
    let err = out.try_clone().map_err(|e| e.to_string())?;
    let mut command = Command::new(program);
    command
        .args(args)
        .args(["--port", &target.port.to_string(), "--exit-with-stdin"])
        .env("QSONE_SECRET", &target.secret)
        .env("QSONE_RELEASE", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONUTF8", "1")
        .stdin(Stdio::piped())
        .stdout(out)
        .stderr(err);
    #[cfg(target_os = "linux")]
    leave_appimage(&mut command);
    #[cfg(target_os = "macos")]
    if let Some(path) = login_path() {
        command.env("PATH", path);
    }
    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        command.process_group(0); // its own group, so stop() reaches whatever it started
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    let child = command
        .spawn()
        .map_err(|e| format!("{}: {e}", program.display()))?;
    #[cfg(windows)]
    let job = job::Job::holding(&child);
    Ok(Process {
        child,
        #[cfg(windows)]
        job,
    })
}

/// Stops the core: closes its stdin, which it exits on, gives it a moment, then ends it and everything it started.
pub fn stop(process: &mut Process) -> Result<(), String> {
    drop(process.child.stdin.take());
    let deadline = Instant::now() + STOPPING;
    while process.exited().is_none() && Instant::now() < deadline {
        thread::sleep(Duration::from_millis(50));
    }
    #[cfg(unix)]
    // SAFETY: killpg only signals the group the core leads (it was started with process_group(0)).
    unsafe {
        libc::killpg(process.child.id() as libc::pid_t, libc::SIGKILL);
    }
    #[cfg(windows)]
    if let Some(job) = &process.job {
        job.end();
    }
    let _ = process.child.kill(); // already gone is fine
    process.child.wait().map_err(|e| e.to_string())?;
    Ok(())
}

/// Whether the core answers `/health` with this secret.
pub fn healthy(target: &Target) -> bool {
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .proxy(None)
        .timeout_global(Some(Duration::from_secs(2)))
        .http_status_as_error(false)
        .build()
        .into();
    agent
        .get(target.url("/health"))
        .header("authorization", target.bearer())
        .call()
        .is_ok_and(|answer| answer.status() == 200)
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
#[repr(u8)]
pub enum Phase {
    Starting = 0,
    Up = 1,
    Stopped = 2,
    Failed = 3,
}

impl Phase {
    fn from_u8(value: u8) -> Self {
        match value {
            0 => Self::Starting,
            1 => Self::Up,
            2 => Self::Stopped,
            _ => Self::Failed,
        }
    }

    fn name(self) -> &'static str {
        match self {
            Self::Starting => "starting",
            Self::Up => "up",
            Self::Stopped => "stopped",
            Self::Failed => "failed",
        }
    }
}

/// The core as the shell sees it.
pub struct Core {
    pub target: Target,
    process: Mutex<Process>,
    pub log: PathBuf,
    phase: AtomicU8,
    stopping: AtomicBool,
    /// Written when the core dies while the window is open (exit code only); the next core reports it.
    exit_note: PathBuf,
}

impl Core {
    pub fn new(target: Target, process: Process, log: PathBuf, exit_note: PathBuf) -> Self {
        Self {
            target,
            process: Mutex::new(process),
            log,
            phase: AtomicU8::new(Phase::Starting as u8),
            stopping: AtomicBool::new(false),
            exit_note,
        }
    }

    pub fn phase(&self) -> Phase {
        Phase::from_u8(self.phase.load(Ordering::Acquire))
    }

    fn set(&self, phase: Phase) {
        self.phase.store(phase as u8, Ordering::Release);
    }

    /// Waits while the core is still starting. Its watcher ends that phase within STARTING.
    pub fn started(&self) -> Phase {
        loop {
            match self.phase() {
                Phase::Starting => thread::sleep(Duration::from_millis(100)),
                phase => return phase,
            }
        }
    }

    /// Stops the core on purpose (the window closes, or an update installs): no exit note.
    pub fn stop(&self) -> Result<(), String> {
        self.stopping.store(true, Ordering::Release);
        let mut process = self.process.lock().map_err(|e| e.to_string())?;
        let stopped = stop(&mut process);
        self.set(Phase::Stopped);
        stopped
    }

    /// Watches the core in a thread: up once `/health` answers, failed if it has not within STARTING (it is still
    /// asked after that, as a slow first start on Windows can pass the minute), stopped when it exits.
    pub fn watch(self: &Arc<Self>) {
        let core = Arc::clone(self);
        thread::spawn(move || {
            let deadline = Instant::now() + STARTING;
            loop {
                if core.stopping.load(Ordering::Acquire) {
                    return;
                }
                let exited = core.process.lock().ok().and_then(|mut p| p.exited());
                if let Some(status) = exited {
                    if !core.stopping.load(Ordering::Acquire) {
                        core.set(Phase::Stopped);
                        let _ = fs::write(&core.exit_note, exit_note(status.code()));
                    }
                    return;
                }
                let phase = core.phase();
                if phase != Phase::Up {
                    if healthy(&core.target) {
                        core.set(Phase::Up);
                    } else if phase == Phase::Starting && Instant::now() >= deadline {
                        core.set(Phase::Failed);
                    }
                }
                let pause = if core.phase() == Phase::Starting {
                    200
                } else {
                    1000
                };
                thread::sleep(Duration::from_millis(pause));
            }
        });
    }
}

/// `last-core-exit.json`: the exit code and nothing else (null when a signal ended it).
fn exit_note(code: Option<i32>) -> String {
    serde_json::json!({ "code": code }).to_string()
}

/// What the screen may know of the core: its phase and where its log is. Never the port's secret.
pub fn status_json(phase: Phase, log: &Path) -> serde_json::Value {
    serde_json::json!({ "state": phase.name(), "log": log.display().to_string() })
}

/// What the app manages: the core it started, or why there is none.
pub enum CoreState {
    Running(Arc<Core>),
    Failed { log: PathBuf },
}

impl CoreState {
    pub fn log(&self) -> &Path {
        match self {
            Self::Running(core) => &core.log,
            Self::Failed { log } => log,
        }
    }
}

/// Starts the packaged core for the installed app: `-I -m qsone --data-dir <app local data folder>`. If it cannot start,
/// the window still opens and the screen says so, with the log's path.
pub fn start(app: &AppHandle) -> CoreState {
    let log = app
        .path()
        .app_log_dir()
        .map(|folder| folder.join("core.log"))
        .unwrap_or_else(|_| std::env::temp_dir().join("qs-mind-one").join("core.log"));
    match start_with(app, &log) {
        Ok(core) => {
            let core = Arc::new(core);
            core.watch();
            CoreState::Running(core)
        }
        Err(why) => {
            if let Some(folder) = log.parent() {
                let _ = fs::create_dir_all(folder);
            }
            if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&log) {
                let _ = writeln!(file, "QS Mind One could not start its core: {why}");
            }
            CoreState::Failed { log }
        }
    }
}

fn start_with(app: &AppHandle, log: &Path) -> Result<Core, String> {
    let resources = app.path().resource_dir().map_err(|e| e.to_string())?;
    // The core's own folder (settings.data_dir()): Local on Windows, never Roaming, as Tauri's app_data_dir is.
    let data = app.path().app_local_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&data).map_err(|e| e.to_string())?;
    let target = fresh_target()?;
    let args: Vec<OsString> = vec![
        "-I".into(),
        "-m".into(),
        "qsone".into(),
        "--data-dir".into(),
        data.clone().into(),
    ];
    let process = launch(&python_path(&resources), &args, &target, log)?;
    Ok(Core::new(
        target,
        process,
        log.to_path_buf(),
        data.join("last-core-exit.json"),
    ))
}

#[tauri::command]
pub fn core_log_path(app: AppHandle) -> String {
    app.try_state::<CoreState>()
        .map(|state| state.log().display().to_string())
        .unwrap_or_default()
}

#[tauri::command]
pub fn core_status(app: AppHandle) -> serde_json::Value {
    match app.try_state::<CoreState>().as_deref() {
        Some(CoreState::Running(core)) => status_json(core.phase(), &core.log),
        Some(CoreState::Failed { log }) => status_json(Phase::Failed, log),
        None => status_json(Phase::Stopped, Path::new("")),
    }
}

/// The AppImage points GTK at its own copies through the environment. The core, and what it opens (the browser
/// for a sign-in, Claude Code), must see the system's.
#[cfg(target_os = "linux")]
fn leave_appimage(command: &mut Command) {
    if std::env::var_os("APPIMAGE").is_none() {
        return;
    }
    for name in [
        "GTK_DATA_PREFIX",
        "GTK_EXE_PREFIX",
        "GTK_PATH",
        "GTK_THEME",
        "GTK_IM_MODULE_FILE",
        "GDK_PIXBUF_MODULE_FILE",
        "GIO_MODULE_DIR",
        "GI_TYPELIB_PATH",
        "GSETTINGS_SCHEMA_DIR",
    ] {
        command.env_remove(name);
    }
    // The AppImage puts its own folder first in XDG_DATA_DIRS; keep only the system's.
    if let (Some(appdir), Some(dirs)) = (
        std::env::var_os("APPDIR"),
        std::env::var_os("XDG_DATA_DIRS"),
    ) {
        let kept: Vec<PathBuf> = std::env::split_paths(&dirs)
            .filter(|dir| !dir.starts_with(&appdir))
            .collect();
        match std::env::join_paths(kept) {
            Ok(dirs) if !dirs.is_empty() => command.env("XDG_DATA_DIRS", dirs),
            _ => command.env_remove("XDG_DATA_DIRS"),
        };
    }
}

/// Opened from Finder, One gets the system's short PATH, without the engineer's `claude`. Ask the login shell for
/// the PATH his terminal has, and give up after three seconds.
#[cfg(target_os = "macos")]
fn login_path() -> Option<String> {
    use std::io::Read;
    let shell = std::env::var("SHELL")
        .ok()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "/bin/zsh".into());
    let mut child = Command::new(shell)
        .args(["-ilc", r#"printf '<<QSONE_PATH>>%s<<QSONE_END>>' "$PATH""#])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;
    let mut out = child.stdout.take()?;
    let (send, receive) = std::sync::mpsc::channel();
    thread::spawn(move || {
        let mut text = String::new();
        let _ = out.read_to_string(&mut text);
        let _ = send.send(text);
    });
    let text = receive.recv_timeout(Duration::from_secs(3));
    if text.is_err() {
        let _ = child.kill();
    }
    let _ = child.wait();
    let text = text.ok()?;
    let path = text
        .split_once("<<QSONE_PATH>>")?
        .1
        .split_once("<<QSONE_END>>")?
        .0;
    (!path.is_empty()).then(|| path.to_string())
}

/// A Windows job that holds the core and everything it starts. Ending it, or One exiting (even by a crash, which
/// closes the handle), ends them all.
#[cfg(windows)]
mod job {
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
        SetInformationJobObject, TerminateJobObject,
    };

    pub struct Job(HANDLE);

    // SAFETY: a job handle may be used and closed from any thread.
    unsafe impl Send for Job {}

    impl Job {
        pub fn holding(child: &Child) -> Option<Job> {
            // SAFETY: plain Win32 calls with a zeroed struct of the size they are told; the handle is owned by Job.
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    return None;
                }
                let job = Job(handle); // closed on every early return
                let mut limits: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
                let set = SetInformationJobObject(
                    job.0,
                    JobObjectExtendedLimitInformation,
                    std::ptr::from_ref(&limits).cast(),
                    size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );
                if set == 0 || AssignProcessToJobObject(job.0, child.as_raw_handle() as HANDLE) == 0
                {
                    return None;
                }
                Some(job)
            }
        }

        pub fn end(&self) {
            // SAFETY: the handle is open for as long as self lives.
            unsafe { TerminateJobObject(self.0, 1) };
        }
    }

    impl Drop for Job {
        fn drop(&mut self) {
            // SAFETY: the handle is open and closed only here.
            unsafe { CloseHandle(self.0) };
        }
    }
}

#[cfg(test)]
pub mod tests {
    use super::*;

    /// A fresh empty folder for one test.
    pub fn scratch(name: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let dir = std::env::temp_dir().join(format!(
            "qsone-desktop-{name}-{}-{nanos}",
            std::process::id()
        ));
        fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// The dev server's stand-in core (scripts/fixtures/fake-core.mjs): same arguments and secret check, and a
    /// child of its own. Answers its `pids` line once it has printed it.
    pub fn fake_core(log: &Path) -> (Target, Process, Vec<u32>) {
        let script =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../scripts/fixtures/fake-core.mjs");
        let target = fresh_target().unwrap();
        let process = launch(Path::new("node"), &[script.into()], &target, log).unwrap();
        let deadline = Instant::now() + Duration::from_secs(15);
        loop {
            let text = fs::read_to_string(log).unwrap_or_default();
            if let Some(line) = text.lines().find(|line| line.starts_with("pids ")) {
                let pids = line
                    .split_whitespace()
                    .skip(1)
                    .map(|p| p.parse().unwrap())
                    .collect();
                while !healthy(&target) {
                    assert!(Instant::now() < deadline, "the fake core never answered");
                    thread::sleep(Duration::from_millis(50));
                }
                return (target, process, pids);
            }
            assert!(
                Instant::now() < deadline,
                "the fake core never started: {text}"
            );
            thread::sleep(Duration::from_millis(50));
        }
    }

    #[cfg(unix)]
    fn alive(pid: u32) -> bool {
        // SAFETY: signal 0 only asks whether the process exists.
        if unsafe { libc::kill(pid as libc::pid_t, 0) } != 0 {
            return false;
        }
        // A zombie still answers; on Linux its state says it is gone.
        fs::read_to_string(format!("/proc/{pid}/stat"))
            .map(|stat| {
                stat.rsplit(')')
                    .next()
                    .is_some_and(|rest| !rest.trim_start().starts_with('Z'))
            })
            .unwrap_or(true)
    }

    #[cfg(windows)]
    fn alive(pid: u32) -> bool {
        use windows_sys::Win32::Foundation::{CloseHandle, STILL_ACTIVE};
        use windows_sys::Win32::System::Threading::{
            GetExitCodeProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION,
        };
        // SAFETY: the handle is checked, read and closed here.
        unsafe {
            let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
            if handle.is_null() {
                return false;
            }
            let mut code = 0u32;
            let read = GetExitCodeProcess(handle, &mut code);
            CloseHandle(handle);
            read != 0 && code == STILL_ACTIVE as u32
        }
    }

    #[test]
    fn starts_the_core_and_stops_it_with_its_children() {
        let dir = scratch("start");
        let log = dir.join("core.log");
        let (target, mut process, pids) = fake_core(&log);
        assert_eq!(pids.len(), 2, "the fake core and its child");

        let without = agent().get(target.url("/health")).call().unwrap();
        assert_eq!(without.status(), 401);
        assert!(healthy(&target), "with the secret");

        stop(&mut process).unwrap();
        let deadline = Instant::now() + Duration::from_secs(3);
        while pids.iter().any(|&pid| alive(pid)) {
            assert!(
                Instant::now() < deadline,
                "still running after stop: {pids:?}"
            );
            thread::sleep(Duration::from_millis(50));
        }
        let text = fs::read_to_string(&log).unwrap();
        assert!(
            !text.contains(&target.secret),
            "the secret never reaches the log"
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn a_core_that_dies_leaves_its_exit_code_only() {
        let dir = scratch("exit");
        let log = dir.join("core.log");
        let target = fresh_target().unwrap();
        let script =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../scripts/fixtures/fake-core.mjs");
        let args: Vec<OsString> = vec![script.into(), "--fail".into()];
        let process = launch(Path::new("node"), &args, &target, &log).unwrap();
        let core = Arc::new(Core::new(
            target,
            process,
            log,
            dir.join("last-core-exit.json"),
        ));
        core.watch();
        let deadline = Instant::now() + Duration::from_secs(15);
        while core.phase() != Phase::Stopped {
            assert!(
                Instant::now() < deadline,
                "the watcher never saw the core stop"
            );
            thread::sleep(Duration::from_millis(50));
        }
        thread::sleep(Duration::from_millis(100));
        assert_eq!(
            fs::read_to_string(dir.join("last-core-exit.json")).unwrap(),
            r#"{"code":1}"#
        );
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn a_core_stopped_on_purpose_leaves_no_exit_note() {
        let dir = scratch("purpose");
        let log = dir.join("core.log");
        let (target, process, _) = fake_core(&log);
        let core = Arc::new(Core::new(
            target,
            process,
            log,
            dir.join("last-core-exit.json"),
        ));
        core.watch();
        assert_eq!(core.started(), Phase::Up);
        core.stop().unwrap();
        thread::sleep(Duration::from_millis(1200)); // a full watcher pause
        assert_eq!(core.phase(), Phase::Stopped);
        assert!(!dir.join("last-core-exit.json").exists());
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn the_log_moves_aside_past_one_megabyte() {
        let dir = scratch("log");
        let log = dir.join("core.log");
        fs::write(&log, vec![b'x'; 1_100_000]).unwrap();
        drop(open_log(&log, 4242).unwrap());
        assert_eq!(
            fs::metadata(dir.join("core.prev.log")).unwrap().len(),
            1_100_000
        );
        let text = fs::read_to_string(&log).unwrap();
        assert!(
            text.starts_with("---- QS Mind One ") && text.contains("port 4242"),
            "{text}"
        );

        // A small log is kept and added to.
        drop(open_log(&log, 4343).unwrap());
        assert_eq!(fs::read_to_string(&log).unwrap().lines().count(), 2);
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn python_lives_where_the_package_puts_it() {
        let found = python_path(Path::new("res"));
        if cfg!(windows) {
            assert_eq!(found, Path::new("res").join("core").join("python.exe"));
        } else {
            assert_eq!(
                found,
                Path::new("res").join("core").join("bin").join("python3")
            );
        }
    }

    #[test]
    fn the_status_says_the_phase_and_the_log_and_nothing_else() {
        let status = status_json(Phase::Starting, Path::new("/logs/core.log"));
        assert_eq!(
            status,
            serde_json::json!({ "state": "starting", "log": "/logs/core.log" })
        );
        assert_eq!(exit_note(None), r#"{"code":null}"#);
    }
}

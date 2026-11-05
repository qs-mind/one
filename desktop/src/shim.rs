// The fetch shim: in the installed app, every call from the page to the core comes here (ui/src/api.ts). Rust adds
// the secret, which the page never holds, lets through only the core's own routes, and streams the answer back
// over a Tauri Channel: a JSON head, raw chunks batched about every 16 ms, then the end. A file goes up whole
// through `core_upload` instead, as the raw body of the call.

use std::collections::HashMap;
use std::io::Read;
use std::sync::Mutex;
use std::sync::mpsc;
use std::thread;
use std::time::{Duration, Instant};

use tauri::http::{HeaderMap, Method};
use tauri::ipc::{Channel, InvokeBody, InvokeResponseBody, Request, Response};
use tauri::{AppHandle, Manager};

use crate::core::{self, CoreState, Phase, Target};

/// The core's own routes: the first part of every path the page may reach (Plans 1–8).
const PREFIXES: [&str; 16] = [
    "health",
    "about",
    "app",
    "chat",
    "settings",
    "setup",
    "engineer",
    "projects",
    "account",
    "backup",
    "usage",
    "briefs",
    "cards",
    "connectors",
    "costs",
    "meaning",
];

/// Headers that belong to the page or to the hop, never to the call: the core gets the shell's own.
const NOT_FORWARDED: [&str; 13] = [
    "authorization",
    "proxy-authorization",
    "cookie",
    "host",
    "origin",
    "referer",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "upgrade",
    "te",
    "accept-encoding",
];

/// Headers of the core's answer that describe the hop, not the answer.
const NOT_RETURNED: [&str; 4] = [
    "connection",
    "keep-alive",
    "transfer-encoding",
    "set-cookie",
];

const READ_SIZE: usize = 16 * 1024;
const BATCH: Duration = Duration::from_millis(16);

/// Whether the page may reach this path: one of the core's own routes, and nothing that could lead elsewhere.
pub fn allowed(path: &str) -> bool {
    let Some(rest) = path.strip_prefix('/') else {
        return false;
    };
    if path
        .chars()
        .any(|c| c.is_control() || c == ' ' || c == '#' || c == '\\')
    {
        return false;
    }
    let route = path.split_once('?').map_or(path, |(route, _)| route);
    let lower = route.to_ascii_lowercase();
    if route.contains("//")
        || route.contains("..")
        || ["%2e", "%2f", "%5c"].iter().any(|s| lower.contains(s))
    {
        return false;
    }
    let first = rest.split(['/', '?']).next().unwrap_or_default();
    PREFIXES.contains(&first)
}

/// The page's headers that go on to the core: lower-case, without the page's own authorization, host or origin.
pub fn forwarded_headers<N: AsRef<str>, V: AsRef<str>>(
    headers: &[(N, V)],
) -> Vec<(String, String)> {
    headers
        .iter()
        .map(|(name, value)| {
            (
                name.as_ref().trim().to_ascii_lowercase(),
                value.as_ref().to_string(),
            )
        })
        .filter(|(name, _)| {
            !NOT_FORWARDED.contains(&name.as_str()) && !name.starts_with("x-qsone-")
        })
        .filter(|(name, value)| {
            !name.is_empty() && !format!("{name}{value}").contains(['\r', '\n'])
        })
        .collect()
}

/// What the page hears of one call.
#[derive(Debug, PartialEq)]
pub enum Event {
    Head {
        status: u16,
        headers: Vec<(String, String)>,
    },
    Chunk(Vec<u8>),
    End,
    /// `not_allowed`, `bad_call`, `core_down` or `cut_short`. The screen says it in words (ui/src/api.ts).
    Error(&'static str),
}

impl From<Event> for InvokeResponseBody {
    fn from(event: Event) -> Self {
        let json = match event {
            Event::Chunk(bytes) => return InvokeResponseBody::Raw(bytes),
            Event::Head { status, headers } => {
                serde_json::json!({ "event": "head", "status": status, "headers": headers })
            }
            Event::End => serde_json::json!({ "event": "end" }),
            Event::Error(code) => serde_json::json!({ "event": "error", "code": code }),
        };
        InvokeResponseBody::Json(json.to_string())
    }
}

/// One call to the core.
pub struct Call {
    pub method: String,
    pub path: String,
    pub headers: Vec<(String, String)>,
    pub body: Option<Vec<u8>>,
}

fn request(target: &Target, call: &Call) -> Result<ureq::http::request::Builder, &'static str> {
    if !allowed(&call.path) {
        return Err("not_allowed");
    }
    let method =
        Method::from_bytes(call.method.to_ascii_uppercase().as_bytes()).map_err(|_| "bad_call")?;
    let mut builder = ureq::http::Request::builder()
        .method(method)
        .uri(target.url(&call.path));
    for (name, value) in forwarded_headers(&call.headers) {
        builder = builder.header(name, value);
    }
    Ok(builder.header("authorization", target.bearer()))
}

fn run(
    agent: &ureq::Agent,
    target: &Target,
    call: Call,
) -> Result<ureq::http::Response<ureq::Body>, &'static str> {
    let builder = request(target, &call)?;
    let sent = match call.body {
        Some(body) => agent.run(builder.body(body).map_err(|_| "bad_call")?),
        None => agent.run(builder.body(()).map_err(|_| "bad_call")?),
    };
    sent.map_err(|_| "core_down")
}

fn answer_headers(headers: &HeaderMap) -> Vec<(String, String)> {
    headers
        .iter()
        .filter(|(name, _)| !NOT_RETURNED.contains(&name.as_str()))
        .filter_map(|(name, value)| {
            Some((name.as_str().to_string(), value.to_str().ok()?.to_string()))
        })
        .collect()
}

/// Sends the call and streams the answer to `send`, which says false once the page has gone.
pub fn send_call(
    agent: &ureq::Agent,
    target: &Target,
    call: Call,
    mut send: impl FnMut(Event) -> bool,
) {
    let answer = match run(agent, target, call) {
        Ok(answer) => answer,
        Err(code) => {
            send(Event::Error(code));
            return;
        }
    };
    let head = Event::Head {
        status: answer.status().as_u16(),
        headers: answer_headers(answer.headers()),
    };
    if !send(head) {
        return;
    }
    let reader = answer.into_body().into_reader();
    match pump(reader, |bytes| send(Event::Chunk(bytes))) {
        Ok(true) => {
            send(Event::End);
        }
        Ok(false) => {}
        Err(_) => {
            send(Event::Error("cut_short"));
        }
    }
}

/// Reads `reader` in a thread, 16 KB at a time, and hands what came in to `send` about every 16 ms, so a stream
/// of small events costs a few messages a frame, not one each. Ok(false) when `send` says the page has gone.
pub fn pump(
    mut reader: impl Read + Send + 'static,
    mut send: impl FnMut(Vec<u8>) -> bool,
) -> std::io::Result<bool> {
    let (tx, rx) = mpsc::channel::<std::io::Result<Vec<u8>>>();
    thread::spawn(move || {
        let mut buffer = vec![0u8; READ_SIZE];
        loop {
            let piece = match reader.read(&mut buffer) {
                Ok(0) => return,
                Ok(n) => Ok(buffer[..n].to_vec()),
                Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
                Err(e) => Err(e),
            };
            let failed = piece.is_err();
            if tx.send(piece).is_err() || failed {
                return; // the page has gone, or the answer was cut
            }
        }
    });
    // Blocks for the first piece of a batch, then gathers what else comes within BATCH.
    while let Ok(first) = rx.recv() {
        let mut batch = first?;
        let deadline = Instant::now() + BATCH;
        let mut ended = false;
        loop {
            let left = deadline.saturating_duration_since(Instant::now());
            match rx.recv_timeout(left) {
                Ok(piece) => batch.extend_from_slice(&piece?),
                Err(mpsc::RecvTimeoutError::Timeout) => break,
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    ended = true;
                    break;
                }
            }
        }
        if !send(batch) {
            return Ok(false);
        }
        if ended {
            break;
        }
    }
    Ok(true)
}

/// The calls in flight, by the page's id, so `core_cancel` can drop one. A cancel can come before its call has
/// started; the call then never starts.
#[derive(Default)]
pub struct Calls(Mutex<HashMap<String, Slot>>);

enum Slot {
    Running(ureq::Agent),
    Cancelled,
}

impl Calls {
    /// The call's own agent, or None when the page has already cancelled it.
    fn begin(&self, id: &str) -> Option<ureq::Agent> {
        let mut calls = self.0.lock().ok()?;
        if let Some(Slot::Cancelled) = calls.remove(id) {
            return None;
        }
        let agent = core::agent();
        calls.insert(id.to_string(), Slot::Running(agent.clone()));
        Some(agent)
    }

    fn end(&self, id: &str) {
        if let Ok(mut calls) = self.0.lock() {
            calls.remove(id);
        }
    }

    /// Closes the call's connection at once, even while its answer is being read.
    pub fn cancel(&self, id: &str) {
        let Ok(mut calls) = self.0.lock() else { return };
        match calls.remove(id) {
            Some(Slot::Running(agent)) => agent.shutdown(),
            Some(Slot::Cancelled) | None => {
                calls.insert(id.to_string(), Slot::Cancelled);
            }
        }
    }
}

/// The running core, once it has started; an error code when there is none.
fn running(app: &AppHandle) -> Result<std::sync::Arc<core::Core>, &'static str> {
    match app.try_state::<CoreState>().as_deref() {
        Some(CoreState::Running(core)) if core.started() != Phase::Stopped => {
            Ok(std::sync::Arc::clone(core))
        }
        _ => Err("core_down"),
    }
}

#[tauri::command]
pub async fn core_fetch(
    app: AppHandle,
    id: String,
    method: String,
    path: String,
    headers: Vec<(String, String)>,
    body: Option<String>,
    on_event: Channel<InvokeResponseBody>,
) -> Result<(), String> {
    let send = move |event: Event| on_event.send(event.into()).is_ok();
    tauri::async_runtime::spawn_blocking(move || {
        let core = match running(&app) {
            Ok(core) => core,
            Err(code) => {
                send(Event::Error(code));
                return;
            }
        };
        let calls = app.state::<Calls>();
        let Some(agent) = calls.begin(&id) else {
            return;
        };
        let call = Call {
            method,
            path,
            headers,
            body: body.map(String::into_bytes),
        };
        send_call(&agent, &core.target, call, send);
        calls.end(&id);
    })
    .await
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn core_cancel(app: AppHandle, id: String) {
    app.state::<Calls>().cancel(&id);
}

/// A whole answer, for an upload.
#[derive(Debug, PartialEq)]
pub struct Answer {
    pub status: u16,
    pub headers: Vec<(String, String)>,
    pub body: String,
}

fn refused(status: u16) -> Answer {
    Answer {
        status,
        headers: vec![("content-type".into(), "application/json".into())],
        body: "{}".into(),
    }
}

/// Sends a raw body to `x-qsone-path` with `x-qsone-method` (POST by default). The web view can hand over a body
/// that stopped early, so `content-length` must match it, or nothing is sent: a cut file is never saved as whole.
pub fn send_upload(
    agent: &ureq::Agent,
    target: &Target,
    headers: &HeaderMap,
    body: Vec<u8>,
) -> Answer {
    let text = |name: &str| {
        headers
            .get(name)
            .and_then(|v| v.to_str().ok())
            .map(str::trim)
    };
    if text("content-length").and_then(|n| n.parse::<usize>().ok()) != Some(body.len()) {
        return refused(400);
    }
    let Some(path) = text("x-qsone-path").filter(|path| allowed(path)) else {
        return refused(403);
    };
    let mut kept = Vec::new();
    if let Some(kind) = text("content-type") {
        kept.push(("content-type".to_string(), kind.to_string()));
    }
    let call = Call {
        method: text("x-qsone-method").unwrap_or("POST").to_string(),
        path: path.to_string(),
        headers: kept,
        body: Some(body),
    };
    match run(agent, target, call) {
        Ok(mut answer) => {
            let status = answer.status().as_u16();
            let headers = answer_headers(answer.headers());
            match answer
                .body_mut()
                .with_config()
                .limit(64 * 1024 * 1024)
                .read_to_vec()
            {
                Ok(bytes) => Answer {
                    status,
                    headers,
                    body: String::from_utf8_lossy(&bytes).into_owned(),
                },
                Err(_) => refused(502),
            }
        }
        Err("not_allowed") => refused(403),
        Err("bad_call") => refused(400),
        Err(_) => refused(503),
    }
}

#[tauri::command]
pub async fn core_upload(app: AppHandle, request: Request<'_>) -> Result<Response, String> {
    let InvokeBody::Raw(bytes) = request.body() else {
        return Err("core_upload takes the file as the raw body of the call".into());
    };
    let (headers, body) = (request.headers().clone(), bytes.clone());
    let answer = tauri::async_runtime::spawn_blocking(move || match running(&app) {
        Ok(core) => send_upload(&core::agent(), &core.target, &headers, body),
        Err(_) => refused(503),
    })
    .await
    .map_err(|e| e.to_string())?;
    let json = serde_json::json!({ "status": answer.status, "headers": answer.headers, "body": answer.body });
    Ok(Response::new(InvokeResponseBody::Json(json.to_string())))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::tests::{fake_core, scratch};
    use std::io::Write;
    use std::net::TcpListener;

    #[test]
    fn only_the_cores_own_paths_pass() {
        for ok in [
            "/chat",
            "/health",
            "/projects/0123456789abcdef0123456789abcdef/files?name=%D8%B9",
            "/projects/p1/files?name=v1..2.pdf",
            "/meaning/status",
            "/chat/c1/stream",
        ] {
            assert!(allowed(ok), "{ok}");
        }
        for bad in [
            "",
            "chat",
            "//evil.example/x",
            "/../x",
            "/projects/../../etc",
            "http://127.0.0.1:9/x",
            "/chat\r\nHost: x",
            "/admin",
            "/chatter",
            "/projects/%2e%2e/x",
            "/projects\\x",
            "/chat x",
        ] {
            assert!(!allowed(bad), "{bad}");
        }
    }

    #[test]
    fn the_pages_own_auth_and_host_never_reach_the_core() {
        let kept = forwarded_headers(&[
            ("authorization", "Bearer x"),
            ("host", "evil"),
            ("origin", "o"),
            ("content-type", "application/json"),
        ]);
        assert_eq!(
            kept,
            vec![("content-type".to_string(), "application/json".to_string())]
        );
        let kept = forwarded_headers(&[
            ("Authorization", "Bearer x"),
            ("X-Qsone-Path", "/x"),
            ("Accept", "a\r\nb"),
        ]);
        assert!(kept.is_empty(), "{kept:?}");
    }

    #[test]
    fn a_cut_upload_is_refused() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let target = Target::new(listener.local_addr().unwrap().port(), "s".into());
        let mut headers = HeaderMap::new();
        headers.insert(
            "x-qsone-path",
            "/projects/p1/files?name=a.pdf".parse().unwrap(),
        );
        headers.insert("content-length", "10".parse().unwrap());
        let answer = send_upload(&core::agent(), &target, &headers, b"abcd".to_vec());
        assert_eq!(answer.status, 400);
        assert!(listener.accept().is_err(), "nothing is forwarded");

        headers.insert("content-length", "4".parse().unwrap());
        headers.insert("x-qsone-path", "/admin".parse().unwrap());
        assert_eq!(
            send_upload(&core::agent(), &target, &headers, b"abcd".to_vec()).status,
            403
        );
        assert!(listener.accept().is_err(), "nothing is forwarded");
    }

    #[test]
    fn calls_and_uploads_reach_the_core_with_its_secret_only() {
        let dir = scratch("shim");
        let (target, mut process, _) = fake_core(&dir.join("core.log"));

        let mut events = Vec::new();
        let call = Call {
            method: "get".into(),
            path: "/chat?x=1".into(),
            headers: vec![("authorization".into(), "Bearer page".into())],
            body: None,
        };
        send_call(&core::agent(), &target, call, |event| {
            events.push(event);
            true
        });
        let Event::Head { status, .. } = &events[0] else {
            panic!("{events:?}")
        };
        assert_eq!(*status, 200, "the shell's secret, not the page's");
        let body: Vec<u8> = events
            .iter()
            .filter_map(|e| {
                if let Event::Chunk(b) = e {
                    Some(b.clone())
                } else {
                    None
                }
            })
            .flatten()
            .collect();
        assert_eq!(
            String::from_utf8(body).unwrap(),
            r#"{"ok":true,"path":"/chat?x=1"}"#
        );
        assert_eq!(events.last(), Some(&Event::End));

        let mut refused = Vec::new();
        let call = Call {
            method: "GET".into(),
            path: "/admin".into(),
            headers: vec![],
            body: None,
        };
        send_call(&core::agent(), &target, call, |event| {
            refused.push(event);
            true
        });
        assert_eq!(refused, vec![Event::Error("not_allowed")]);

        let mut headers = HeaderMap::new();
        headers.insert(
            "x-qsone-path",
            "/projects/p1/files?name=%D8%B9.pdf".parse().unwrap(),
        );
        headers.insert("content-length", "4".parse().unwrap());
        headers.insert("content-type", "application/pdf".parse().unwrap());
        let answer = send_upload(&core::agent(), &target, &headers, b"%PDF".to_vec());
        assert_eq!(answer.status, 200);
        assert!(
            answer.body.contains("/projects/p1/files?name=%D8%B9.pdf"),
            "{}",
            answer.body
        );

        core::stop(&mut process).unwrap();
        let mut down = Vec::new();
        let call = Call {
            method: "GET".into(),
            path: "/health".into(),
            headers: vec![],
            body: None,
        };
        send_call(&core::agent(), &target, call, |event| {
            down.push(event);
            true
        });
        assert_eq!(down, vec![Event::Error("core_down")]);
        let _ = std::fs::remove_dir_all(dir);
    }

    #[test]
    fn a_stream_arrives_whole_in_batches_and_in_order() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let target = Target::new(listener.local_addr().unwrap().port(), "s".into());
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            let mut seen = [0u8; 4096];
            let n = socket.read(&mut seen).unwrap();
            let request = String::from_utf8_lossy(&seen[..n]).to_string();
            socket
                .write_all(b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\nconnection: close\r\n\r\n")
                .unwrap();
            for i in 0..5 {
                socket
                    .write_all(format!("data: مرحبا {i}\n\n").as_bytes())
                    .unwrap();
                socket.flush().unwrap();
                thread::sleep(Duration::from_millis(if i == 2 { 80 } else { 1 }));
            }
            request
        });
        let mut events = Vec::new();
        let call = Call {
            method: "POST".into(),
            path: "/chat".into(),
            headers: vec![],
            body: Some(b"{}".to_vec()),
        };
        send_call(&core::agent(), &target, call, |event| {
            events.push(event);
            true
        });
        let request = server.join().unwrap();
        assert!(request.contains("authorization: Bearer s"), "{request}");

        let Event::Head { status, headers } = &events[0] else {
            panic!("{events:?}")
        };
        assert_eq!(*status, 200);
        assert!(headers.contains(&("content-type".into(), "text/event-stream".into())));
        assert!(!headers.iter().any(|(name, _)| name == "connection"));
        let chunks: Vec<&Vec<u8>> = events
            .iter()
            .filter_map(|e| {
                if let Event::Chunk(b) = e {
                    Some(b)
                } else {
                    None
                }
            })
            .collect();
        assert!(
            chunks.len() >= 2 && chunks.len() < 5,
            "batched, and the pause splits them: {}",
            chunks.len()
        );
        let text = String::from_utf8(chunks.into_iter().flatten().copied().collect()).unwrap();
        assert_eq!(
            text,
            (0..5)
                .map(|i| format!("data: مرحبا {i}\n\n"))
                .collect::<String>()
        );
        assert_eq!(events.last(), Some(&Event::End));
    }

    #[test]
    fn a_cancelled_call_stops_at_once_even_mid_answer() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let target = Target::new(listener.local_addr().unwrap().port(), "s".into());
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            let mut seen = [0u8; 4096];
            let _ = socket.read(&mut seen);
            let _ = socket.write_all(
                b"HTTP/1.1 200 OK\r\ncontent-type: text/event-stream\r\n\r\n: hello\n\n",
            );
            thread::sleep(Duration::from_secs(10)); // quiet, the way a stream is between events
        });
        let calls = Calls::default();
        calls.cancel("early");
        assert!(
            calls.begin("early").is_none(),
            "a cancel that came first wins"
        );

        let agent = calls.begin("c1").unwrap();
        let started = Instant::now();
        let (tx, rx) = mpsc::channel();
        let call = Call {
            method: "GET".into(),
            path: "/chat/c1/stream".into(),
            headers: vec![],
            body: None,
        };
        let worker = thread::spawn(move || {
            send_call(&agent, &target, call, |event| {
                let _ = tx.send(matches!(event, Event::Chunk(_)));
                true
            });
        });
        assert!(
            rx.recv_timeout(Duration::from_secs(5)).is_ok(),
            "the head came"
        );
        assert!(
            rx.recv_timeout(Duration::from_secs(5)).unwrap(),
            "the first chunk came"
        );
        calls.cancel("c1");
        worker.join().unwrap();
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "it did not wait for the quiet stream"
        );
        drop(server);
    }
}

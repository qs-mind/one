//! ONE's drawing reader: DWG or DXF bytes on stdin, one JSON object on stdout.
//! Exit 0: read. Exit 2: read with repairs or with content left out (`omitted`, `problems`).
//! Exit 1: nothing was read; `{"reason", "file_version", "problems"}` says why.

mod digest;
mod embed;
mod emit;
mod insert;
#[cfg(test)]
mod tests;
#[cfg(test)]
mod tests_cut;
mod text;

use acadrust::io::{
    dwg::{DwgReadOptions, DwgReader},
    dxf::{DxfReader, DxfReaderConfiguration},
};
use digest::{digest, LIMIT};
use serde_json::{json, Value};
use std::io::{Cursor, Read};

const INPUT_LIMIT: u64 = 64 * 1024 * 1024;
const DECOMPRESSED_LIMIT: usize = 128 * 1024 * 1024;
const READS: [&str; 8] = [
    "AC1012", "AC1014", "AC1015", "AC1018", "AC1021", "AC1024", "AC1027", "AC1032",
];
// Content keys: a row of these not kept is content the engineer does not get.
const COUNTED: [&str; 14] = [
    "texts",
    "inserts",
    "closed",
    "hatches",
    "embedded",
    "segments",
    "dimensions",
    "tables",
    "references",
    "blocks",
    "layers",
    "layouts",
    "xrefs",
    "styles",
];

fn read_document(
    name: &str,
    data: Vec<u8>,
    budget: usize,
) -> Result<acadrust::io::read::ReadOutcome, String> {
    if name.to_lowercase().ends_with(".dwg") {
        DwgReader::from_stream_with_options(
            Cursor::new(data),
            DwgReadOptions::failsafe().with_max_decompressed_bytes(budget),
        )
        .read_with_stats()
    } else {
        DxfReader::from_reader(Cursor::new(data))
            .map(|r| {
                r.with_configuration(DxfReaderConfiguration {
                    failsafe: true,
                    ..Default::default()
                })
            })
            .and_then(|r| r.read_with_stats())
    }
    .map_err(|e| e.to_string())
}

fn read_with(name: &str, data: Vec<u8>, budget: usize) -> Result<(Value, i32), String> {
    let dwg = name.to_lowercase().ends_with(".dwg");
    let result = read_document(name, data, budget)?;
    let stats = &result.stats;
    // Failsafe hands back an empty default document when the header cannot be read: nothing
    // of this file was read, and saying "partly read" would not be true.
    if let Some(d) = stats
        .diagnostics
        .iter()
        .find(|d| d.code == "file-header-read-failed")
    {
        return Err(d.message.clone());
    }
    if stats.decoded_source_records == 0 && !stats.diagnostics.is_empty() {
        return Err(stats.diagnostics[0].message.clone());
    }
    let mut out = digest(&result.document, if dwg { "dwg" } else { "dxf" });
    out["stats"] = json!({"source_version":stats.source_version,"records":stats.source_records,
        "decoded":stats.decoded_source_records,"skipped":stats.skipped_source_records,
        "stream_completed":stats.stream_completed,"recovered_errors":stats.recovered_errors});
    out["problems"] = json!(stats.diagnostics);
    for key in COUNTED {
        let kept = out[key].as_array().map(|a| a.len()).unwrap_or(0) as u64;
        let omitted = out["totals"][key]
            .as_u64()
            .unwrap_or(0)
            .saturating_sub(kept);
        if omitted > 0 {
            out["omitted"][key] = json!(omitted);
        }
    }
    let capped = out["limited"] == true;
    if capped {
        out["problems"].as_array_mut().unwrap().push(json!({"code":"output-limit","message":"Output capped; totals include omitted entities"}));
    }
    let code = if stats.recovered() || capped { 2 } else { 0 };
    for key in ["work", "byte_counts", "output_bytes"] {
        out.as_object_mut().unwrap().remove(key);
    }
    Ok((out, code))
}

fn read(name: &str, data: Vec<u8>) -> Result<(Value, i32), String> {
    read_with(name, data, DECOMPRESSED_LIMIT)
}

/// The six bytes a DWG starts with ("AC1032"), or "" when they are not a version.
fn sniff(data: &[u8]) -> String {
    let m: String = data.iter().take(6).map(|b| *b as char).collect();
    let digits = m.len() == 6 && m[2..].chars().all(|c| c.is_ascii_digit());
    if m.starts_with("AC") && digits {
        m
    } else {
        String::new()
    }
}

/// Why nothing was read, as a code the core turns into words.
fn reason(name: &str, version: &str, message: &str) -> &'static str {
    if message.contains("decompressed bytes") || message.contains("exceeds reader limit") {
        "too-large"
    } else if name.to_lowercase().ends_with(".dwg") && version.is_empty() {
        "not-a-dwg"
    } else if message.contains("Unsupported CAD version") {
        "unsupported-version"
    } else {
        "damaged"
    }
}

fn unreadable(name: &str, data: &[u8], message: String) -> Value {
    let version = sniff(data);
    let why = reason(name, &version, &message);
    json!({"problems":[message],"file_version":version,"reason":why})
}

fn run(name: &str, data: Vec<u8>) -> (Value, i32) {
    if data.len() as u64 > INPUT_LIMIT {
        return (
            unreadable(name, &data, "Input exceeds reader limit".into()),
            1,
        );
    }
    let version = sniff(&data);
    let head = data[..data.len().min(16)].to_vec();
    let result = std::panic::catch_unwind(|| read(name, data))
        .unwrap_or_else(|_| Err("Reader could not recover drawing".into()));
    match result {
        Ok((mut out, code)) => {
            out["file_version"] = json!(version);
            (out, code)
        }
        Err(e) => (unreadable(name, &head, e), 1),
    }
}

fn main() {
    let args: Vec<_> = std::env::args().collect();
    if args.iter().any(|a| a == "--version") {
        println!(
            "{}",
            json!({"reader":"qsone-drawings","version":env!("CARGO_PKG_VERSION"),"library":"acadrust 0.6.8","reads":READS,"limit_rows":LIMIT})
        );
        return;
    }
    let name = args
        .windows(2)
        .find(|a| a[0] == "--name")
        .map(|a| a[1].as_str())
        .unwrap_or("");
    let mut data = Vec::new();
    let (out, code) = match std::io::stdin()
        .take(INPUT_LIMIT + 1)
        .read_to_end(&mut data)
    {
        Ok(_) => run(name, data),
        Err(e) => (
            json!({"problems":[e.to_string()],"file_version":"","reason":"damaged"}),
            1,
        ),
    };
    println!("{}", out);
    std::process::exit(code);
}

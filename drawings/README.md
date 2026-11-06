# ONE drawing reader

Receives DWG/DXF bytes on stdin, accepts --name, and emits JSON without temporary drawings.
Build: cargo build --manifest-path drawings/Cargo.toml --release -j 4.
Tests: cargo test --manifest-path drawings/Cargo.toml -j 4.

Exit 0: read; 1: unreadable; 2: recovered or capped. Limits: 64 MiB input,
128 MiB DWG decompression, 24 MiB entity JSON, 20,000 rows per category,
4,096 vertices per outline, eight nested inserts, 200,000 entity visits.
The Python wrapper times out after 30 seconds. Counts on capped drawings are partial.
Curves use sampled polygons for containment and segment-integral areas; circle areas are exact.
Tilted or nonplanar outlines are omitted with a limit diagnostic.
Room matching is a candidate, never a confirmed room. Unknown units produce no area.
PDF room areas require supplied closed vectors and explicit calibration.

## Dependencies and licences

acadrust 0.6.8 is used unmodified; Qiyas is not linked or changed.
The following target dependency inventory is also enforced and included in packaged notices.
Unicode-3.0 appears in unicode-ident, the same version already used by the desktop shell.

| Crate | Version | Licence |
| --- | --- | --- |
| acadrust | 0.6.8 | MPL-2.0 |
| adler2 | 2.0.1 | 0BSD OR MIT OR Apache-2.0 |
| anyhow | 1.0.104 | MIT OR Apache-2.0 |
| bitflags | 2.13.2 | MIT OR Apache-2.0 |
| byteorder | 1.5.0 | Unlicense OR MIT |
| cfg-if | 1.0.5 | MIT OR Apache-2.0 |
| core_detect | 1.0.0 | MIT OR Apache-2.0 |
| crc32fast | 1.5.4 | MIT OR Apache-2.0 |
| crossbeam-deque | 0.8.8 | MIT OR Apache-2.0 |
| crossbeam-epoch | 0.9.21 | MIT OR Apache-2.0 |
| crossbeam-utils | 0.8.23 | MIT OR Apache-2.0 |
| either | 1.19.0 | MIT OR Apache-2.0 |
| encoding_rs | 0.8.44 | (Apache-2.0 OR MIT) AND BSD-3-Clause |
| equivalent | 1.0.3 | Apache-2.0 OR MIT |
| flate2 | 1.1.11 | MIT OR Apache-2.0 |
| foldhash | 0.2.0 | Zlib |
| hashbrown | 0.17.1 | MIT OR Apache-2.0 |
| indexmap | 2.14.2 | Apache-2.0 OR MIT |
| itoa | 1.0.18 | MIT OR Apache-2.0 |
| libc | 0.2.191 | MIT OR Apache-2.0 |
| memchr | 2.8.3 | Unlicense OR MIT |
| memmap2 | 0.9.12 | MIT OR Apache-2.0 |
| minimal-lexical | 0.2.1 | MIT OR Apache-2.0 |
| miniz_oxide | 0.9.1 | MIT OR Zlib OR Apache-2.0 |
| multiversion_no_op | 1.0.0 | Apache-2.0 OR MIT |
| nom | 7.1.3 | MIT |
| oem_cp | 2.1.2 | MIT |
| once_cell | 1.21.4 | MIT OR Apache-2.0 |
| phf | 0.11.3 | MIT |
| phf_shared | 0.11.3 | MIT |
| proc-macro2 | 1.0.107 | MIT OR Apache-2.0 |
| quote | 1.0.47 | MIT OR Apache-2.0 |
| rayon | 1.12.0 | MIT OR Apache-2.0 |
| rayon-core | 1.13.0 | MIT OR Apache-2.0 |
| rustversion | 1.0.23 | MIT OR Apache-2.0 |
| ryu | 1.0.23 | Apache-2.0 OR BSL-1.0 |
| scopeguard | 1.2.0 | MIT OR Apache-2.0 |
| serde | 1.0.229 | MIT OR Apache-2.0 |
| serde_core | 1.0.229 | MIT OR Apache-2.0 |
| serde_derive | 1.0.229 | MIT OR Apache-2.0 |
| serde_json | 1.0.154 | MIT OR Apache-2.0 |
| simd-adler32 | 0.3.10 | MIT |
| simdutf8 | 0.1.5 | MIT OR Apache-2.0 |
| siphasher | 1.0.4 | MIT OR Apache-2.0 |
| syn | 3.0.9 | MIT OR Apache-2.0 |
| thiserror | 2.0.21 | MIT OR Apache-2.0 |
| thiserror-impl | 2.0.21 | MIT OR Apache-2.0 |
| unicode-ident | 1.0.27 | (MIT OR Apache-2.0) AND Unicode-3.0 |
| web-time | 1.1.0 | MIT OR Apache-2.0 |
| zlib-rs | 0.6.8 | Zlib |
| zmij | 1.0.23 | MIT |

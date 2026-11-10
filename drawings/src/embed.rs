//! Objects embedded in a drawing (OLE frames): their stream names, and an Excel package in them.

pub fn hex(data: &[u8]) -> String {
    data.iter().map(|b| format!("{:02x}", b)).collect()
}

pub fn package_stream(storage: &acadrust::compound_file::CompoundStorage) -> Option<Vec<u8>> {
    for entry in &storage.entries {
        match entry {
            acadrust::compound_file::CompoundEntry::Stream(s) if s.name == "Package" => {
                return Some(s.content.encode())
            }
            acadrust::compound_file::CompoundEntry::Storage(s) => {
                if let Some(data) = package_stream(s) {
                    return Some(data);
                }
            }
            _ => {}
        }
    }
    None
}

pub fn stream_names(storage: &acadrust::compound_file::CompoundStorage, names: &mut Vec<String>) {
    for entry in &storage.entries {
        match entry {
            acadrust::compound_file::CompoundEntry::Stream(s) => names.push(s.name.clone()),
            acadrust::compound_file::CompoundEntry::Storage(s) => stream_names(s, names),
        }
    }
}

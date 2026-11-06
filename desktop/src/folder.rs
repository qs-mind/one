use std::collections::HashSet;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

pub struct FileEntry {
    pub path: PathBuf,
    pub name: String,
    pub folder: String,
    pub size: u64,
}

pub fn files(root: &Path) -> Result<Vec<FileEntry>, String> {
    fn walk(path: &Path, relative: &Path, out: &mut Vec<FileEntry>) -> std::io::Result<()> {
        let mut entries = std::fs::read_dir(path)?.collect::<Result<Vec<_>, _>>()?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            let kind = entry.file_type()?;
            if kind.is_symlink() {
                continue;
            }
            if kind.is_dir() {
                walk(&entry.path(), &relative.join(entry.file_name()), out)?;
            } else if kind.is_file() {
                out.push(FileEntry {
                    path: entry.path(),
                    name: entry.file_name().to_string_lossy().into_owned(),
                    folder: relative.to_string_lossy().replace('\\', "/"),
                    size: entry.metadata()?.len(),
                });
            }
        }
        Ok(())
    }
    let mut out = Vec::new();
    let name = root.file_name().ok_or("Select a named folder")?;
    walk(root, Path::new(name), &mut out).map_err(|e| e.to_string())?;
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nested_files_keep_the_selected_folder_and_skip_symlinks() {
        let root = std::env::temp_dir().join(format!("one-folder-sample-{}", std::process::id()));
        std::fs::create_dir_all(root.join("sub")).unwrap();
        std::fs::write(root.join("sub/sample.txt"), "sample").unwrap();
        #[cfg(unix)]
        std::os::unix::fs::symlink(root.join("sub"), root.join("loop")).unwrap();
        let found = files(&root).unwrap();
        std::fs::remove_dir_all(&root).unwrap();
        assert_eq!(found.len(), 1);
        assert_eq!(found[0].name, "sample.txt");
        assert_eq!(found[0].size, 6);
        assert_eq!(
            found[0].folder,
            format!("{}/sub", root.file_name().unwrap().to_str().unwrap())
        );
        assert_eq!(found[0].path, root.join("sub/sample.txt"));
    }
}

/// Only paths returned by the native picker can be read by the page.
#[derive(Default)]
pub struct Selection(Mutex<HashSet<PathBuf>>);

impl Selection {
    pub fn remember(&self, files: &[FileEntry]) -> Result<(), String> {
        let mut selected = self.0.lock().map_err(|e| e.to_string())?;
        selected.extend(files.iter().map(|file| file.path.clone()));
        Ok(())
    }

    pub fn read(&self, path: &Path) -> Result<Vec<u8>, String> {
        let canonical = std::fs::canonicalize(path).map_err(|e| e.to_string())?;
        // A path changed to a symlink after selection is never followed to another file.
        if canonical != path
            || !self
                .0
                .lock()
                .map_err(|e| e.to_string())?
                .contains(&canonical)
        {
            return Err("File was not selected".into());
        }
        let file = std::fs::File::open(canonical).map_err(|e| e.to_string())?;
        let mut bytes = Vec::new();
        file.take(256 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map_err(|e| e.to_string())?;
        if bytes.len() > 256 * 1024 * 1024 {
            return Err("File is too large".into());
        }
        Ok(bytes)
    }
}

#[cfg(test)]
mod selection_tests {
    use super::*;
    #[test]
    fn reads_only_files_enumerated_from_the_native_choice() {
        let root = std::env::temp_dir().join(format!("one-selected-sample-{}", std::process::id()));
        std::fs::create_dir_all(root.join("chosen")).unwrap();
        std::fs::write(root.join("chosen/sample.txt"), "sample").unwrap();
        std::fs::write(root.join("other.txt"), "private").unwrap();
        let root = root.canonicalize().unwrap();
        let selected = Selection::default();
        assert!(selected.read(&root.join("chosen/sample.txt")).is_err());
        selected
            .remember(&files(&root.join("chosen")).unwrap())
            .unwrap();
        assert_eq!(
            selected.read(&root.join("chosen/sample.txt")).unwrap(),
            b"sample"
        );
        assert!(selected.read(&root.join("other.txt")).is_err());
        #[cfg(unix)]
        {
            std::fs::remove_file(root.join("chosen/sample.txt")).unwrap();
            std::os::unix::fs::symlink(root.join("other.txt"), root.join("chosen/sample.txt"))
                .unwrap();
            assert!(selected.read(&root.join("chosen/sample.txt")).is_err());
        }
        std::fs::remove_dir_all(root).unwrap();
    }
}

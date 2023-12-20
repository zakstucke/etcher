use std::path::PathBuf;

#[derive(Debug)]
pub struct Template {
    pub path: PathBuf,
    pub rel_path: String,
    pub out_path: PathBuf,
}

impl Template {
    pub fn new(root: PathBuf, path: PathBuf, out_path: PathBuf) -> Self {
        Self {
            // Need to make the path relative to the root:
            rel_path: path
                .strip_prefix(&root)
                .expect("Template path not relative to root")
                .to_string_lossy()
                .to_string(),
            path,
            out_path,
        }
    }
}

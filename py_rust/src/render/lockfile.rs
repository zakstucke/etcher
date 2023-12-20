use std::{
    collections::{HashMap, HashSet},
    fs,
    path::PathBuf,
};

use bitbazaar::errors::TracedErr;
use log::{debug, warn};

use super::template;
pub static LOCKFILE_NAME: &str = ".etch.lock";

#[derive(Debug, serde::Serialize, serde::Deserialize)]
struct Contents {
    version: String,
    // The relative filepath to the hashed contents:
    files: HashMap<String, String>,
}

impl Contents {
    pub fn default() -> Self {
        Self {
            version: env!("CARGO_PKG_VERSION").to_string(),
            files: HashMap::new(),
        }
    }
}

pub struct Lockfile {
    filepath: PathBuf,
    seen_template_paths: HashSet<String>,
    contents: Contents,
    pub modified: bool,
}

impl Lockfile {
    pub fn load(root: PathBuf, force: bool) -> Self {
        let filepath = root.join(LOCKFILE_NAME);
        let mut modified = false;

        let contents = if force {
            modified = true;
            warn!("Cli forced lockfile override.");
            Contents::default()
        } else {
            let str_contents = match fs::read_to_string(&filepath) {
                Ok(contents) => Some(contents),
                Err(err) => {
                    warn!(
                        "Starting lockfile afresh, failed to read existing at '{}': {}",
                        filepath.display(),
                        err
                    );
                    None
                }
            };

            match str_contents {
                Some(str_contents) => match serde_json::from_str::<Contents>(&str_contents) {
                    Ok(contents) => {
                        if contents.version != env!("CARGO_PKG_VERSION") {
                            warn!(
                                "Starting lockfile afresh, version mismatch: {} != {}",
                                contents.version,
                                env!("CARGO_PKG_VERSION")
                            );
                            modified = true;
                            Contents::default()
                        } else {
                            debug!(
                                "Loaded lockfile from '{}' successfully.",
                                filepath.display()
                            );
                            contents
                        }
                    }
                    Err(err) => {
                        warn!(
                            "Starting lockfile afresh, failed to parse existing at '{}': {}",
                            filepath.display(),
                            err
                        );
                        modified = true;
                        Contents::default()
                    }
                },
                None => {
                    debug!(
                        "Couldn't find existing lockfile, creating new at '{}'",
                        filepath.display()
                    );
                    modified = true;
                    Contents::default()
                }
            }
        };

        Self {
            filepath,
            contents,
            seen_template_paths: HashSet::new(),
            modified,
        }
    }

    /// After compiling a template run this, it will update the lockfile and write the compiled template to disk.
    ///
    /// Returns true when added, false when identical already present in lockfile.
    pub fn add_template(
        &mut self,
        template: &template::Template,
        compiled: String,
    ) -> Result<bool, TracedErr> {
        // To prevent bloating the filesize and readability of the lockfile, only include a hash of the compiled template rather than the full contents.
        let hashed = bitbazaar::hash::fnv1a(compiled.as_bytes()).to_string();
        let identical = if let Some(old_hashed) = self.contents.files.get(&template.rel_path) {
            if old_hashed != &hashed {
                debug!(
                    "Template '{}' has changed, updating lockfile and rewriting.",
                    template.rel_path
                );
                self.modified = true;
                false
            } else {
                debug!(
                    "Template '{}' has identical hash in lockfile, skipping.",
                    template.rel_path
                );
                true
            }
        } else {
            debug!(
                "Template '{}' didn't exist in lockfile prior, updating lockfile and rewriting.",
                template.rel_path
            );
            self.modified = true;
            false
        };

        // Only update if not already identical:
        if !identical {
            self.modified = true;
            self.contents
                .files
                .insert(template.rel_path.clone(), hashed);

            // Write the compiled file:
            fs::write(template.out_path.clone(), compiled)?;
        }

        self.seen_template_paths.insert(template.rel_path.clone());

        Ok(!identical)
    }

    /// After all compiled templates have been added, run this to close out and save the lockfile.
    pub fn sync(&mut self) -> Result<(), TracedErr> {
        let before_len = self.contents.files.len();
        // Anything which isn't in the new compiled set should be removed from the lockfile:
        self.contents
            .files
            .retain(|template_path, _| self.seen_template_paths.contains(template_path));

        if self.contents.files.len() != before_len {
            debug!(
                "Removed {} templates from lockfile which no longer exist.",
                before_len - self.contents.files.len()
            );
            self.modified = true;
        }

        if self.modified {
            // Write the updated lockfile
            debug!("Writing updated lockfile to '{}'", self.filepath.display());
            fs::write(
                &self.filepath,
                serde_json::to_string_pretty(&self.contents)?,
            )?;
        }

        Ok(())
    }
}

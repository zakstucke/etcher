use std::path::PathBuf;

use bitbazaar::{err, errors::TracedErr};
use log::info;

use crate::args::{InitCommand, DEFAULT_CONFIG_PATH};

/// Initialize the config file in the current directory.
pub fn init(_args: InitCommand) -> Result<(), TracedErr> {
    // Raise if config file already exists:
    if PathBuf::from(&DEFAULT_CONFIG_PATH).exists() {
        return Err(err!(
            "Config file already exists at the default location: '{}'.",
            DEFAULT_CONFIG_PATH
        ));
    }

    // Check if a .gitignore file exists in the current directory:
    let gitignore_path = PathBuf::from(".gitignore");
    let gitignore_exists = gitignore_path.exists();

    std::fs::write(DEFAULT_CONFIG_PATH, get_default_conf(gitignore_exists)).map_err(|e| {
        err!(
            "Failed to write config file to '{}': '{}'.",
            DEFAULT_CONFIG_PATH,
            e
        )
    })?;

    info!(
        "Successfully wrote config file to '{}'.",
        DEFAULT_CONFIG_PATH
    );

    Ok(())
}

fn get_default_conf(gitignore_exists: bool) -> String {
    format!(
        r#"#:schema https://github.com/zakstucke/etcher/blob/v{}/py_rust/src/config/schema.json

ignore_files = [{}] {}

exclude = []

[engine]
keep_trailing_newline = true
allow_undefined = false
custom_extensions = []

[context.static]
FOO = {{ value = "foo" }}

[context.env]
BAR = {{ default = "bar" }}

[context.cli]
BAZ = {{ commands = ["echo 1"], coerce = "int" }}
"#,
        env!("CARGO_PKG_VERSION"),
        if gitignore_exists {
            "\".gitignore\""
        } else {
            ""
        },
        if gitignore_exists {
            ""
        } else {
            "# Couldn't find a .gitignore, not adding by default. Recommended if available."
        }
    )
}

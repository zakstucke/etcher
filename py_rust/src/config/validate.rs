use std::path::{Path, PathBuf};

use bitbazaar::{err, errors::TracedErr};
use once_cell::sync::Lazy;
use regex::Regex;

use super::RawConfig;

// Include the schema in the binary to use at runtime:
static JSON_SCHEMA: &str = include_str!(r"./schema.json");

pub fn pre_validate(value: &serde_json::Value) -> Result<(), TracedErr> {
    let state = run_against_schema(value)?;
    if !state.is_strictly_valid() {
        return Err(err!(
            "{}",
            state
                .errors
                .into_iter()
                .map(format_err)
                .collect::<Vec<String>>()
                .join("\n")
        ));
    }

    Ok(())
}

/// Extra validation & cleaning to do on the created config object.
pub fn post_validate(conf: &mut RawConfig, config_path: &Path) -> Result<(), TracedErr> {
    // Check stat.value is not empty string, plus same for env.default (if provided):
    for (key, value) in conf.context.stat.iter() {
        validate_not_empty_string(format!("[context.static.{}.value]", key), &value.value)?;
    }

    for (key, value) in conf.context.env.iter() {
        if let Some(default) = &value.default {
            validate_not_empty_string(format!("[context.env.{}.default]", key), default)?;
        }
    }

    // ignore_files and engine.custom_extensions should be resolved relative to the config file, so rewrite the paths if needed and make sure they exist:
    let validate_and_rewrite = |in_path: String| -> Result<String, TracedErr> {
        // Make relative to config file if not absolute:
        let path = if !PathBuf::from(&in_path).is_absolute() {
            config_path
                .parent()
                .unwrap()
                .join(in_path)
                .to_str()
                .unwrap()
                .to_string()
        } else {
            in_path
        };

        // Make sure exists:
        if !PathBuf::from(&path).exists() {
            return Err(err!("Path '{}' does not exist. Note relative paths are resolved from the config file directory.", path));
        }

        Ok(path)
    };

    for ignore_file in conf.ignore_files.iter_mut() {
        *ignore_file = validate_and_rewrite(ignore_file.clone())?;

        // Make sure is a file:
        if !PathBuf::from(&ignore_file).is_file() {
            return Err(err!("Path '{}' is not a file.", ignore_file));
        }
    }

    for user_extension in conf.engine.custom_extensions.iter_mut() {
        *user_extension = validate_and_rewrite(user_extension.clone())?;

        let path = PathBuf::from(&user_extension);
        // If it's a dir, make sure it has an __init__.py file:
        if path.is_dir() {
            let init_file = path.join("__init__.py");
            if !init_file.exists() {
                return Err(err!(
                    "Custom extension '{}' is a directory but does not contain an __init__.py file, not a valid package.",
                    user_extension
                ));
            }
        } else {
            // Otherwise make sure its a .py file:
            let extension = path.extension().unwrap_or_default();
            if extension != "py" {
                return Err(err!(
                    "Custom extension '{}' is not a .py file.",
                    user_extension
                ));
            }
        }
    }

    Ok(())
}

/// Because we're hacking together toml validation using a json parser, format the errors a bit more applicably where possible.
fn format_err(err: Box<dyn valico::common::error::ValicoError>) -> String {
    // Want the actual detail, only use title if detail is missing (crates cli seems to state title is always available but detail not so. But detail seems to always be there.)
    let info = if let Some(detail) = err.get_detail() {
        detail
    } else {
        err.get_title()
    };

    let loc_parts = err
        .get_path()
        .split('/')
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>();

    let loc_str = if loc_parts.is_empty() {
        "[root]: ".to_string()
    } else {
        format!("[{}]: ", loc_parts.join("."))
    };

    let mut desc = info.to_string();

    if let Some(extra) = err_extra_property(&desc) {
        desc = format!("Unknown property: '{}'.", extra);
    } else if let Some(invalid_type) = err_invalid_type(&desc) {
        desc = format!(
            "Expected {}.",
            match invalid_type.as_str() {
                "object" => "a table".to_string(),
                "array" => "an array".to_string(),
                _ => format!("a {}", invalid_type),
            }
        );
    } else if err_coerce_invalid(&loc_parts, &desc) {
        desc = "Expected one of ['json', 'str', 'int', 'float', 'bool'].".to_string();
    }

    format!(
        "{}{}{}",
        loc_str,
        desc,
        if desc.ends_with('.') { "" } else { "." }
    )
}

static RE_ENUM_UNMATCHED: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"Enum conditions are not met").expect("Invalid regex pattern"));

fn err_coerce_invalid(loc_parts: &[&str], desc: &str) -> bool {
    // If its the enum err and it's talking about coerce, then it's our error.
    if loc_parts.last() != Some(&"coerce") {
        return false;
    }
    RE_ENUM_UNMATCHED.is_match(desc)
}

static RE_EXTRA_PROP: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r"Additional property '([^']*)' is not allowed").expect("Invalid regex pattern")
});

fn err_extra_property(desc: &str) -> Option<String> {
    RE_EXTRA_PROP
        .captures(desc)
        .map(|caps| caps.get(1).unwrap().as_str().to_string())
}

static RE_INVALID_TYPE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"The value must be ([^']*)").expect("Invalid regex pattern"));

fn err_invalid_type(desc: &str) -> Option<String> {
    RE_INVALID_TYPE
        .captures(desc)
        .map(|caps| caps.get(1).unwrap().as_str().to_string())
}

fn run_against_schema(
    json: &serde_json::Value,
) -> Result<valico::json_schema::ValidationState, TracedErr> {
    let json_schema: serde_json::Value = serde_json::from_str(JSON_SCHEMA)?;
    let mut scope = valico::json_schema::Scope::new();
    let schema = scope.compile_and_return(json_schema, true)?;
    Ok(schema.validate(json))
}

fn validate_not_empty_string(context: String, value: &serde_json::Value) -> Result<(), TracedErr> {
    let valid = match &value {
        serde_json::Value::String(s) => !s.trim().is_empty(),
        _ => true,
    };
    if valid {
        Ok(())
    } else {
        Err(err!("{}: Cannot be an empty string.", context))
    }
}

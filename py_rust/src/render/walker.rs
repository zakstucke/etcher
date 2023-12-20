use bitbazaar::{err, errors::TracedErr};
use ignore::{overrides::OverrideBuilder, WalkBuilder};
use log::debug;
use once_cell::sync::Lazy;
use regex::Regex;

use super::lockfile::LOCKFILE_NAME;
use crate::{args::RenderCommand, config::Config};

pub fn create(render_args: &RenderCommand, conf: &Config) -> Result<WalkBuilder, TracedErr> {
    let mut builder = WalkBuilder::new(&render_args.root);
    builder.git_exclude(false); // Don't auto read .git/info/exclude
    builder.git_global(false); // Don't auto use a global .gitignore file
    builder.git_ignore(false); // Don't auto use .gitignore file
    builder.ignore(false); // Don't auto use .ignore file
    builder.require_git(false); // Works better when not in a git repo
    builder.hidden(false); // Doesn't auto ignore hidden files

    for ignore_file in conf.ignore_files.iter() {
        builder.add_ignore(ignore_file);
    }

    // Don't ever match the target config file or the lockfile:
    let mut all_excludes = vec![
        render_args.config.display().to_string(),
        LOCKFILE_NAME.to_string(),
    ];

    // Add in config supplied excludes:
    all_excludes.extend(conf.exclude.iter().map(|s| s.to_string()));

    let mut overrider: OverrideBuilder = OverrideBuilder::new(&render_args.root);
    for exclude in all_excludes.iter() {
        // The override adder is the opposite, i.e. a match is a whitelist, so need to invert the exclude pattern provided:
        let trimmed = exclude.trim();
        let inverted = if trimmed.starts_with('!') {
            // Remove the leading "!" to invert:
            trimmed
                .strip_prefix('!')
                .ok_or_else(|| err!("Failed to strip leading '!' from exclude: {}", trimmed))?
                .to_string()
        } else {
            // Add a leading "!" to invert:
            format!("!{}", trimmed)
        };
        overrider.add(&inverted)?;
    }

    builder.overrides(overrider.build()?);

    Ok(builder)
}

static MIDDLE_MATCHER: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(.*)(\.etch\.)(.*)").expect("Regex failed to compile"));

static END_MATCHER: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(.*)(\.etch)$").expect("Regex failed to compile"));

fn try_regexes_get_match(filename: &str) -> Option<String> {
    if let Some(caps) = MIDDLE_MATCHER.captures(filename) {
        return Some(format!(
            "{}.{}",
            caps.get(1).map_or("", |m| m.as_str()),
            caps.get(3).map_or("", |m| m.as_str())
        ));
    }

    if let Some(caps) = END_MATCHER.captures(filename) {
        return Some(caps.get(1).map_or("", |m| m.as_str()).to_string());
    }

    None
}

pub fn find_templates(
    render_args: &RenderCommand,
    walker: WalkBuilder,
) -> Result<Vec<super::template::Template>, TracedErr> {
    let mut templates = vec![];
    let mut files_checked = 0;
    for entry in walker.build() {
        let entry = entry?;
        if entry.file_type().map(|ft| ft.is_file()).unwrap_or(false) {
            let filename = entry.file_name().to_string_lossy();
            if let Some(compiled_name) = try_regexes_get_match(&filename) {
                templates.push(super::template::Template::new(
                    render_args.root.clone(),
                    entry.path().to_path_buf(),
                    // Replacing the name with the compiled name:
                    entry.path().parent().unwrap().join(compiled_name),
                ));
            }
        }
        files_checked += 1;
    }

    debug!(
        "Checked {} unignored files to find {} templates.",
        files_checked,
        templates.len()
    );

    Ok(templates)
}

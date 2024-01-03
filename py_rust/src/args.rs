use std::path::PathBuf;

use bitbazaar::{err, errors::TracedErr};
use clap::{command, Parser};
use pyo3::Python;

pub static DEFAULT_CONFIG_PATH: &str = "./etch.config.toml";

/// Get the args from python rather than rust, works better:
pub fn get_py_args() -> Result<Vec<String>, TracedErr> {
    Python::with_gil(|py| {
        Ok::<_, TracedErr>(
            py.import("sys")?
                .getattr("argv")?
                .extract::<Vec<String>>()?,
        )
    })
}

// Create the version info string, used in multiple places so need to centralize logic.
pub fn get_version_info() -> String {
    let inner = || {
        let py_args = get_py_args()?;
        let bin_path = py_args
            .first()
            .ok_or_else(|| err!("Failed to get binary path from args: '{:?}'.", py_args))?
            .clone();
        Ok::<_, TracedErr>(format!("{} ({})", env!("CARGO_PKG_VERSION"), bin_path))
    };
    match inner() {
        Ok(s) => s,
        Err(e) => {
            format!("Failed to get version info: {}", e)
        }
    }
}

#[derive(Debug, Parser)]
#[command(
    author,
    name = "etch",
    about = "Etch: An extremely fast metaprogrammer.",
    after_help = "For help with a specific command, see: `etch help <command>`."
)]
#[command(version = get_version_info())]
pub struct Args {
    #[command(subcommand)]
    pub command: Command,
    #[clap(flatten)]
    pub log_level_args: bitbazaar::logging::ClapLogLevelArgs,
}

#[derive(Debug, clap::Subcommand)]
pub enum Command {
    /// Render all templates found whilst traversing the given root (default).
    Render(RenderCommand),
    /// Initialize the config file in the current directory.
    Init(InitCommand),
    /// Display Etch's version
    Version {
        #[arg(long, value_enum, default_value = "text")]
        output_format: HelpFormat,
    },
}

#[derive(Clone, Debug, clap::Parser)]
pub struct RenderCommand {
    /// The target directory to search and render.
    #[clap(
        default_value = ".",
        help = "The target directory to search and compile."
    )]
    pub root: PathBuf,
    /// The config file to use.
    #[arg(
        short,
        long,
        default_value = DEFAULT_CONFIG_PATH,
        help = "The config file to use."
    )]
    pub config: PathBuf,
    /// Force write all rendered files, ignore existing lockfile.
    #[arg(
        short,
        long,
        default_value = "false",
        help = "Force write all rendered files, ignore existing lockfile."
    )]
    pub force: bool,
    /// Hidden test flag, writes some json output to the root dir.
    #[arg(
        long,
        default_value = "false",
        help = "Force write all rendered files, ignore existing lockfile.",
        hide = true
    )]
    pub debug: bool,
}

#[derive(Clone, Debug, clap::Parser)]
pub struct InitCommand {}

#[derive(Debug, Clone, Copy, clap::ValueEnum)]
pub enum HelpFormat {
    Text,
    Json,
}

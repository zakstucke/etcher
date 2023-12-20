use std::path::PathBuf;

use clap::{command, Parser};

pub static DEFAULT_CONFIG_PATH: &str = "./etch.config.toml";

#[derive(Debug, Parser)]
#[command(
    author,
    name = "etch",
    about = "Etch: An extremely fast metaprogrammer.",
    after_help = "For help with a specific command, see: `etch help <command>`."
)]
#[command(version)]
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

use bitbazaar::{
    errors::TracedErr,
    logging::{setup_logger, LogTarget},
    timing::GLOBAL_TIME_RECORDER,
};
use clap::{Parser, Subcommand};
use log::debug;

use crate::{
    args::{self, get_py_args, get_version_info},
    init, render, ETCH_ROOT_ARGS,
};

pub fn run() -> Result<(), TracedErr> {
    let mut py_args = get_py_args()?;

    // Clap doesn't support default subcommands but we want to run `render` by
    // default for convenience, so we just preprocess the arguments accordingly before passing them to Clap.
    let arg1 = py_args.get(1);
    let add = {
        if let Some(arg1) = arg1 {
            // If the first argument isn't already a subcommand, and isn't a specific root arg/option, true:
            !args::Command::has_subcommand(arg1) && !ETCH_ROOT_ARGS.contains(&arg1.as_str())
        } else {
            true
        }
    };
    if add {
        py_args.insert(1, "render".into());
    }

    let args = args::Args::parse_from(py_args);

    let logger = setup_logger(vec![LogTarget {
        msg_prefix: Some("etch".to_string()),
        level_filter: args.log_level_args.level_filter(),
        include_ts_till: Some(log::LevelFilter::Debug),
        variant: bitbazaar::logging::LogTargetVariant::Stdout {},
        ..Default::default()
    }])?;
    logger.apply()?;

    let result = match args.command {
        args::Command::Render(render) => {
            render::render(render)?;
            Ok(())
        }
        args::Command::Init(init) => Ok(init::init(init)?),
        args::Command::Version { output_format: _ } => {
            println!("etch {}", get_version_info());
            Ok(())
        }
    };

    debug!("{}", GLOBAL_TIME_RECORDER.format_verbose()?);

    result
}

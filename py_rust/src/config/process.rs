use std::collections::HashMap;

use bitbazaar::{cli::run_cmd, err, errors::TracedErr, timeit};
use log::info;
use serde::Serialize;

use super::{engine::Engine, raw_conf::RawConfig};

#[derive(Debug, Serialize)]
pub struct Config {
    pub context: HashMap<String, serde_json::Value>,
    pub exclude: Vec<String>,
    pub engine: Engine,
    pub ignore_files: Vec<String>,
    pub setup_commands: Vec<String>,
}

pub fn process(raw: RawConfig) -> Result<Config, TracedErr> {
    let mut context: HashMap<String, serde_json::Value> = HashMap::new();

    // Before anything else, run the setup commands:
    for command in raw.setup_commands.iter() {
        info!("Running command: {}", command);
        let cmd_out = timeit!(format!("Setup cmd: {}", command).as_str(), {
            run_cmd(command)
        })?;

        info!("{}", cmd_out.stdout);

        if cmd_out.code != 0 {
            return Err(err!(
                "Setup command '{}' returned non zero exit code: {}",
                command,
                cmd_out.code
            ));
        }
    }

    for (key, value) in raw.context.stat {
        context.insert(key, value.consume()?);
    }

    for (key, value) in raw.context.env {
        context.insert(key.clone(), value.consume(&key)?);
    }

    // External commands can be extremely slow compared to the rest of the library,
    // try and remedy a bit by running them in parallel:
    let mut handles = vec![];
    for (key, value) in raw.context.cli {
        handles.push(std::thread::spawn(
            move || -> Result<(String, serde_json::Value), TracedErr> {
                let value = value.consume()?;
                Ok((key, value))
            },
        ));
    }
    for handle in handles {
        let (key, value) = handle.join().unwrap()?;
        context.insert(key, value);
    }

    Ok(Config {
        context,
        exclude: raw.exclude,
        engine: raw.engine,
        ignore_files: raw.ignore_files,
        setup_commands: raw.setup_commands,
    })
}

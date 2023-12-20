use std::{collections::HashMap, fs, path::PathBuf};

use bitbazaar::{
    cli::{run_cmd, CmdOut},
    err,
    errors::TracedErr,
    timeit,
};
use log::info;
use serde::{Deserialize, Serialize};

use super::{coerce, engine::Engine};
use crate::args::RenderCommand;

// String literal of json, str, int, float, bool:
#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Coerce {
    Json,
    Str,
    Int,
    Float,
    Bool,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct CtxStaticVar {
    pub value: serde_json::Value,
    pub coerce: Option<Coerce>,
}

impl CtxStaticVar {
    pub fn consume(self) -> Result<serde_json::Value, TracedErr> {
        coerce(self.value, self.coerce)
    }
}

#[derive(Debug, Deserialize, Serialize)]
pub struct CtxEnvVar {
    pub env_name: Option<String>,
    pub default: Option<serde_json::Value>,
    pub coerce: Option<Coerce>,
}

impl CtxEnvVar {
    pub fn consume(self, key_name: &str) -> Result<serde_json::Value, TracedErr> {
        let env_name = match self.env_name {
            Some(env_name) => env_name,
            None => key_name.to_string(),
        };

        let value = match std::env::var(&env_name) {
            Ok(value) => value,
            Err(_) => match self.default {
                Some(value) => return Ok(value),
                None => {
                    return Err(err!(
                        "Could not find environment variable '{}' and no default provided.",
                        env_name
                    ))
                }
            },
        };

        let value = serde_json::Value::String(value);

        coerce(value, self.coerce)
    }
}

#[derive(Debug, Deserialize, Serialize)]
pub struct CtxCliVar {
    pub commands: Vec<String>,
    pub coerce: Option<Coerce>,
}

impl CtxCliVar {
    pub fn consume(self) -> Result<serde_json::Value, TracedErr> {
        let commands = self.commands;

        let runner = |command: &str| -> Result<CmdOut, TracedErr> {
            info!("Running command: {}", command);
            let cmd_out = timeit!(format!("Cmd: {}", command).as_str(), { run_cmd(command) })?;

            if cmd_out.code != 0 {
                return Err(err!(
                    "Command '{}' returned non zero exit code: {}",
                    command,
                    cmd_out.code
                ));
            }

            Ok(cmd_out)
        };

        // Run each command before the last:
        for command in commands[..commands.len() - 1].iter() {
            runner(command)?;
        }

        // Run the last and store its stdout as the value:
        let cmd_out = runner(&commands[commands.len() - 1])?;
        if cmd_out.stdout.trim().is_empty() {
            return Err(err!(
                "Implicit None. Final cli script returned nothing. Command '{}'.",
                &commands[commands.len() - 1]
            ));
        }
        let value = serde_json::Value::String(cmd_out.stdout);

        coerce(value, self.coerce)
    }
}

#[derive(Debug, Deserialize, Serialize)]
pub struct Context {
    #[serde(rename(deserialize = "static"))]
    #[serde(default = "HashMap::new")]
    pub stat: HashMap<String, CtxStaticVar>,

    #[serde(default = "HashMap::new")]
    pub env: HashMap<String, CtxEnvVar>,

    #[serde(default = "HashMap::new")]
    pub cli: HashMap<String, CtxCliVar>,
}

impl Context {
    pub fn default() -> Self {
        Self {
            stat: HashMap::new(),
            env: HashMap::new(),
            cli: HashMap::new(),
        }
    }
}

#[derive(Debug, Deserialize, Serialize)]
pub struct RawConfig {
    // All should be optional to allow empty config file, even though it wouldn't make too much sense!
    #[serde(default = "Context::default")]
    pub context: Context,
    #[serde(default = "Vec::new")]
    pub exclude: Vec<String>,
    #[serde(default = "Engine::default")]
    pub engine: Engine,
    #[serde(default = "Vec::new")]
    pub ignore_files: Vec<String>,
    #[serde(default = "Vec::new")]
    pub setup_commands: Vec<String>,
}

impl RawConfig {
    pub fn from_toml(render_args: &RenderCommand) -> Result<Self, TracedErr> {
        // If the config path is relative, make relative to the root:
        let config_path = match render_args.config.is_relative() {
            true => render_args.root.join(&render_args.config),
            false => render_args.config.clone(),
        };

        match RawConfig::from_toml_inner(&config_path) {
            Ok(config) => Ok(config),
            Err(e) => Err(e.modify_msg(|msg| {
                format!(
                    "Error reading config file from '{}'.\n{}",
                    config_path.display(),
                    msg
                )
            })),
        }
    }

    fn from_toml_inner(config_path: &PathBuf) -> Result<Self, TracedErr> {
        let contents = match fs::read_to_string(config_path) {
            Ok(c) => c,
            Err(e) => return Err(err!("Failed file read: '{}'.", e)),
        };

        // Decode directly the toml directly into serde/json, using that internally:
        let json: serde_json::Value = match toml::from_str(&contents) {
            Ok(toml) => toml,
            Err(e) => return Err(err!("Invalid toml formatting: '{}'.", e)),
        };

        // This will check against the json schema,
        // can produce much better errors than the toml decoder can, so prevalidate first:
        super::validate::pre_validate(&json)?;

        // Now deserialize after validation:
        let mut config: RawConfig = serde_json::from_value(json)?;

        super::validate::post_validate(&mut config, config_path)?;

        Ok(config)
    }
}

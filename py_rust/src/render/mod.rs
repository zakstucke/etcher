use bitbazaar::{
    err,
    errors::TracedErr,
    timeit,
    timing::{format_duration, GLOBAL_TIME_RECORDER},
};
use log::{debug, info};
use minijinja::context;

mod args_validate;
mod debug;
mod lockfile;
mod template;
mod walker;
use crate::{args::RenderCommand, config};

pub fn render(render_args: RenderCommand) -> Result<bool, TracedErr> {
    args_validate::args_validate(&render_args)?;

    let raw_conf = timeit!("Config processing", {
        config::RawConfig::from_toml(&render_args)
    })?;

    let conf = timeit!("Context value extraction (including scripting)", {
        config::process(raw_conf)
    })?;

    let walker = timeit!("Filesystem walker creation", {
        self::walker::create(&render_args, &conf)
    })?;

    let templates = timeit!("Traversing filesystem & identifying templates", {
        self::walker::find_templates(&render_args, walker)
    })?;

    let mut lockfile = timeit!("Lockfile preparation", {
        self::lockfile::Lockfile::load(render_args.root.clone(), render_args.force)
    });

    let mut identical = Vec::new();
    let mut written = Vec::new();

    // Create the minijinja environment with the context.
    // A loader is set that can automatically load templates, this means it can load the main templates, and any other "includes" in user templates too.
    let env = timeit!("Creating rendering environment", {
        conf.engine
            .create_minijinja_env(&render_args.root, &conf.context)
    })?;

    timeit!("Rendering templates & syncing files", {
        for template in templates.iter() {
            debug!("Rendering template: {}", template.rel_path);
            let tmpl = env.get_template(&template.rel_path)?;
            let compiled = match tmpl.render(context! {}) {
                Ok(compiled) => compiled,
                Err(e) => return Err(err!("Failed to render template: '{}'", e)),
            };
            let is_new = lockfile.add_template(template, compiled)?;
            if is_new {
                written.push(template);
            } else {
                identical.push(template);
            }
        }
        Ok::<_, TracedErr>(())
    })?;

    timeit!("Syncing lockfile", { lockfile.sync() })?;

    // Write only when hidden cli flag --debug is set, to allow testing internals from python without having to setup custom interfaces:
    if render_args.debug {
        let debug = debug::Debug {
            config: conf,
            written: written
                .iter()
                .map(|t| t.out_path.display().to_string())
                .collect(),
            identical: identical.iter().map(|t| t.rel_path.clone()).collect(),
            lockfile_modified: lockfile.modified,
        };

        // Write as json to etcher_debug.json at root:
        let debug_json = serde_json::to_string_pretty(&debug)?;
        std::fs::write(render_args.root.join("etcher_debug.json"), debug_json)?;
    }

    info!(
        "{} template{} written, {} identical. Lockfile {}. {} elapsed.",
        written.len(),
        if written.len() == 1 { "" } else { "s" },
        identical.len(),
        if lockfile.modified {
            "modified"
        } else {
            "unchanged"
        },
        format_duration(GLOBAL_TIME_RECORDER.total_elapsed()?)
    );

    Ok(true)
}

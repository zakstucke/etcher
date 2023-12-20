#![warn(clippy::disallowed_types)]

use std::ops::Deref;

use colored::Colorize;
use config::PY_CONTEXT;
use pyo3::{exceptions::PyValueError, prelude::*};
use pythonize::depythonize;

mod args;
mod config;
mod init;
mod render;
mod run;
mod utils;

// If one of these is the first argument, won't auto assume etch render subcommand
const ETCH_ROOT_ARGS: &[&str] = &["-h", "--help", "help", "-V", "--version", "version"];

#[pyfunction]
pub fn cli() {
    match run::run() {
        Ok(_) => std::process::exit(0),
        Err(e) => {
            #[allow(clippy::print_stderr)]
            {
                eprintln!("{}", "etch failed".red().bold());
                eprintln!("{e}");
            }
            std::process::exit(1);
        }
    }
}

#[pyfunction]
#[pyo3(name = "register_function")]
pub fn py_register_function(py: Python, py_fn: &PyAny) -> PyResult<()> {
    config::register_py_func(py, py_fn)?;
    Ok(())
}

/// Get the current context as a Python dictionary to be used in custom user functions.
#[pyfunction]
#[pyo3(name = "context")]
pub fn py_context(py: Python) -> PyResult<PyObject> {
    let py_ctx = PY_CONTEXT.lock();
    if let Some(py_ctx) = py_ctx.deref() {
        Ok(py_ctx.clone_ref(py))
    } else {
        Err(PyValueError::new_err(
            "Context not registered. This should only be called by custom user extensions.",
        ))
    }
}

#[pyfunction]
#[pyo3(name = "_toml_update")]
pub fn py_toml_update(
    initial: &str,
    update: Option<&PyAny>,
    remove: Option<&PyAny>,
) -> PyResult<String> {
    let update: Option<serde_json::Value> = if let Some(update) = update {
        depythonize(update)?
    } else {
        None
    };
    let remove: Option<Vec<Vec<String>>> = if let Some(remove) = remove {
        depythonize(remove)?
    } else {
        None
    };
    Ok(utils::toml::update(initial, update, remove)?)
}

#[pyfunction]
#[pyo3(name = "_hash_contents")]
pub fn py_hash_contents(contents: &str) -> PyResult<String> {
    Ok(bitbazaar::hash::fnv1a(contents.as_bytes()).to_string())
}

/// A Python module implemented in Rust. The name of this function must match
/// the `lib.name` setting in the `Cargo.toml`, else Python will not be able to
/// import the module.
#[pymodule]
#[pyo3(name = "_rs")]
fn root_module(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cli, m)?)?;

    m.add_function(wrap_pyfunction!(py_register_function, m)?)?;

    m.add_function(wrap_pyfunction!(py_context, m)?)?;

    m.add_function(wrap_pyfunction!(py_toml_update, m)?)?;

    m.add_function(wrap_pyfunction!(py_hash_contents, m)?)?;

    Ok(())
}

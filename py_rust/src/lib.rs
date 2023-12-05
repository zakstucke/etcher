#![warn(clippy::disallowed_types)]

use pyo3::prelude::*;

mod utils;

#[pyfunction]
pub fn cli(py: Python) -> PyResult<bool> {
    let etcher_main = py.import("etcher.main")?;
    let typer = py.import("typer")?;

    typer.call_method1("run", (etcher_main.getattr("main")?,))?;

    Ok(true)
}

/// A Python module implemented in Rust. The name of this function must match
/// the `lib.name` setting in the `Cargo.toml`, else Python will not be able to
/// import the module.
#[pymodule]
#[pyo3(name = "_rs")]
fn root_module(py: Python, m: &PyModule) -> PyResult<()> {
    // A top level function:
    m.add_function(wrap_pyfunction!(cli, m)?)?;

    // A submodule:
    m.add_submodule(utils::build_module(py)?)?;

    Ok(())
}

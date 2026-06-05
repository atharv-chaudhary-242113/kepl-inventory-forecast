use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

use kepl_core::orchestrator::process_pipeline;

#[pyfunction]
fn run_pipeline(
    pov_files: Vec<String>,
    grn_files: Vec<String>,
    pv_files: Vec<String>,
    stock_files: Vec<String>,
) -> PyResult<usize> {
    let result = process_pipeline(pov_files, grn_files, pv_files, stock_files)
        .map_err(|e| PyRuntimeError::new_err(e.to_string()))?;

    Ok(result.processed_rows)
}

#[pymodule]
fn kepl_bindings(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(run_pipeline, m)?)?;
    Ok(())
}

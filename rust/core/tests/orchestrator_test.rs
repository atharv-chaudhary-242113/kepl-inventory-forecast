use kepl_core::orchestrator::{EngineRequest, process_pipeline, run_engine};

use std::path::PathBuf;

#[test]
fn process_pipeline_returns_payload() {
    let result = process_pipeline(vec![], vec![], vec![], vec![]);

    assert!(result.is_ok());
}

#[test]
fn run_engine_returns_payload() {
    let request = EngineRequest {
        pov_paths: vec![],
        grn_paths: vec![],
        pv_paths: vec![],
        stock_paths: vec![],
        forecast_horizon: 12,
        output_workbook_path: PathBuf::from("output.xlsx"),
    };

    let result = run_engine(request);

    assert!(result.is_ok());
}

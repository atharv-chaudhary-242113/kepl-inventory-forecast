use crate::error::KeplError;
use std::path::PathBuf;

#[derive(Debug, Clone)]
pub struct EngineRequest {
    pub pov_paths: Vec<PathBuf>,
    pub grn_paths: Vec<PathBuf>,
    pub pv_paths: Vec<PathBuf>,
    pub stock_paths: Vec<PathBuf>,
    pub forecast_horizon: u32,
    pub output_workbook_path: PathBuf,
}

#[derive(Debug, Clone)]
pub struct EnginePayload {
    pub processed_rows: usize,
    pub supplier_count: usize,
    pub item_count: usize,
}

pub fn run_engine(_request: EngineRequest) -> Result<EnginePayload, KeplError> {
    Ok(EnginePayload {
        processed_rows: 0,
        supplier_count: 0,
        item_count: 0,
    })
}

pub fn process_pipeline(
    pov_paths: Vec<String>,
    grn_paths: Vec<String>,
    pv_paths: Vec<String>,
    stock_paths: Vec<String>,
) -> Result<EnginePayload, KeplError> {
    let request = EngineRequest {
        pov_paths: pov_paths.into_iter().map(PathBuf::from).collect(),
        grn_paths: grn_paths.into_iter().map(PathBuf::from).collect(),
        pv_paths: pv_paths.into_iter().map(PathBuf::from).collect(),
        stock_paths: stock_paths.into_iter().map(PathBuf::from).collect(),
        forecast_horizon: 12,
        output_workbook_path: PathBuf::from("output.xlsx"),
    };

    run_engine(request)
}

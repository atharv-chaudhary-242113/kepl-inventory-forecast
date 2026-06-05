// rust/core/src/forecasting/mod.rs
//! Forecasting layer.
//! Orchestrates demand reconstruction, Holt-Winters baselining, and SBC-routed model refinement.

pub mod demand_reconstruction;
pub mod glm;
pub mod holt_winters;
pub mod pipeline;
pub mod random_forest;
pub mod routing;
pub mod tsb;

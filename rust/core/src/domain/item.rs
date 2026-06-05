// rust/core/src/domain/item.rs
//! Inventory Item identity modeling.
//! Implements the composite key rule: Item Identity = Normalized Supplier + Item Details.

use crate::domain::supplier::SupplierId;
use serde::{Deserialize, Serialize};

/// Authoritative identity for an inventory item.
/// The same physical item from different suppliers represents distinct entities.
#[derive(Debug, Clone, Hash, Eq, PartialEq, Serialize, Deserialize)]
pub struct ItemId {
    pub supplier: SupplierId,
    pub details: String,
}

impl ItemId {
    pub fn new(supplier: SupplierId, details: String) -> Self {
        Self { supplier, details }
    }
}

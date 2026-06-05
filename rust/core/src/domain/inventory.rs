// rust/core/src/domain/inventory.rs
//! Inventory classification and valuation entities.

use crate::classification::abc::AbcClass;
use crate::classification::sbc::DemandClass;
use crate::domain::item::ItemId;
use rust_decimal::Decimal;

/// A point-in-time snapshot of inventory levels and valuation.
#[derive(Debug, Clone)]
pub struct InventoryRecord {
    pub item: ItemId,
    pub available_quantity: f64,
    pub unit_cost: Decimal,
    pub total_value: Decimal,
}

/// Binds domain classifications to a specific item.
#[derive(Debug, Clone)]
pub struct ItemClassification {
    pub item: ItemId,
    pub abc_class: AbcClass,
    pub sbc_class: DemandClass,
}

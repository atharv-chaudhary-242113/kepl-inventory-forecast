"""Runtime configuration for a single pipeline run.

A frozen Pydantic model holding the business-tunable parameters from README
§10. Frozen for reproducibility (Constitution Rule 9): a run's settings cannot
mutate mid-pipeline. Several defaults (freight_rate, ABC thresholds) encode
assumptions still *pending business validation* (DOMAIN_RULES.md) — they are
configurable precisely so no unvalidated value is hard-coded into the engine.
"""

from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from opstools.inventory_forecast.domain.enums import ForecastGranularity


class Settings(BaseModel):
    """Typed, validated, immutable settings for one run."""

    # frozen=True => instances are immutable and hashable. Mutating settings
    # mid-run would break reproducibility, so we forbid it at the type level.
    model_config = ConfigDict(frozen=True)

    forecast_horizon: int = Field(default=12, gt=0)
    forecast_granularity: ForecastGranularity = ForecastGranularity.MONTHLY
    service_z: float = Field(default=1.65, gt=0.0)
    default_lead_time_days: int = Field(default=30, gt=0)
    # Money is Decimal end to end; floating-point currency accumulation is
    # prohibited (DOMAIN_RULES.md "Currency Precision"; THREAT_MODEL.md
    # "Floating-Point Errors"). The freight *rate* lives here as Decimal so the
    # multiplication downstream stays in Decimal space.
    freight_rate: Decimal = Field(default=Decimal("0.18"), ge=Decimal("0"))
    abc_a_threshold: float = Field(default=0.80, gt=0.0, lt=1.0)
    abc_b_threshold: float = Field(default=0.95, gt=0.0, lt=1.0)
    enable_supplier_risk: bool = True
    enable_partnerships: bool = True

    @model_validator(mode="after")
    def _check_threshold_order(self) -> Self:
        """A-band cutoff must sit below the B-band cutoff (DOMAIN_RULES.md ABC).

        Field-level `gt/lt` can only bound each threshold to (0, 1); the
        *relationship* between them needs a model-level check, which runs after
        both fields are populated.
        """
        if self.abc_a_threshold >= self.abc_b_threshold:
            msg = (
                "abc_a_threshold must be < abc_b_threshold "
                f"(got {self.abc_a_threshold} and {self.abc_b_threshold})"
            )
            raise ValueError(msg)
        return self

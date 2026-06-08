"""Pipeline Schema with Pydantic.

All business variables are typed into a pydantic schema to make the pipeline smoother.
Instead of working with a wrong configuration or dtype, the pipeline will first check
the datatype and if it does not match the schema then it will not proceed further.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PipelineSettings(BaseModel):
    """Create schema for each business variable."""

    # frozen=True: settings can't mutate mid-run -> reproducibility.
    # extra="forbid": an unknown/typoed config key is rejected loudly, not silently
    #                   dropped. (Constituion Rule 7, fail-closed on bad input).
    model_config = ConfigDict(frozen=True, extra="forbid")

    forecast_horizon: int = Field(
        default=12, description="Number of future periods to forecast.", ge=1
    )
    forecast_granularity: Literal["monthly", "quarterly"] = Field(
        default="monthly", description="Monthly or Quarterly forecast"
    )
    service_z: float = Field(
        default=1.65,
        description="Service-level z-score in the reorder-point formula.",
        gt=0,
    )
    default_lead_time_days: int = Field(
        default=30, gt=1, description="Fallback lead time when history is insufficient."
    )
    freight_rate: float = Field(
        default=0.18, description="Freight treated as a separate cost component."
    )
    abc_thresholds: dict[str, float] = Field(
        default_factory=lambda: {"a": 0.80, "b": 0.95},
        description="Cumulative-value cut points for A/B/C.",
    )
    enable_supplier_risk: bool = Field(
        default=True, description="Toggle supplier-risk analytics."
    )
    enable_partnerships: bool = Field(
        default=True, description="Toggle suspected-partnership detection."
    )

    @field_validator("forecast_granularity", mode="before")
    @classmethod
    def check_granularity(cls, v: str) -> str:
        """Validate Granularity is one of: 'monthly' or 'quarterly'.

        Args:
            v (str): Granularity to validate.

        Returns:
            str: Valid Granularity.
        """
        if not isinstance(v, str):
            return v
        accepted_granularity = ["monthly", "quarterly"]
        v = v.lower().strip()
        if v not in accepted_granularity:
            raise ValueError("forecast_granularity must be 'monthly' or 'quarterly'")
        return v

    @field_validator("abc_thresholds", mode="before")
    @classmethod
    def check_abc_thresholds(cls, v: dict[str, float]) -> dict[str, float]:
        """Validate ABC cut-points are present, ordered, and within (0, 1).

        Args:
            v (dict[str, float]): Cut-points to validate.

        Returns:
            dict[str, float]: Valid ABC cut-points.
        """
        # Keys must exist before we can compare them.
        if "a" not in v or "b" not in v:
            raise ValueError("abc_thresholds must have keys 'a' and 'b'.")
        a, b = v["a"], v["b"]
        if not (0 < a < b < 1):
            raise ValueError("abc_thresholds must satisfy (0 < a < b < 1).")
        return v

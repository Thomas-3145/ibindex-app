from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductResponse(BaseModel):
    """One entry from GET /ibi/index/getProducts.req"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    ticker: str = Field(alias="product")
    product_name: str = Field(alias="productName")
    price: float
    previous_price: float = Field(alias="previousPrice")
    price_change: float = Field(alias="priceChange")
    nav: float = Field(alias="netAssetValue")
    nav_calculated: float = Field(alias="netAssetValueCalculated")
    nav_rebate_premium: float = Field(alias="netAssetValueRebatePremium")
    nav_calculated_rebate_premium: float = Field(alias="netAssetValueCalculatedRebatePremium")


class WeightResponse(BaseModel):
    """One entry from GET /ibi/index/getProductWeights.req"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    ticker: str = Field(alias="product")
    product_name: str = Field(alias="productName")
    weight: float


class SnapshotRow(BaseModel):
    """One row from the snapshots table, joined with products."""

    ticker: str
    product_name: str
    price: float
    previous_price: float | None
    price_change: float | None
    nav: float | None
    nav_calculated: float | None
    nav_rebate_premium: float | None
    nav_calculated_rebate_premium: float | None
    weight: float | None
    market_cap_weight: float | None
    scraped_at: datetime


class AllocationResult(BaseModel):
    """Output of the portfolio allocation for one company."""

    ticker: str
    product_name: str
    price: float
    weight: float
    allocated_sek: float
    approx_shares: float

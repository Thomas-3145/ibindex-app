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


class HoldingResponse(BaseModel):
    """One entry from POST /ibi/company/getHoldings.req"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    holding_ticker: str | None = Field(default=None, alias="holdingProduct")
    holding_name: str = Field(alias="holdingName")
    exchange: str | None = Field(default=None, alias="holdingExchange")
    value: float = Field(alias="holdingValue")
    category: str
    category_name: str = Field(alias="categoryName")


class HoldingRow(BaseModel):
    """One row from the holdings table."""

    owner_ticker: str
    holding_ticker: str | None
    holding_name: str
    exchange: str | None
    value: float
    category: str
    category_name: str
    scraped_at: datetime


class ShareClassRow(BaseModel):
    """One row from the share_classes table: an alternative listing of a company."""

    base_ticker: str
    ticker: str
    price: float
    avg_volume: float | None
    scraped_at: datetime


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
    target_sek: float
    allocated_sek: float
    shares: int


class UnderlyingAllocation(BaseModel):
    """One row after expanding investment companies into their holdings.

    `via` lists how the exposure is obtained: "Direkt" for companies kept
    as-is, otherwise the names of the investment companies holding it.
    """

    name: str
    ticker: str | None
    allocated_sek: float
    weight: float
    via: list[str]


class ShareClassComparison(BaseModel):
    """The cheapest and most expensive listed class of one company.

    `spread_pct` is how much more the expensive class costs than the cheap
    one. `illiquid` flags that at least one class trades too thinly for its
    last price — and therefore the spread — to be trusted.
    """

    base_ticker: str
    product_name: str
    cheapest_ticker: str
    cheapest_price: float
    priciest_ticker: str
    priciest_price: float
    spread_pct: float
    illiquid: bool

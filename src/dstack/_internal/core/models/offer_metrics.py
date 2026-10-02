from typing import Annotated, Optional

from pydantic import Field

from dstack._internal.core.models.common import CoreModel

NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class VastAIOfferMetrics(CoreModel):
    download_mbps: Optional[NonNegativeFloat] = None
    """Advertised internet download bandwidth in Mbps; not measured throughput."""
    download_cost_per_gb: Optional[NonNegativeFloat] = None
    """Internet download price in USD per decimal GB."""
    upload_mbps: Optional[NonNegativeFloat] = None
    upload_cost_per_gb: Optional[NonNegativeFloat] = None
    """Internet upload price in USD per decimal GB."""
    disk_read_mbps: Optional[NonNegativeFloat] = None
    """Disk read bandwidth in MB/s (megabytes, not megabits); not disk write speed."""
    storage_cost_per_gb_month: Optional[NonNegativeFloat] = None


class ColdStartEstimate(CoreModel):
    download_size_gb: NonNegativeFloat
    """Per-instance download traffic in decimal GB, assuming no cache hits."""
    bandwidth_utilization: float = 0.8
    estimated_duration_seconds: Optional[NonNegativeFloat] = None
    """Download time only; excludes provisioning, extraction and model initialization."""
    estimated_download_cost: Optional[NonNegativeFloat] = None
    """Estimated ingress traffic charge in USD."""
    estimated_instance_cost: Optional[NonNegativeFloat] = None
    """Conservatively assumes the instance's hourly rate is billed throughout the download."""
    estimated_cost: Optional[NonNegativeFloat] = None
    """Sum of traffic and instance charges, in USD."""
    cost_ratio: Optional[NonNegativeFloat] = None
    """Total cold-start cost divided by the cost of one instance-hour; may exceed 1."""

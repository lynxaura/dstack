import math

from dstack._internal.core.models.offer_metrics import ColdStartEstimate, VastAIOfferMetrics

BANDWIDTH_UTILIZATION = 0.8


def estimate_cold_start(
    download_size_gb: float, metrics: VastAIOfferMetrics, price: float
) -> ColdStartEstimate:
    duration = None
    download_cost = None
    if download_size_gb == 0:
        duration = download_cost = 0.0
    else:
        if metrics.download_mbps is not None and metrics.download_mbps > 0:
            duration = _finite(
                download_size_gb * 8000 / (metrics.download_mbps * BANDWIDTH_UTILIZATION)
            )
        if metrics.download_cost_per_gb is not None:
            download_cost = _finite(download_size_gb * metrics.download_cost_per_gb)
    valid_price = math.isfinite(price) and price >= 0
    instance_cost = (
        _finite(price * (duration / 3600)) if valid_price and duration is not None else None
    )
    total = (
        _finite(download_cost + instance_cost)
        if download_cost is not None and instance_cost is not None
        else None
    )
    ratio = _finite(total / price) if total is not None and price > 0 else None
    return ColdStartEstimate(
        download_size_gb=download_size_gb,
        bandwidth_utilization=BANDWIDTH_UTILIZATION,
        estimated_duration_seconds=duration,
        estimated_download_cost=download_cost,
        estimated_instance_cost=instance_cost,
        estimated_cost=total,
        cost_ratio=ratio,
        mixed_cold_price=_finite(total + price) if total is not None else None,
    )


def _finite(value: float) -> float | None:
    return value if math.isfinite(value) else None

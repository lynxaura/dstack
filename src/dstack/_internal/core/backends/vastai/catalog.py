"""Vast catalog adapter retaining metrics omitted by gpuhunt 0.1.32."""

import copy
import math
from typing import Optional

import gpuhunt
import requests
from gpuhunt._internal.constraints import correct_gpu_memory_gib
from gpuhunt.providers.vastai import (
    VastAIProvider as GPUHuntVastAIProvider,
)
from gpuhunt.providers.vastai import (
    bundles_url,
    get_dstack_gpu_name,
    get_location,
    stricter_constraint,
)

from dstack._internal.core.models.offer_metrics import VastAIOfferMetrics
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class VastAIProvider(GPUHuntVastAIProvider):
    def get(
        self,
        query_filter: Optional[gpuhunt.QueryFilter] = None,
        balance_resources: bool = True,
        apply_filter: bool = False,
    ) -> list[gpuhunt.CatalogItem]:
        # Keep upstream filtering, naming, resource allocation and price semantics.
        filters = self.make_filters(query_filter or gpuhunt.QueryFilter())
        if self.extra_filters:
            for key, constraints in self.extra_filters.items():
                for op, value in constraints.items():
                    filters[key][op] = stricter_constraint(op, filters[key].get(op), value)
        response = requests.post(bundles_url, json=filters, timeout=10)
        response.raise_for_status()
        items = []
        for offer in response.json()["offers"]:
            cpu_cores = offer["cpu_cores"]
            if not cpu_cores:
                continue
            cpu = int(offer["cpu_cores_effective"])
            memory = round(offer["cpu_ram"] * offer["cpu_cores_effective"] / cpu_cores / 1000, 2)
            if cpu < 1 or memory <= 0:
                continue
            if not self.satisfies_filters(offer, filters):
                logger.debug("Vast offer %s does not satisfy filters", offer["id"])
                continue
            disk_size = query_filter and query_filter.min_disk_size or offer["disk_space"]
            disk_cost = disk_size * offer["storage_cost"] / 30 / 24
            gpu_name = get_dstack_gpu_name(offer["gpu_name"])
            metrics = get_offer_metrics(offer)
            item = gpuhunt.CatalogItem(
                provider=self.NAME,
                instance_name=str(offer["id"]),
                location=get_location(offer["geolocation"]),
                price=round(offer["dph_base"] + disk_cost, 5),
                cpu=cpu,
                memory=memory,
                gpu_vendor=gpuhunt.AcceleratorVendor.NVIDIA if offer["num_gpus"] else None,
                gpu_count=offer["num_gpus"],
                gpu_name=gpu_name,
                gpu_memory=float(correct_gpu_memory_gib(gpu_name, offer["gpu_ram"])),
                spot=False,
                disk_size=disk_size,
                provider_data={"vastai": metrics.model_dump()},
            )
            variants = [item]
            if offer.get("min_bid"):
                spot = copy.deepcopy(item)
                spot.price = round(offer["min_bid"] + disk_cost, 5)
                spot.spot = True
                spot.provider_data["min_bid"] = offer["min_bid"]
                variants.append(spot)
            variants.sort(key=lambda item: item.price)
            items.extend(variants)
        return items


def get_offer_metrics(offer: dict) -> VastAIOfferMetrics:
    return VastAIOfferMetrics(
        machine_id=offer.get("machine_id"),
        dlperf=_nonnegative_number(offer.get("dlperf")),
        download_mbps=_nonnegative_number(offer.get("inet_down")),
        download_cost_per_gb=_nonnegative_number(offer.get("inet_down_cost")),
        upload_mbps=_nonnegative_number(offer.get("inet_up")),
        upload_cost_per_gb=_nonnegative_number(offer.get("inet_up_cost")),
        disk_read_mbps=_nonnegative_number(offer.get("disk_bw")),
        storage_cost_per_gb_month=_nonnegative_number(offer.get("storage_cost")),
    )


def _nonnegative_number(value) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and value >= 0 else None

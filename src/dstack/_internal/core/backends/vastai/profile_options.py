from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.backends.base.profile_options import BackendProfileOptions
from dstack._internal.core.models.common import CoreModel
from dstack._internal.utils.combine import (
    CombineError,
    combine_optional,
    get_max_optional,
    get_single_value_optional,
)


class VastAIOfferOrder(str, Enum):
    SCORE = "score"
    PRICE = "price"


VASTAI_DEFAULT_OFFER_ORDER = VastAIOfferOrder.SCORE
VASTAI_DEFAULT_MIN_RELIABILITY = 0.9


VastAIFilterValue = Union[int, float, str, bool]


class VastAIFilter(CoreModel):
    lt: Annotated[
        Optional[VastAIFilterValue],
        Field(description="Match offers whose field value is less than this value"),
    ] = None
    lte: Annotated[
        Optional[VastAIFilterValue],
        Field(description="Match offers whose field value is less than or equal to this value"),
    ] = None
    eq: Annotated[
        Optional[VastAIFilterValue],
        Field(description="Match offers whose field value equals this value"),
    ] = None
    gte: Annotated[
        Optional[VastAIFilterValue],
        Field(description="Match offers whose field value is greater than or equal to this value"),
    ] = None
    gt: Annotated[
        Optional[VastAIFilterValue],
        Field(description="Match offers whose field value is greater than this value"),
    ] = None


class VastAIExtraFilters(CoreModel):
    bw_nvlink: Optional[VastAIFilter] = None
    cluster_id: Optional[VastAIFilter] = None
    cpu_ghz: Optional[VastAIFilter] = None
    disk_bw: Optional[VastAIFilter] = None
    dlperf: Optional[VastAIFilter] = None
    dlperf_per_dphtotal: Optional[VastAIFilter] = None
    driver_version: Optional[VastAIFilter] = None
    duration: Optional[VastAIFilter] = None
    flops_per_dphtotal: Optional[VastAIFilter] = None
    gpu_arch: Optional[VastAIFilter] = None
    gpu_display_active: Optional[VastAIFilter] = None
    gpu_frac: Optional[VastAIFilter] = None
    gpu_max_power: Optional[VastAIFilter] = None
    gpu_max_temp: Optional[VastAIFilter] = None
    gpu_mem_bw: Optional[VastAIFilter] = None
    has_avx: Optional[VastAIFilter] = None
    host_id: Optional[VastAIFilter] = None
    id: Optional[VastAIFilter] = None
    inet_down: Optional[VastAIFilter] = None
    inet_down_cost: Optional[VastAIFilter] = None
    inet_up: Optional[VastAIFilter] = None
    inet_up_cost: Optional[VastAIFilter] = None
    machine_id: Optional[VastAIFilter] = None
    min_bid: Optional[VastAIFilter] = None
    mobo_name: Optional[VastAIFilter] = None
    pci_gen: Optional[VastAIFilter] = None
    pcie_bw: Optional[VastAIFilter] = None
    static_ip: Optional[VastAIFilter] = None
    storage_cost: Optional[VastAIFilter] = None
    total_flops: Optional[VastAIFilter] = None
    ubuntu_version: Optional[VastAIFilter] = None
    vms_enabled: Optional[VastAIFilter] = None


class VastAIColdStartOptions(CoreModel):
    download_size_gb: Annotated[
        float,
        Field(
            ge=0,
            allow_inf_nan=False,
            description="Per-instance uncached download size in decimal GB",
        ),
    ]
    max_cost_ratio: Annotated[
        Optional[float],
        Field(
            ge=0,
            allow_inf_nan=False,
            description=(
                "Maximum estimated cold-start cost divided by one instance-hour's cost."
                " Uses 80% of advertised download bandwidth and includes download traffic"
                " and instance charges during the download. May exceed 1"
            ),
        ),
    ] = None

    def combine(self, other: "VastAIColdStartOptions") -> "VastAIColdStartOptions":
        if self.download_size_gb != other.download_size_gb:
            raise CombineError("Conflicting Vast.ai cold-start download sizes")
        return VastAIColdStartOptions(
            download_size_gb=self.download_size_gb,
            max_cost_ratio=combine_optional(self.max_cost_ratio, other.max_cost_ratio, min),
        )


class VastAIProfileOptions(BackendProfileOptions["VastAIProfileOptions"]):
    type: Literal["vastai"] = "vastai"
    offer_order: Annotated[
        Optional[VastAIOfferOrder],
        Field(
            description=(
                "Controls the order in which offers are considered for provisioning."
                " Use `score` to prioritize the highest overall score first"
                " (the default order in the Vast.ai console),"
                " or `price` to prioritize the lowest-cost offers first."
                " Lower-cost offers are often less reliable,"
                " so consider applying stricter filters when using `price`."
                f" Defaults to `{VASTAI_DEFAULT_OFFER_ORDER.value}`"
            )
        ),
    ] = None
    min_reliability: Annotated[
        Optional[float],
        Field(
            description=(
                "The minimum reliability threshold for offers, on a scale from `0` to `1`."
                f" Defaults to `{VASTAI_DEFAULT_MIN_RELIABILITY}`"
            ),
            ge=0,
            le=1,
        ),
    ] = None
    min_score: Annotated[
        Optional[int],
        Field(
            description=(
                "The minimum overall score required for offers to be considered."
                " The scoring scale varies and may require experimentation."
                " Starting with a value in the low hundreds is generally recommended"
            ),
            ge=0,
        ),
    ] = None
    extra_filters: Annotated[
        Optional[VastAIExtraFilters],
        Field(
            description=(
                "Additional Vast.ai offer filters that are not already exposed by dstack,"
                " such as `storage_cost` or `inet_down_cost`."
                " Each field accepts the comparison operators `lt`, `lte`, `eq`, `gte`, and `gt`."
            )
        ),
    ] = None

    cold_start: Annotated[
        Optional[VastAIColdStartOptions],
        Field(
            description="Estimate cold-start download time and cost, optionally filtering by cost ratio",
            exclude_if=lambda value: value is None,
        ),
    ] = None

    def combine(self, other: "VastAIProfileOptions") -> "VastAIProfileOptions":
        return VastAIProfileOptions(
            offer_order=get_single_value_optional(self.offer_order, other.offer_order),
            min_reliability=get_max_optional(self.min_reliability, other.min_reliability),
            min_score=get_max_optional(self.min_score, other.min_score),
            extra_filters=_combine_extra_filters(self.extra_filters, other.extra_filters),
            cold_start=combine_optional(
                self.cold_start, other.cold_start, lambda a, b: a.combine(b)
            ),
        )


def _combine_extra_filters(
    value1: Optional[VastAIExtraFilters],
    value2: Optional[VastAIExtraFilters],
) -> Optional[VastAIExtraFilters]:
    if value1 is None:
        if value2 is None:
            return None
        return value2.model_copy(deep=True)
    if value2 is None:
        return value1.model_copy(deep=True)

    result = value1.model_dump(exclude_none=True)
    for name, constraints in value2.model_dump(exclude_none=True).items():
        if name not in result:
            result[name] = constraints
            continue
        merged = result[name]
        for operator, value in constraints.items():
            if operator not in merged:
                merged[operator] = value
                continue
            merged[operator] = _combine_filter_value(operator, merged[operator], value)
        result[name] = merged
    return VastAIExtraFilters.model_validate(result)


def _combine_filter_value(
    operator: str, value1: VastAIFilterValue, value2: VastAIFilterValue
) -> VastAIFilterValue:
    if value1 == value2:
        return value1
    try:
        if operator in {"gt", "gte"}:
            return max(value1, value2)
        if operator in {"lt", "lte"}:
            return min(value1, value2)
    except TypeError as e:
        raise CombineError(
            f"Vast.ai extra filter values {value1!r} and {value2!r} cannot be combined"
        ) from e
    raise CombineError(f"Vast.ai extra filter values {value1!r} and {value2!r} cannot be combined")

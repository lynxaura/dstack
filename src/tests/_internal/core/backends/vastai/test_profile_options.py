import pytest
from pydantic import ValidationError

from dstack._internal.core.backends.vastai.profile_options import (
    VastAIOfferOrder,
    VastAIProfileOptions,
)
from dstack._internal.utils.combine import CombineError


class TestVastAIProfileOptionsCombine:
    def test_combine_empty_options(self):
        a = VastAIProfileOptions()
        b = VastAIProfileOptions()
        result = a.combine(b)
        assert result == VastAIProfileOptions()

    def test_combine_all_fields_set(self):
        a = VastAIProfileOptions(
            offer_order=VastAIOfferOrder.PRICE,
            min_reliability=0.7,
            min_score=100,
        )
        b = VastAIProfileOptions(
            offer_order=VastAIOfferOrder.PRICE,
            min_reliability=0.95,
            min_score=300,
        )
        a_combine_b = a.combine(b)
        assert a_combine_b.offer_order == VastAIOfferOrder.PRICE
        assert a_combine_b.min_reliability == 0.95
        assert a_combine_b.min_score == 300
        b_combine_a = b.combine(a)
        assert b_combine_a.offer_order == VastAIOfferOrder.PRICE
        assert b_combine_a.min_reliability == 0.95
        assert b_combine_a.min_score == 300

    def test_combine_one_has_all_fields_set(self):
        a = VastAIProfileOptions(
            offer_order=VastAIOfferOrder.PRICE,
            min_reliability=0.7,
            min_score=100,
        )
        b = VastAIProfileOptions()
        assert a.combine(b) == a
        assert b.combine(a) == a

    def test_combine_conflicting_offer_order_raises(self):
        a = VastAIProfileOptions(offer_order=VastAIOfferOrder.PRICE)
        b = VastAIProfileOptions(offer_order=VastAIOfferOrder.SCORE)
        with pytest.raises(CombineError):
            a.combine(b)

    def test_combine_extra_filters(self):
        a = VastAIProfileOptions(
            extra_filters={
                "storage_cost": {"lte": 0.2},
                "static_ip": {"eq": True},
            }
        )
        b = VastAIProfileOptions(
            extra_filters={
                "storage_cost": {"lte": 0.1},
                "inet_down_cost": {"lte": 0.01},
            }
        )

        result = a.combine(b)

        assert result.extra_filters is not None
        assert result.extra_filters.storage_cost is not None
        assert result.extra_filters.storage_cost.lte == 0.1
        assert result.extra_filters.static_ip is not None
        assert result.extra_filters.static_ip.eq is True
        assert result.extra_filters.inet_down_cost is not None
        assert result.extra_filters.inet_down_cost.lte == 0.01

    def test_combine_conflicting_extra_filter_eq_raises(self):
        a = VastAIProfileOptions(extra_filters={"static_ip": {"eq": True}})
        b = VastAIProfileOptions(extra_filters={"static_ip": {"eq": False}})

        with pytest.raises(CombineError):
            a.combine(b)


def test_vastai_profile_options_schema_exposes_extra_filter_operators():
    schema = VastAIProfileOptions.model_json_schema()

    assert "extra_filters" in schema["properties"]
    extra_filters_schema = schema["$defs"]["VastAIExtraFilters"]
    assert set(extra_filters_schema["properties"]) == {
        "bw_nvlink",
        "cluster_id",
        "cpu_ghz",
        "disk_bw",
        "dlperf",
        "dlperf_per_dphtotal",
        "driver_version",
        "duration",
        "flops_per_dphtotal",
        "gpu_arch",
        "gpu_display_active",
        "gpu_frac",
        "gpu_max_power",
        "gpu_max_temp",
        "gpu_mem_bw",
        "has_avx",
        "host_id",
        "id",
        "inet_down",
        "inet_down_cost",
        "inet_up",
        "inet_up_cost",
        "machine_id",
        "min_bid",
        "mobo_name",
        "pci_gen",
        "pcie_bw",
        "static_ip",
        "storage_cost",
        "total_flops",
        "ubuntu_version",
        "vms_enabled",
    }
    assert extra_filters_schema["additionalProperties"] is False
    filter_schema = schema["$defs"]["VastAIFilter"]
    assert set(filter_schema["properties"]) == {"lt", "lte", "eq", "gte", "gt"}
    assert filter_schema["additionalProperties"] is False


@pytest.mark.parametrize("field", ["verified", "gpu_name", "dph_total"])
def test_vastai_profile_options_rejects_filters_already_exposed_by_dstack(field):
    with pytest.raises(ValidationError):
        VastAIProfileOptions(extra_filters={field: {"eq": True}})


class TestVastAIColdStartOptions:
    @pytest.mark.parametrize(
        "options",
        [
            {"max_cost_ratio": 0.2},
            {"download_size_gb": -1},
            {"download_size_gb": float("nan")},
            {"download_size_gb": float("inf")},
            {"download_size_gb": 20, "max_cost_ratio": -1},
            {"download_size_gb": 20, "max_cost_ratio": float("inf")},
        ],
    )
    def test_rejects_invalid_options(self, options):
        with pytest.raises(ValidationError):
            VastAIProfileOptions(cold_start=options)

    def test_ratio_may_exceed_one(self):
        assert (
            VastAIProfileOptions(
                cold_start={"download_size_gb": 20, "max_cost_ratio": 2}
            ).cold_start.max_cost_ratio
            == 2
        )

    def test_combine_uses_stricter_ratio(self):
        a = VastAIProfileOptions(cold_start={"download_size_gb": 20, "max_cost_ratio": 0.2})
        b = VastAIProfileOptions(cold_start={"download_size_gb": 20, "max_cost_ratio": 0.1})
        assert a.combine(b).cold_start.max_cost_ratio == 0.1
        assert b.combine(a).cold_start.max_cost_ratio == 0.1
        assert a.combine(VastAIProfileOptions()) == a

    def test_conflicting_sizes_cannot_be_combined(self):
        a = VastAIProfileOptions(cold_start={"download_size_gb": 20})
        b = VastAIProfileOptions(cold_start={"download_size_gb": 40})
        with pytest.raises(CombineError):
            a.combine(b)

    def test_unset_field_is_omitted_for_older_servers(self):
        assert "cold_start" not in VastAIProfileOptions().model_dump()
        assert "cold_start" not in VastAIProfileOptions(cold_start=None).model_dump()
        assert (
            VastAIProfileOptions(cold_start={"download_size_gb": 20}).model_dump()["cold_start"][
                "download_size_gb"
            ]
            == 20
        )

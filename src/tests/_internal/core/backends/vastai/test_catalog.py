from unittest.mock import Mock, patch

import gpuhunt
import pytest
from gpuhunt.providers.vastai import VastAIProvider as GPUHuntVastAIProvider

from dstack._internal.core.backends.vastai.catalog import VastAIProvider, get_offer_metrics
from dstack._internal.core.backends.vastai.compute import VastAICompute
from dstack._internal.core.backends.vastai.models import VastAIConfig, VastAICreds
from dstack._internal.core.backends.vastai.profile_options import VastAIProfileOptions
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements


def _raw_offer(**overrides):
    return {
        "id": 12345,
        "cpu_cores": 16,
        "cpu_cores_effective": 8,
        "cpu_ram": 64000,
        "disk_space": 200,
        "storage_cost": 0.1,
        "gpu_name": "RTX 4090",
        "gpu_ram": 24576,
        "num_gpus": 1,
        "geolocation": "Hong Kong, HK",
        "dph_base": 0.5,
        "min_bid": 0.2,
        "inet_down": 1000,
        "inet_down_cost": 0.002,
        "inet_up": 500,
        "inet_up_cost": 0.005,
        "disk_bw": 1500,
        **overrides,
    }


class TestVastAIProvider:
    def test_retains_metrics_without_changing_upstream_offer_semantics(self):
        response = Mock()
        response.json.return_value = {"offers": [_raw_offer()]}
        query = gpuhunt.QueryFilter(min_disk_size=100)
        with patch(
            "dstack._internal.core.backends.vastai.catalog.requests.post", return_value=response
        ) as post:
            items = VastAIProvider().get(query)
            upstream = GPUHuntVastAIProvider().get(query)
        assert len(items) == 2
        for item, original in zip(items, upstream):
            metrics = item.provider_data.pop("vastai")
            assert metrics["download_mbps"] == 1000
            assert metrics["download_cost_per_gb"] == 0.002
            assert metrics["disk_read_mbps"] == 1500
            assert item == original
        assert items[0].spot
        assert items[0].provider_data["min_bid"] == 0.2
        assert post.call_count == 2

    def test_extra_filters_are_applied_before_returning_metrics(self):
        response = Mock()
        response.json.return_value = {
            "offers": [_raw_offer(inet_down_cost=0.5), _raw_offer(id=67890)]
        }
        provider = VastAIProvider(extra_filters={"inet_down_cost": {"lte": 0.01}})
        with patch(
            "dstack._internal.core.backends.vastai.catalog.requests.post", return_value=response
        ) as post:
            items = provider.get()
        assert [item.instance_name for item in items] == ["67890", "67890"]
        assert post.call_args.kwargs["json"]["inet_down_cost"] == {"lte": 0.01}

    def test_invalid_resources_are_skipped(self):
        response = Mock()
        response.json.return_value = {
            "offers": [_raw_offer(cpu_cores=None), _raw_offer(cpu_cores_effective=0)]
        }
        with patch(
            "dstack._internal.core.backends.vastai.catalog.requests.post", return_value=response
        ):
            assert VastAIProvider().get() == []


class TestGetOfferMetrics:
    @pytest.mark.parametrize("value", [None, -1, "invalid", float("nan"), float("inf"), True])
    def test_unknown_or_invalid_metrics_are_null(self, value):
        metrics = get_offer_metrics(
            {"inet_down": value, "inet_down_cost": value, "disk_bw": value}
        )
        assert metrics.download_mbps is None
        assert metrics.download_cost_per_gb is None
        assert metrics.disk_read_mbps is None

    def test_zero_cost_is_preserved(self):
        assert get_offer_metrics({"inet_down_cost": 0}).download_cost_per_gb == 0


class TestVastAICatalogIntegration:
    def test_raw_api_metrics_reach_filtered_instance_offers(self):

        response = Mock()
        response.json.return_value = {"offers": [_raw_offer()]}
        compute = VastAICompute(VastAIConfig(creds=VastAICreds(api_key="test")))
        requirements = Requirements(
            resources=ResourcesSpec(),
            backend_options=[
                VastAIProfileOptions(cold_start={"download_size_gb": 20, "max_cost_ratio": 0.2})
            ],
        )
        with patch(
            "dstack._internal.core.backends.vastai.catalog.requests.post", return_value=response
        ):
            offers = list(compute.get_offers(requirements, False, False))
        assert len(offers) == 1
        assert not offers[0].instance.resources.spot
        payload = offers[0].model_dump(mode="json")
        assert payload["vastai"]["download_mbps"] == 1000
        assert payload["vastai"]["disk_read_mbps"] == 1500
        assert payload["cold_start"]["estimated_duration_seconds"] == 200
        assert payload["cold_start"]["cost_ratio"] <= 0.2

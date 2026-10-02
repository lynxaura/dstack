from unittest.mock import MagicMock, patch

from dstack._internal.core.backends.vastai.compute import VastAICompute
from dstack._internal.core.backends.vastai.models import VastAIConfig, VastAICreds
from dstack._internal.core.backends.vastai.profile_options import VastAIProfileOptions
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import Requirements


def _config(community_cloud=None) -> VastAIConfig:
    return VastAIConfig(creds=VastAICreds(api_key="test"), community_cloud=community_cloud)


def _requirements(backend_options=None) -> Requirements:
    return Requirements(resources=ResourcesSpec(), backend_options=backend_options)


def _offer(
    *, spot: bool, price: float = 0.5, min_bid: float | None = None
) -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.VASTAI,
        instance=InstanceType(
            name="12345",
            resources=Resources(
                cpus=8,
                memory_mib=32 * 1024,
                gpus=[Gpu(name="RTX4090", memory_mib=24 * 1024)],
                spot=spot,
                disk=Disk(size_mib=100 * 1024),
            ),
        ),
        region="Hong Kong, HK",
        price=price,
        availability=InstanceAvailability.AVAILABLE,
        backend_data={
            **({"min_bid": min_bid} if min_bid is not None else {}),
        },
    )


# build_authorized_keys() rejects the project key unless it actually parses
PROJECT_SSH_PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINOmx0T+hBRaJ6jCi21ZYe2NW3EZS8e0Mdwl+yZJt+kD project"
)


def _run_job(compute: VastAICompute, offer: InstanceOfferWithAvailability):
    run = MagicMock()
    job = MagicMock()
    job.job_spec.image_name = "dstackai/base:latest"
    job.job_spec.registry_auth = None
    with (
        patch(
            "dstack._internal.core.backends.vastai.compute.generate_unique_instance_name_for_job",
            return_value="dstack-test",
        ),
        patch(
            "dstack._internal.core.backends.vastai.compute.get_docker_commands",
            return_value=["echo hi"],
        ),
    ):
        return compute.run_job(
            run=run,
            job=job,
            instance_offer=offer,
            project_ssh_public_key=PROJECT_SSH_PUBLIC_KEY,
            project_ssh_private_key="private-key",
            volumes=[],
            placement_group=None,
            requirements=_requirements(),
            extra_authorized_keys=[],
        )


def test_vastai_compute_enables_community_cloud_by_default():
    with (
        patch("dstack._internal.core.backends.vastai.compute.VastAIProvider") as vast_provider_cls,
        patch("dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog") as catalog_cls,
        patch("dstack._internal.core.backends.vastai.compute.get_catalog_offers", return_value=[]),
    ):
        catalog_instance = catalog_cls.return_value
        compute = VastAICompute(_config())
        list(compute.get_offers(_requirements(), full_offers=False, unallocated_resources=False))
        vast_provider_cls.assert_called_once()
        assert vast_provider_cls.call_args.kwargs["community_cloud"] is True
        catalog_instance.add_provider.assert_called_once()


def test_vastai_compute_can_enable_community_cloud():
    with (
        patch("dstack._internal.core.backends.vastai.compute.VastAIProvider") as vast_provider_cls,
        patch("dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog") as catalog_cls,
        patch("dstack._internal.core.backends.vastai.compute.get_catalog_offers", return_value=[]),
    ):
        catalog_instance = catalog_cls.return_value
        compute = VastAICompute(_config(community_cloud=True))
        list(compute.get_offers(_requirements(), full_offers=False, unallocated_resources=False))
        vast_provider_cls.assert_called_once()
        assert vast_provider_cls.call_args.kwargs["community_cloud"] is True
        catalog_instance.add_provider.assert_called_once()


def test_vastai_compute_can_disable_community_cloud():
    with (
        patch("dstack._internal.core.backends.vastai.compute.VastAIProvider") as vast_provider_cls,
        patch("dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog") as catalog_cls,
        patch("dstack._internal.core.backends.vastai.compute.get_catalog_offers", return_value=[]),
    ):
        catalog_instance = catalog_cls.return_value
        compute = VastAICompute(_config(community_cloud=False))
        list(compute.get_offers(_requirements(), full_offers=False, unallocated_resources=False))
        vast_provider_cls.assert_called_once()
        assert vast_provider_cls.call_args.kwargs["community_cloud"] is False
        catalog_instance.add_provider.assert_called_once()


def test_vastai_compute_merges_extra_filters_with_defaults():
    options = VastAIProfileOptions(
        extra_filters={
            "storage_cost": {"lte": 0.05},
            "inet_down_cost": {"lte": 0.01},
            "inet_down": {"gte": 600},
            "inet_up": {"gt": 256},
        }
    )
    with (
        patch("dstack._internal.core.backends.vastai.compute.VastAIProvider") as vast_provider_cls,
        patch("dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog"),
        patch("dstack._internal.core.backends.vastai.compute.get_catalog_offers", return_value=[]),
    ):
        compute = VastAICompute(_config())
        requirements = _requirements(backend_options=[options])
        list(compute.get_offers(requirements, full_offers=False, unallocated_resources=False))

        filters = vast_provider_cls.call_args.kwargs["extra_filters"]
        assert filters["storage_cost"] == {"lte": 0.05}
        assert filters["inet_down_cost"] == {"lte": 0.01}
        assert filters["inet_up"] == {"gt": 256}
        assert filters["inet_down"] == {"gte": 600}
        assert filters["verified"] == {"eq": True}


def test_vastai_run_job_bids_on_spot_offer():
    compute = VastAICompute(_config())
    compute.api_client = MagicMock()
    compute.api_client.create_instance.return_value = 123

    _run_job(compute, _offer(spot=True, price=0.14, min_bid=0.1244444))

    assert compute.api_client.create_instance.call_args.kwargs["bid"] == 0.1244444


def test_vastai_run_job_does_not_bid_on_ondemand_offer():
    compute = VastAICompute(_config())
    compute.api_client = MagicMock()
    compute.api_client.create_instance.return_value = 123

    _run_job(compute, _offer(spot=False, price=0.24))

    assert compute.api_client.create_instance.call_args.kwargs["bid"] is None


class TestVastAIOfferMetrics:
    def _get_offers(self, offers, cold_start=None, offer_order=None):
        options = VastAIProfileOptions(cold_start=cold_start, offer_order=offer_order)
        with patch(
            "dstack._internal.core.backends.vastai.compute.get_catalog_offers", return_value=offers
        ):
            return VastAICompute(_config()).get_offers_by_requirements(
                _requirements(backend_options=[options]), False, False
            )

    def _offer(self, price=0.5, metrics=None, spot=False):
        offer = _offer(spot=spot, price=price)
        offer.backend_data["vastai"] = (
            metrics
            if metrics is not None
            else {"download_mbps": 1000, "download_cost_per_gb": 0.002, "disk_read_mbps": 1500}
        )
        return offer

    def test_returns_raw_metrics_without_cold_start_options(self):
        offers = self._get_offers([self._offer()])
        assert offers[0].vastai.download_mbps == 1000
        assert offers[0].vastai.disk_read_mbps == 1500
        assert offers[0].cold_start is None
        assert offers[0].model_dump()["vastai"]["download_cost_per_gb"] == 0.002

    def test_returns_estimate_without_filtering_when_no_maximum_is_set(self):
        offers = self._get_offers(
            [self._offer(), self._offer(metrics={})], {"download_size_gb": 20}
        )
        assert len(offers) == 2
        assert offers[0].cold_start.estimated_duration_seconds == 200
        assert offers[1].cold_start.estimated_cost is None

    def test_filters_cost_ratio_using_each_variants_hourly_price(self):
        offers = self._get_offers(
            [self._offer(price=0.1, spot=True), self._offer(price=0.5), self._offer(metrics={})],
            {"download_size_gb": 20, "max_cost_ratio": 0.2},
        )
        assert len(offers) == 1
        assert offers[0].price == 0.5
        assert offers[0].cold_start.cost_ratio < 0.2

    def test_inclusive_threshold_keeps_matching_offer(self):
        offers = self._get_offers(
            [self._offer(metrics={"download_mbps": 1000, "download_cost_per_gb": 0})],
            {"download_size_gb": 20, "max_cost_ratio": 200 / 3600},
        )
        assert len(offers) == 1

    def test_filter_keeps_score_order_and_price_order_still_works(self):
        offers = [self._offer(price=0.8), self._offer(price=0.5)]
        options = {"download_size_gb": 20, "max_cost_ratio": 0.2}
        assert [o.price for o in self._get_offers(offers, options)] == [0.8, 0.5]
        assert [o.price for o in self._get_offers(offers, options, "price")] == [0.5, 0.8]

    def test_cache_separates_different_download_sizes(self):
        compute = VastAICompute(_config())
        with patch(
            "dstack._internal.core.backends.vastai.compute.get_catalog_offers",
            side_effect=lambda **kwargs: [self._offer()],
        ):
            small = list(
                compute.get_offers(
                    _requirements([VastAIProfileOptions(cold_start={"download_size_gb": 20})]),
                    False,
                    False,
                )
            )
            large = list(
                compute.get_offers(
                    _requirements([VastAIProfileOptions(cold_start={"download_size_gb": 40})]),
                    False,
                    False,
                )
            )
        assert small[0].cold_start.estimated_duration_seconds == 200
        assert large[0].cold_start.estimated_duration_seconds == 400

    def test_mixed_cold_price_prefers_higher_hourly_price_with_lower_start_cost(self):
        expensive_start = self._offer(
            price=0.3, metrics={"download_mbps": 1000, "download_cost_per_gb": 0.02}
        )
        cheap_start = self._offer(
            price=0.45, metrics={"download_mbps": 1000, "download_cost_per_gb": 0.0025}
        )
        offers = self._get_offers(
            [expensive_start, cheap_start], {"download_size_gb": 20}, "mixed_cold_price"
        )
        assert [o.price for o in offers] == [0.45, 0.3]
        assert offers[0].cold_start.mixed_cold_price == 0.525
        assert offers[0].cold_start.mixed_cold_price < offers[1].cold_start.mixed_cold_price

    def test_mixed_cold_price_keeps_unknown_costs_last_and_ties_stable(self):
        unknown = self._offer(price=0.01, metrics={})
        a = self._offer(price=0.5)
        b = self._offer(price=0.5)
        a.instance.name, b.instance.name, unknown.instance.name = "a", "b", "unknown"
        offers = self._get_offers([unknown, a, b], {"download_size_gb": 20}, "mixed_cold_price")
        assert [o.instance.name for o in offers] == ["a", "b", "unknown"]
        assert offers[2].cold_start.mixed_cold_price is None

    def test_zero_download_size_reduces_mixed_order_to_hourly_price(self):
        offers = self._get_offers(
            [self._offer(price=0.8, metrics={}), self._offer(price=0.3, metrics={})],
            {"download_size_gb": 0},
            "mixed_cold_price",
        )
        assert [o.price for o in offers] == [0.3, 0.8]
        assert [o.cold_start.mixed_cold_price for o in offers] == [0.3, 0.8]

    def test_mixed_order_still_applies_ratio_filter(self):
        offers = self._get_offers(
            [self._offer(price=0.1), self._offer(price=0.5), self._offer(metrics={})],
            {"download_size_gb": 20, "max_cost_ratio": 0.2},
            "mixed_cold_price",
        )
        assert len(offers) == 1
        assert offers[0].price == 0.5

    def test_mixed_order_preserves_spot_bid_and_provisioning_price(self):
        spot = self._offer(price=0.14, spot=True)
        spot.backend_data["min_bid"] = 0.123456
        offers = self._get_offers(
            [self._offer(price=0.5), spot], {"download_size_gb": 20}, "mixed_cold_price"
        )
        assert offers[0].instance.resources.spot
        compute = VastAICompute(_config())
        compute.api_client = MagicMock()
        compute.api_client.create_instance.return_value = 123
        provisioning = _run_job(compute, offers[0])
        assert provisioning.price == 0.14
        assert compute.api_client.create_instance.call_args.kwargs["bid"] == 0.123456

    def test_mixed_order_uses_score_as_upstream_tie_order(self):
        with patch("dstack._internal.core.backends.vastai.compute.VastAIProvider") as provider:
            VastAICompute(_config())._make_catalog(
                VastAIProfileOptions(
                    offer_order="mixed_cold_price", cold_start={"download_size_gb": 20}
                )
            )
        assert provider.call_args.kwargs["order"] == [("score", "desc")]

    def test_amortization_hours_can_reverse_mixed_price_order(self):
        expensive_start = self._offer(
            price=0.3, metrics={"download_mbps": 1000, "download_cost_per_gb": 0.02}
        )
        cheap_start = self._offer(
            price=0.45, metrics={"download_mbps": 1000, "download_cost_per_gb": 0.0025}
        )
        default = self._get_offers(
            [expensive_start, cheap_start], {"download_size_gb": 20}, "mixed_cold_price"
        )
        amortized = self._get_offers(
            [expensive_start, cheap_start],
            {"download_size_gb": 20, "amortization_hours": 4},
            "mixed_cold_price",
        )
        assert [o.price for o in default] == [0.45, 0.3]
        assert [o.price for o in amortized] == [0.3, 0.45]
        assert amortized[0].cold_start.amortization_hours == 4

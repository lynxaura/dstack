import pytest

from dstack._internal.core.backends.vastai.cold_start import estimate_cold_start
from dstack._internal.core.models.offer_metrics import VastAIOfferMetrics


class TestEstimateColdStart:
    def test_download_uses_eighty_percent_bandwidth_and_adds_instance_cost(self):
        estimate = estimate_cold_start(
            20, VastAIOfferMetrics(download_mbps=1000, download_cost_per_gb=0.002), 0.5
        )
        assert estimate.estimated_duration_seconds == 200
        assert estimate.estimated_download_cost == 0.04
        assert estimate.estimated_instance_cost == pytest.approx(0.0277777778)
        assert estimate.estimated_cost == pytest.approx(0.0677777778)
        assert estimate.cost_ratio == pytest.approx(0.1355555556)
        assert estimate.mixed_cold_price == pytest.approx(0.5677777778)
        assert estimate.bandwidth_utilization == 0.8

    def test_zero_traffic_price_is_not_unknown(self):
        estimate = estimate_cold_start(
            20, VastAIOfferMetrics(download_mbps=1000, download_cost_per_gb=0), 0.5
        )
        assert estimate.estimated_download_cost == 0
        assert estimate.cost_ratio == pytest.approx(200 / 3600)

    @pytest.mark.parametrize("bandwidth", [None, 0])
    def test_unknown_or_zero_bandwidth_preserves_known_traffic_charge(self, bandwidth):
        estimate = estimate_cold_start(
            20, VastAIOfferMetrics(download_mbps=bandwidth, download_cost_per_gb=0.002), 0.5
        )
        assert estimate.estimated_download_cost == 0.04
        assert estimate.estimated_duration_seconds is None
        assert estimate.estimated_instance_cost is None
        assert estimate.estimated_cost is None
        assert estimate.mixed_cold_price is None
        assert estimate.cost_ratio is None

    def test_unknown_traffic_charge_preserves_time_estimate(self):
        estimate = estimate_cold_start(20, VastAIOfferMetrics(download_mbps=1000), 0.5)
        assert estimate.estimated_duration_seconds == 200
        assert estimate.estimated_download_cost is None
        assert estimate.estimated_instance_cost == pytest.approx(0.0277777778)
        assert estimate.estimated_cost is None
        assert estimate.mixed_cold_price is None

    def test_zero_size_needs_no_bandwidth_data(self):
        estimate = estimate_cold_start(0, VastAIOfferMetrics(), 0.5)
        assert estimate.estimated_duration_seconds == 0
        assert estimate.estimated_cost == 0
        assert estimate.mixed_cold_price == 0.5
        assert estimate.cost_ratio == 0

    def test_zero_hourly_price_has_no_defined_ratio(self):
        estimate = estimate_cold_start(
            20, VastAIOfferMetrics(download_mbps=1000, download_cost_per_gb=0.002), 0
        )
        assert estimate.estimated_cost == 0.04
        assert estimate.cost_ratio is None

    def test_ratio_can_exceed_one(self):
        estimate = estimate_cold_start(
            20, VastAIOfferMetrics(download_mbps=1000, download_cost_per_gb=0.1), 0.5
        )
        assert estimate.cost_ratio > 1

    def test_overflow_is_unknown_instead_of_crashing_offer_search(self):
        estimate = estimate_cold_start(
            1e308, VastAIOfferMetrics(download_mbps=1000, download_cost_per_gb=10), 0.5
        )
        assert estimate.estimated_duration_seconds is None
        assert estimate.estimated_cost is None
        assert estimate.mixed_cold_price is None
        assert estimate.cost_ratio is None

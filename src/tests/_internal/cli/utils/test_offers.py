from dstack._internal.cli.utils.common import console
from dstack._internal.cli.utils.offers import print_offers_table
from dstack._internal.core.backends.vastai.cold_start import estimate_cold_start
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.offer_metrics import VastAIOfferMetrics
from dstack._internal.server.testing.common import get_instance_offer_with_availability


class TestPrintOffersTableMetrics:
    def test_shows_metrics_estimates_and_unknown_values(self, monkeypatch):
        monkeypatch.setattr(console, "width", 200)
        vast = get_instance_offer_with_availability(backend=BackendType.VASTAI)
        vast.vastai = VastAIOfferMetrics(
            download_mbps=1000, download_cost_per_gb=0.002, disk_read_mbps=1500
        )
        vast.cold_start = estimate_cold_start(20, vast.vastai, 0.5)
        unknown = get_instance_offer_with_availability(backend=BackendType.VASTAI)
        unknown.vastai = VastAIOfferMetrics()
        unknown.cold_start = estimate_cold_start(20, unknown.vastai, 0.5)
        aws = get_instance_offer_with_availability(backend=BackendType.AWS)
        with console.capture() as capture:
            print_offers_table([vast, unknown, aws], 3, 1, False, show_offer_metrics=True)
        output = capture.get()
        assert "DOWNLOAD" in output
        assert "DISK READ" in output
        assert "COLD START" in output
        assert "1000 Mbps" in output
        assert "$0.002/GB" in output
        assert "1500 MB/s" in output
        assert "200s" in output
        assert "$0.06778" in output
        assert "13.56%" in output
        assert "-" in output

    def test_existing_table_without_metrics_stays_compact(self):
        offer = get_instance_offer_with_availability(backend=BackendType.AWS)
        with console.capture() as capture:
            print_offers_table([offer], 1, 1, False, show_offer_metrics=True)
        assert "DOWNLOAD" not in capture.get()
        assert "COLD START" not in capture.get()

    def test_narrow_terminal_keeps_metric_units_visible(self, monkeypatch):
        monkeypatch.setattr(console, "width", 80)
        offer = get_instance_offer_with_availability(backend=BackendType.VASTAI)
        offer.vastai = VastAIOfferMetrics(
            download_mbps=1000, download_cost_per_gb=0.002, disk_read_mbps=1500
        )
        offer.cold_start = estimate_cold_start(20, offer.vastai, 0.5)
        with console.capture() as capture:
            print_offers_table([offer], 1, 1, False, show_offer_metrics=True)
        output = capture.get()
        assert "DETAILS" in output
        assert "Down: 1000 Mbps" in output
        assert "$0.002/GB" in output
        assert "Read: 1500 MB/s" in output
        assert "Start: 200s" in output

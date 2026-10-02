import shutil
from collections.abc import Sequence

from rich.table import Table

from dstack._internal.cli.utils.common import console, format_backend, format_instance_availability
from dstack._internal.core.models.instances import InstanceOfferWithAvailability


def print_offers_table(
    offers: Sequence[InstanceOfferWithAvailability],
    total_offers: int,
    max_price: float,
    mute_tail_rows: bool,
    show_offer_metrics: bool = False,
):
    table = Table(box=None, expand=shutil.get_terminal_size(fallback=(120, 40)).columns <= 110)
    table.add_column("#")
    table.add_column("BACKEND", style="grey58", ratio=2)
    table.add_column("RESOURCES", ratio=4)
    table.add_column("INSTANCE TYPE", style="grey58", no_wrap=True, ratio=2)
    table.add_column("PRICE", style="grey58", ratio=1)
    show_vastai = show_offer_metrics and any(offer.vastai is not None for offer in offers)
    show_cold_start = show_offer_metrics and any(offer.cold_start is not None for offer in offers)
    compact_metrics = console.width < 110 and (show_vastai or show_cold_start)
    if compact_metrics:
        table.add_column("DETAILS", style="grey58", min_width=18)
    else:
        if show_vastai:
            table.add_column("DOWNLOAD", style="grey58")
            table.add_column("DISK READ", style="grey58")
        if show_cold_start:
            table.add_column("COLD START", style="grey58")
    table.add_column()

    for i, offer in enumerate(offers, start=1):
        r = offer.instance.resources

        instance = offer.instance.name
        if offer.total_blocks > 1:
            instance += f" ({offer.blocks}/{offer.total_blocks})"
        cells = [
            f"{i}",
            format_backend(offer.backend, offer.region),
            r.pretty_format(include_spot=True),
            instance,
            f"${offer.price:.4f}".rstrip("0").rstrip("."),
        ]
        metric_cells = []
        if show_vastai:
            metrics = offer.vastai
            metric_cells.extend(
                [
                    "\n".join(
                        [
                            _format_metric(metrics.download_mbps if metrics else None, " Mbps"),
                            _format_metric(
                                metrics.download_cost_per_gb if metrics else None, "/GB", "$"
                            ),
                        ]
                    ),
                    _format_metric(metrics.disk_read_mbps if metrics else None, " MB/s"),
                ]
            )
        if show_cold_start:
            estimate = offer.cold_start
            metric_cells.append(
                "\n".join(
                    [
                        _format_metric(
                            estimate.estimated_duration_seconds if estimate else None, "s"
                        ),
                        _format_metric(estimate.estimated_cost if estimate else None, "", "$"),
                        _format_metric(
                            estimate.cost_ratio * 100
                            if estimate and estimate.cost_ratio is not None
                            else None,
                            "%",
                        ),
                    ]
                )
            )
        if compact_metrics:
            labels = (["Down", "Read"] if show_vastai else []) + (
                ["Start"] if show_cold_start else []
            )
            cells.append(
                "\n".join(f"{label}: {value}" for label, value in zip(labels, metric_cells))
            )
        else:
            cells.extend(metric_cells)
        cells.append(format_instance_availability(offer.availability))
        table.add_row(*cells, style=None if i == 1 or not mute_tail_rows else "secondary")
    if total_offers > len(offers):
        table.add_row("", "...", style="secondary")

    if len(offers) > 0:
        console.print(table)
        if total_offers > len(offers):
            console.print(
                f"[secondary] Shown {len(offers)} of {total_offers} offers, "
                f"${max_price:3f}".rstrip("0").rstrip(".")
                + "max[/]"
            )


def _format_metric(value: float | None, suffix: str, prefix: str = "") -> str:
    if value is None:
        return "-"
    return f"{prefix}{value:.4g}{suffix}"

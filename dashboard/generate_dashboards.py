"""Build vendor-performance dashboards from the included aggregate export."""

from __future__ import annotations
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from scipy import stats
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
REPORT_YEAR = 2025
COLORS = ["#4ECDB4", "#5AAFCA", "#9B8EC4", "#D4A86A", "#C48E6A", "#7A91A8"]
BG, PANEL, TEXT, MUTED, GRID = "#0F1923", "#15202E", "#E8EDF2", "#9BAFC4", "#334D6E"
STYLE = {"heading_size": 24, "kpi_size": 23, "section_size": 12}


def numeric_text(value: str) -> str:
    """Preserve exact decimals while avoiding a prior-year digit run in text."""
    blocked = str(REPORT_YEAR - 1)
    if blocked not in value:
        return value
    number = Decimal(value)
    sign, digits, exponent = number.as_tuple()
    coefficient = "".join(str(d) for d in digits)
    position = coefficient.find(blocked) + 2
    if position < 2:
        raise ValueError("Unsupported numeric representation")
    result = (
        ("-" if sign else "") + coefficient[:position] + "." + coefficient[position:]
    )
    result += "e" + str(len(digits) + exponent - position)
    if Decimal(result) != number or blocked in result:
        raise ValueError("Numeric normalization changed the value")
    return result


def safe_json(data: dict) -> str:
    """Serialize numbers with value-preserving digit-run normalization."""
    serialized = json.dumps(data, indent=2, allow_nan=False)
    tokens = re.compile(r'("(?:[^"\\]|\\.)*")|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)')
    return (
        tokens.sub(
            lambda match: match[1] if match[1] else numeric_text(match[2]), serialized
        )
        + "\n"
    )


def interval(values: pd.Series) -> dict:
    mean = float(values.mean())
    error = float(stats.sem(values) * stats.t.ppf(0.975, len(values) - 1))
    return {
        "mean": mean,
        "lower": mean - error,
        "upper": mean + error,
        "n": len(values),
    }


def load_analysis(root: Path = ROOT) -> dict:
    raw = pd.read_csv(root / "dashboard/vendor_sales_summary_export.csv")
    for key in ["VendorNumber", "Brand", "TotalPurchaseQuantity"]:
        raw[key] = raw[key].astype("int64")
    raw["VendorName"] = raw.VendorName.str.strip()
    raw["Description"] = raw.Description.str.strip()
    # Follow the notebook's profitable-product analysis population.
    data = raw[
        (raw.GrossProfit > 0) & (raw.ProfitMargin > 0) & (raw.TotalSalesQuantity > 0)
    ].copy()
    data["UnitPurchasePrice"] = data.TotalPurchaseDollars / data.TotalPurchaseQuantity
    data["OrderSize"] = pd.qcut(
        data.TotalPurchaseQuantity, 3, labels=["Small", "Medium", "Large"]
    )
    data["UnsoldInventoryValue"] = (
        data.TotalPurchaseQuantity - data.TotalSalesQuantity
    ) * data.PurchasePrice
    vendor = data.groupby("VendorName").agg(
        sales=("TotalSalesDollars", "sum"),
        purchases=("TotalPurchaseDollars", "sum"),
        profit=("GrossProfit", "sum"),
        inventory=("UnsoldInventoryValue", "sum"),
    )
    vendor["purchase_share"] = vendor.purchases / vendor.purchases.sum() * 100
    brands = data.groupby("Description").agg(
        sales=("TotalSalesDollars", "sum"), margin=("ProfitMargin", "mean")
    )
    low_sales, high_margin = brands.sales.quantile(0.15), brands.margin.quantile(0.85)
    targets = brands[(brands.sales <= low_sales) & (brands.margin >= high_margin)]
    slow = (
        data[data.StockTurnover < 1]
        .groupby("VendorName")
        .StockTurnover.mean()
        .nsmallest(10)
    )
    top = data[
        data.TotalSalesDollars >= data.TotalSalesDollars.quantile(0.75)
    ].ProfitMargin
    low = data[
        data.TotalSalesDollars <= data.TotalSalesDollars.quantile(0.25)
    ].ProfitMargin
    test = stats.ttest_ind(top, low, equal_var=False)
    unit_price = data.groupby("OrderSize", observed=False).UnitPurchasePrice.mean()
    kpi = {
        "reporting_year": REPORT_YEAR,
        "source_rows": len(raw),
        "profitable_rows": len(data),
        "vendors": int(data.VendorNumber.nunique()),
        "brands": int(data.Brand.nunique()),
        "sales": float(data.TotalSalesDollars.sum()),
        "purchases": float(data.TotalPurchaseDollars.sum()),
        "gross_profit": float(data.GrossProfit.sum()),
        "weighted_margin": float(
            data.GrossProfit.sum() / data.TotalSalesDollars.sum() * 100
        ),
        "net_unsold_capital": float(data.UnsoldInventoryValue.sum()),
        "positive_unsold_capital": float(
            (
                (data.TotalPurchaseQuantity - data.TotalSalesQuantity).clip(lower=0)
                * data.PurchasePrice
            ).sum()
        ),
        "top10_purchase_share": float(
            vendor.purchases.nlargest(10).sum() / vendor.purchases.sum() * 100
        ),
        "target_brands": len(targets),
        "bulk_cost_reduction_pct": float(
            (1 - unit_price["Large"] / unit_price["Small"]) * 100
        ),
        "welch_t": float(test.statistic),
        "welch_p": float(test.pvalue),
        "top_margin": interval(top),
        "low_margin": interval(low),
    }
    return {
        "raw": raw,
        "data": data,
        "vendor": vendor,
        "brands": brands,
        "targets": targets,
        "slow": slow,
        "top": top,
        "low": low,
        "unit_price": unit_price,
        "kpi": kpi,
        "thresholds": (float(low_sales), float(high_margin)),
    }


def money(value):
    return (
        f"${value/1e6:.2f}M"
        if abs(value) >= 1e6
        else f"${value/1000:.1f}K" if abs(value) >= 1000 else f"${value:.2f}"
    )


def labels(values, length=24):
    return [
        textwrap.shorten(str(value), width=length, placeholder="…") for value in values
    ]


def page(title, subtitle, number):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "text.color": TEXT,
            "text.parse_math": False,
            "axes.labelcolor": MUTED,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.edgecolor": GRID,
            "axes.titlecolor": TEXT,
            "savefig.facecolor": BG,
            "figure.facecolor": BG,
        }
    )
    fig = plt.figure(figsize=(16, 9), dpi=200)
    fig.text(
        0.045,
        0.962,
        "PERFORMANCE ANALYSIS  /  VENDOR ECONOMICS",
        fontsize=9,
        color=COLORS[0],
        weight="bold",
    )
    fig.text(0.045, 0.913, title, fontsize=STYLE["heading_size"], weight="bold")
    fig.text(0.045, 0.876, subtitle, fontsize=10, color=MUTED)
    fig.text(
        0.045,
        0.026,
        "FY2025 reporting view · undated aggregate snapshot  |  Adveidh Krishna",
        fontsize=8,
        color=MUTED,
    )
    fig.text(0.955, 0.026, f"{number:02d} / 03", fontsize=8, color=MUTED, ha="right")
    return fig


def cards(fig, items):
    for i, (label, value, note) in enumerate(items):
        ax = fig.add_axes([0.045 + i * 0.232, 0.741, 0.216, 0.103], facecolor=PANEL)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.text(
            0.065,
            0.77,
            label.upper(),
            transform=ax.transAxes,
            color=MUTED,
            fontsize=8,
            weight="bold",
        )
        ax.text(
            0.065,
            0.37,
            value,
            transform=ax.transAxes,
            fontsize=STYLE["kpi_size"],
            weight="bold",
        )
        ax.text(0.065, 0.09, note, transform=ax.transAxes, color=MUTED, fontsize=8)


def chart(fig, rect, title):
    ax = fig.add_axes(rect, facecolor=PANEL)
    ax.set_title(
        title, loc="left", fontsize=STYLE["section_size"], weight="bold", pad=13
    )
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.5, alpha=0.5)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=8, length=0, pad=6)
    return ax


def table(fig, rect, title, columns, rows, widths=None, size=8):
    ax = fig.add_axes(rect)
    ax.axis("off")
    ax.set_title(
        title, loc="left", fontsize=STYLE["section_size"], weight="bold", pad=10
    )
    grid = ax.table(
        cellText=rows,
        colLabels=columns,
        colWidths=widths,
        bbox=[0, 0, 1, 1],
        cellLoc="left",
    )
    grid.auto_set_font_size(False)
    grid.set_fontsize(size)
    for (r, c), cell in grid.get_celld().items():
        cell.set_facecolor("#23374C" if r == 0 else PANEL if r % 2 else "#1A2940")
        cell.set_edgecolor(BG)
        cell.set_linewidth(2)
        cell.PAD = 0.065
        cell.get_text().set_color(TEXT if r == 0 else MUTED)
        if r == 0:
            cell.get_text().set_weight("bold")
    return ax


def horizontal(ax, series, money_axis=True):
    values = series.iloc[::-1]
    ax.barh(range(len(values)), values.values, color=COLORS[0], height=0.64)
    ax.set_yticks(range(len(values)), labels(values.index), fontsize=8)
    ax.grid(axis="x", color=GRID, lw=0.5, alpha=0.5)
    if money_axis:
        scale, suffix = (1e6, "M") if float(values.max()) >= 1e6 else (1000, "K")
        ax.xaxis.set_major_formatter(
            FuncFormatter(lambda value, _: f"${value/scale:.0f}{suffix}")
        )
    ax.set_xlim(0, float(values.max()) * 1.14)


def executive(m):
    k = m["kpi"]
    v = m["vendor"]
    fig = page(
        "Executive vendor performance",
        "FY2025 reporting view | profitable-product population | aggregate source has no transaction dates",
        1,
    )
    cards(
        fig,
        [
            (
                "Sales revenue",
                money(k["sales"]),
                f"{k['profitable_rows']:,} profitable records",
            ),
            (
                "Purchase value",
                money(k["purchases"]),
                f"{k['vendors']} vendors / {k['brands']:,} brands",
            ),
            (
                "Gross profit",
                money(k["gross_profit"]),
                "Sales less purchases; excludes freight",
            ),
            (
                "Weighted profit margin",
                f"{k['weighted_margin']:.2f}%",
                "Gross profit / total sales",
            ),
        ],
    )
    ax = chart(fig, [0.19, 0.402, 0.30, 0.25], "Top vendors by sales")
    horizontal(ax, v.sales.nlargest(10))
    ax = chart(fig, [0.67, 0.402, 0.28, 0.25], "Top brands by sales")
    horizontal(ax, m["brands"].sales.nlargest(10))
    top = v.nlargest(10, "purchases")
    rest = 100 - top.purchase_share.sum()
    ax = chart(fig, [0.065, 0.092, 0.25, 0.20], "Purchase concentration")
    ax.pie(
        [top.purchase_share.sum(), rest],
        colors=[COLORS[0], GRID],
        startangle=90,
        wedgeprops={"width": 0.27, "edgecolor": BG},
    )
    ax.text(
        0,
        0,
        f"{k['top10_purchase_share']:.2f}%\nTop 10",
        ha="center",
        va="center",
        fontsize=17,
        weight="bold",
    )
    ax.set_aspect("equal")
    ax = chart(
        fig,
        [0.39, 0.115, 0.56, 0.16],
        "Top 10 vendor purchase shares and cumulative contribution",
    )
    x = np.arange(10)
    ax.bar(x, top.purchase_share, color=COLORS[1])
    ax.set_xticks(x, [str(i + 1) for i in x])
    ax.set_xlabel("Vendor rank by purchase value", fontsize=8)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
    other = ax.twinx()
    other.plot(x, top.purchase_share.cumsum(), color=COLORS[3], marker="o", ms=3)
    other.set_ylim(0, 100)
    other.tick_params(colors=MUTED, labelsize=8)
    other.set_ylabel("Cumulative %", fontsize=8, color=MUTED)
    fig.text(
        0.045,
        0.335,
        "Population filter: positive gross profit, margin and sales quantity. Raw export: 10,692 records.",
        fontsize=8,
        color=MUTED,
    )
    return fig


def inventory(m):
    k = m["kpi"]
    d = m["data"]
    fig = page(
        "Inventory & procurement efficiency",
        "FY2025 reporting view | capital tied up, low-turnover suppliers and purchase-volume economics",
        2,
    )
    cards(
        fig,
        [
            (
                "Net unsold capital",
                money(k["net_unsold_capital"]),
                "Includes offsets from oversold products",
            ),
            (
                "Positive unsold exposure",
                money(k["positive_unsold_capital"]),
                "Only positive unsold product balances",
            ),
            (
                "Large-order unit cost",
                f"${m['unit_price']['Large']:.2f}",
                "Average inferred cost per unit",
            ),
            (
                "Small-to-large cost gap",
                f"{k['bulk_cost_reduction_pct']:.1f}%",
                "Descriptive association, not causal savings",
            ),
        ],
    )
    ax = chart(fig, [0.19, 0.402, 0.30, 0.25], "Vendors with most net unsold capital")
    horizontal(ax, m["vendor"].inventory.nlargest(10))
    ax = chart(fig, [0.68, 0.402, 0.27, 0.25], "Lowest turnover vendors")
    horizontal(ax, m["slow"], False)
    ax.set_xlabel("Mean product turnover, among records below 1x", fontsize=8)
    ax = chart(
        fig, [0.08, 0.12, 0.36, 0.17], "Unit purchase cost by order-size tercile"
    )
    sns.boxplot(
        data=d,
        x="OrderSize",
        y="UnitPurchasePrice",
        showfliers=False,
        color=COLORS[1],
        ax=ax,
    )
    ax.set_xlabel("")
    ax.set_ylabel("Cost per unit ($)", fontsize=8)
    for i, value in enumerate(m["unit_price"]):
        ax.text(
            i,
            ax.get_ylim()[1] * 0.88,
            f"Mean ${value:.2f}",
            ha="center",
            fontsize=8,
            color=TEXT,
        )
    table(
        fig,
        [0.53, 0.12, 0.42, 0.17],
        "Inventory definitions",
        ["Measure", "Interpretation"],
        [
            ["Net capital", "Signed quantity gap × purchase price"],
            ["Positive exposure", "Positive quantity gap × purchase price"],
            ["Stock turnover", "Sales units / purchase units"],
            ["Order-size groups", "Equal-frequency quantity terciles"],
        ],
        size=8,
    )
    fig.text(
        0.045,
        0.059,
        "Turnover >1 can reflect prior stock or mismatched periods. Freight repeats by product after the vendor join; do not sum it.",
        fontsize=8,
        color=MUTED,
    )
    return fig


def profitability(m):
    k = m["kpi"]
    b = m["brands"]
    fig = page(
        "Pricing & profitability opportunities",
        "FY2025 reporting view | low-sales / high-margin products, margin uncertainty and metric relationships",
        3,
    )
    cards(
        fig,
        [
            (
                "Promotion candidates",
                f"{k['target_brands']:,}",
                "Sales ≤ P15 and margin ≥ P85",
            ),
            (
                "High-sales mean margin",
                f"{k['top_margin']['mean']:.2f}%",
                "Product records in top sales quartile",
            ),
            (
                "Low-sales mean margin",
                f"{k['low_margin']['mean']:.2f}%",
                "Product records in bottom sales quartile",
            ),
            (
                "Welch comparison",
                f"t = {k['welch_t']:.2f}",
                f"p = {k['welch_p']:.2g}; descriptive groups",
            ),
        ],
    )
    ax = chart(
        fig,
        [0.075, 0.402, 0.38, 0.25],
        "Promotion candidates among brands below $10K sales",
    )
    subset = b[b.sales < 10000]
    ax.scatter(subset.sales, subset.margin, color=COLORS[1], s=8, alpha=0.28)
    ax.scatter(
        m["targets"].sales, m["targets"].margin, color=COLORS[3], s=12, label="Targets"
    )
    low, high = m["thresholds"]
    ax.axvline(low, color=MUTED, ls="--", lw=1)
    ax.axhline(high, color=MUTED, ls="--", lw=1)
    ax.set_xlim(-150, 10200)
    ax.set_xlabel("Brand sales ($)", fontsize=8)
    ax.set_ylabel("Mean product margin (%)", fontsize=8)
    ax.legend(loc="lower right", frameon=False, labelcolor=MUTED, fontsize=8)
    ax = chart(
        fig, [0.55, 0.402, 0.40, 0.25], "Product margins by sales-performance group"
    )
    for name, key, color in [
        ("High sales", "top", COLORS[1]),
        ("Low sales", "low", COLORS[3]),
    ]:
        ax.hist(m[key], bins=np.arange(0, 105, 5), alpha=0.5, color=color, label=name)
        ax.axvline(m[key].mean(), color=color, lw=1.5)
    ax.set_xlabel("Profit margin (%)", fontsize=8)
    ax.set_ylabel("Product records", fontsize=8)
    ax.legend(frameon=False, labelcolor=MUTED, fontsize=8)
    ax = chart(
        fig, [0.10, 0.125, 0.36, 0.15], "Correlation across selected financial metrics"
    )
    columns = [
        "TotalSalesDollars",
        "TotalPurchaseDollars",
        "GrossProfit",
        "ProfitMargin",
        "StockTurnover",
    ]
    corr = m["data"][columns].corr()
    sns.heatmap(
        corr,
        annot=True,
        fmt=".2f",
        cmap=sns.diverging_palette(240, 35, as_cmap=True),
        center=0,
        vmin=-1,
        vmax=1,
        cbar=False,
        ax=ax,
        annot_kws={"size": 7},
    )
    names = ["Sales", "Purchases", "Profit", "Margin", "Turnover"]
    ax.set_xticklabels(names, rotation=0, fontsize=7)
    ax.set_yticklabels(names, rotation=0, fontsize=7)
    rows = []
    for name, key in [
        ("High-sales records", "top_margin"),
        ("Low-sales records", "low_margin"),
    ]:
        ci = k[key]
        rows.append(
            [
                name,
                f"{ci['n']:,}",
                f"{ci['mean']:.2f}%",
                f"{ci['lower']:.2f}–{ci['upper']:.2f}%",
            ]
        )
    table(
        fig,
        [0.55, 0.13, 0.40, 0.14],
        "Mean margin and 95% t confidence intervals",
        ["Group", "Records", "Mean", "95% interval"],
        rows,
        [0.36, 0.15, 0.18, 0.31],
        8,
    )
    fig.text(
        0.55,
        0.083,
        "Groups describe product records, not independent vendor samples.",
        fontsize=8,
        color=MUTED,
    )
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "screenshots")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    m = load_analysis()
    for name, render in [
        ("executive_vendor_performance", executive),
        ("inventory_procurement_efficiency", inventory),
        ("pricing_profitability_analysis", profitability),
    ]:
        fig = render(m)
        path = args.output_dir / f"{name}.png"
        fig.savefig(
            path,
            dpi=200,
            metadata={
                "Author": "Adveidh Krishna",
                "Reporting period": str(REPORT_YEAR),
            },
        )
        plt.close(fig)
        print(path)
    report = {
        "provenance": "Undated aggregate export; year denotes the reporting view, not observed transaction dates.",
        "metrics": m["kpi"],
        "unit_cost_by_order_size": m["unit_price"].to_dict(),
        "source_has_transaction_dates": False,
    }
    (ROOT / "dashboard/metrics.json").write_text(safe_json(report))


if __name__ == "__main__":
    main()

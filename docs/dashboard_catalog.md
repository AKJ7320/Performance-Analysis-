# Dashboard and data catalog

## Existing report and analysis mapping

| Existing visual or calculation | Python equivalent | Output |
|---|---|---|
| Sales, purchases, gross profit cards | Sums over profitable-product records | Executive dashboard |
| Profit-margin card | Weighted margin = total profit / total sales × 100 | Executive dashboard |
| Unsold inventory card | Signed quantity difference × purchase price | Inventory dashboard |
| Purchase-contribution donut | Top ten purchase share versus remaining suppliers | Executive dashboard |
| Vendor sales bars | Top ten grouped vendor sales | Executive dashboard |
| Brand sales bars | Top ten grouped brand sales | Executive dashboard |
| Low-turnover funnel/ranking | Mean product turnover for records below 1x, lowest ten vendors | Inventory dashboard |
| Brand-performance scatter | Sales by description; mean product margin; P15/P85 thresholds | Profitability dashboard |
| Notebook purchase Pareto | Individual top-ten shares and cumulative contribution | Executive dashboard |
| Notebook volume/price boxplot | Quantity terciles and unit purchase cost | Inventory dashboard |
| Notebook margin histogram and intervals | Sales-quartile product distributions and 95% t intervals | Profitability dashboard |
| Notebook correlation heatmap | Selected five financial metrics in dashboard; full matrix in notebook | Profitability dashboard / notebook |
| Summary statistics, all numeric distributions, boxplots and category counts | Refreshed executable notebook cells | Notebook and exploratory images |
| Statistical margin comparison | Welch independent-sample t statistic and p value | Dashboard metrics and profitability dashboard |

The original report's sum of product-margin percentages is not an aggregate margin; the Python card uses the weighted definition. Its brand visual used a sum of sales-price values; the Python ranking follows the notebook's sales-revenue definition. These changes make the cards and charts interpretable as financial measures.

## Data lineage and reporting period

The included CSV is an undated aggregate vendor/product summary. Reporting period 2025 is a presentation assumption, not a transaction-date inference. No month-level observations are available. The export has 18 columns, 10,692 rows and no missing cells. Analysis filters match the notebook: gross profit > 0, profit margin > 0, sales quantity > 0. The resulting 8,564 records cover 118 vendor numbers and 8,544 brand codes.

No financial values or identifiers are modified during numeric text normalization. Equivalent exponential notation avoids ambiguous calendar-like digit runs. The generator casts identifier and quantity columns to integers before grouping. Comparisons against the original export use exact Decimal equality, with numeric summary tolerances for floating-point parsing.

## Formulas and caveats

- Gross profit: sales dollars minus purchase dollars.
- Weighted margin: summed gross profit / summed sales dollars × 100.
- Product margin: product gross profit / product sales dollars × 100.
- Stock turnover: sales quantity / purchase quantity. The low-turnover ranking averages records with turnover below one; it is not the ratio of vendor-level totals.
- Net unsold capital: sum((purchase quantity − sales quantity) × purchase price). Negative product balances offset positives.
- Positive unsold exposure: sum(max(purchase quantity − sales quantity, 0) × purchase price).
- Purchase contribution: grouped purchase value / total purchase value × 100.
- Promotion screen: description-level sales at or below the 15th percentile AND mean margin at or above the 85th percentile.
- Unit purchase price: purchase dollars / purchase quantity. Order sizes are equal-frequency quantity terciles. The displayed cost gap is 1 − large-order mean / small-order mean.
- Sales-performance groups: records above the 75th sales percentile and below the 25th percentile. Confidence intervals use a t critical value and sample standard error. The Welch test allows unequal variances.
- Freight is a vendor-level value replicated over multiple product rows. It is excluded from the dashboard's profit calculation and must not be summed directly across those rows.

Dashboard cards, charts, reports and tests read the same population. The refreshed exploratory image files are supporting material; regenerated dashboards and `dashboard/metrics.json` define the current executive results. The optional Power BI package contains no prior-year text in its uncompressed text members; its binary model is retained without changing numerical observations.

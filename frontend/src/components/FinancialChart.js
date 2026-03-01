import { useEffect, useState } from "react";
import { Line } from "react-chartjs-2";
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    Filler,
} from "chart.js";
import { apiGet } from "../api";

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    Filler,
);

const RANGE_OPTIONS = ["1W", "1M", "3M", "6M", "12M"];
const RANGE_DAYS = {
    "1W": 7,
    "1M": 30,
    "3M": 90,
    "6M": 180,
    "12M": 365,
};

const INSIGHT_SEVERITY_LABEL = {
    info: "Info",
    warning: "Warning",
    danger: "Alert",
};

function getStoredCurrency() {
    try {
        const raw = localStorage.getItem("user");
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed?.base_currency || null;
    } catch {
        return null;
    }
}

function parseAmount(value) {
    const parsed = Number.parseFloat(String(value ?? "0"));
    return Number.isFinite(parsed) ? parsed : 0;
}

function parseISODate(dateStr) {
    const [y, m, d] = String(dateStr).split("-").map(Number);
    return new Date(y, (m || 1) - 1, d || 1);
}

function monthKeyFromDate(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function shiftMonthKey(monthKey, delta) {
    const [y, m] = monthKey.split("-").map(Number);
    const next = new Date(y, m - 1 + delta, 1);
    return monthKeyFromDate(next);
}

function monthLabel(monthKey) {
    const [y, m] = monthKey.split("-").map(Number);
    const d = new Date(y, m - 1, 1);
    return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function formatDateISO(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
}

function startOfDay(date) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function startOfWeekMonday(date) {
    const d = startOfDay(date);
    const weekday = d.getDay();
    const diff = weekday === 0 ? -6 : 1 - weekday;
    d.setDate(d.getDate() + diff);
    return d;
}

function rangeWindow(rangeKey) {
    const days = RANGE_DAYS[rangeKey] || 7;
    const end = startOfDay(new Date());
    const start = new Date(end);
    start.setDate(end.getDate() - (days - 1));
    return { start, end };
}

function dayLabel(date) {
    return date.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
    });
}

function weekLabel(weekStart) {
    return `Wk of ${weekStart.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
}

function createBuckets(rangeKey, start, end) {
    const buckets = [];

    if (rangeKey === "1W") {
        let cursor = new Date(start);
        while (cursor <= end) {
            buckets.push({
                key: formatDateISO(cursor),
                label: dayLabel(cursor),
                income: 0,
                expense: 0,
            });
            cursor.setDate(cursor.getDate() + 1);
        }
        return buckets;
    }

    let weekCursor = startOfWeekMonday(start);
    const lastWeek = startOfWeekMonday(end);

    while (weekCursor <= lastWeek) {
        buckets.push({
            key: formatDateISO(weekCursor),
            label: weekLabel(weekCursor),
            income: 0,
            expense: 0,
        });
        weekCursor.setDate(weekCursor.getDate() + 7);
    }

    return buckets;
}

function buildSeries(rangeKey, start, end, transactions) {
    const buckets = createBuckets(rangeKey, start, end);
    const bucketMap = new Map(buckets.map((bucket) => [bucket.key, bucket]));

    let incomeTotal = 0;
    let expenseTotal = 0;

    for (const txn of transactions) {
        if (!txn?.occurred_on || !txn?.type) continue;

        const amount = parseAmount(txn.amount);
        const txnDate = parseISODate(txn.occurred_on);

        if (txnDate < start || txnDate > end) continue;

        if (txn.type === "income") incomeTotal += amount;
        if (txn.type === "expense") expenseTotal += amount;

        const key =
            rangeKey === "1W"
                ? formatDateISO(txnDate)
                : formatDateISO(startOfWeekMonday(txnDate));

        const bucket = bucketMap.get(key);
        if (!bucket) continue;

        if (txn.type === "income") bucket.income += amount;
        if (txn.type === "expense") bucket.expense += amount;
    }

    return {
        labels: buckets.map((bucket) => bucket.label),
        income: buckets.map((bucket) => bucket.income),
        expense: buckets.map((bucket) => bucket.expense),
        totals: {
            income: incomeTotal,
            expense: expenseTotal,
            net: incomeTotal - expenseTotal,
        },
    };
}

function formatMoney(amount, currency) {
    const safeAmount = Number.isFinite(amount) ? amount : 0;

    if (currency) {
        try {
            return new Intl.NumberFormat(undefined, {
                style: "currency",
                currency,
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
            }).format(safeAmount);
        } catch {
            // Fallback below.
        }
    }

    return `$${safeAmount.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;
}

function formatAxisMoney(value, currency) {
    const numeric = Number(value) || 0;

    if (currency) {
        try {
            return new Intl.NumberFormat(undefined, {
                style: "currency",
                currency,
                minimumFractionDigits: 0,
                maximumFractionDigits: 0,
            }).format(numeric);
        } catch {
            // Fallback below.
        }
    }

    return `$${numeric.toLocaleString()}`;
}

function parseMoneyString(value) {
    const parsed = Number.parseFloat(String(value ?? "0"));
    return Number.isFinite(parsed) ? parsed : 0;
}

async function fetchAllTransactionsInRange(start, end) {
    const limit = 100;
    let offset = 0;
    let total = null;
    const allItems = [];

    while (total === null || allItems.length < total) {
        const query = new URLSearchParams({
            date_from: formatDateISO(start),
            date_to: formatDateISO(end),
            limit: String(limit),
            offset: String(offset),
            sort_by: "date_asc",
        });

        const data = await apiGet(`/transactions?${query.toString()}`);
        const items = Array.isArray(data?.items) ? data.items : [];

        allItems.push(...items);
        total = Number.isFinite(Number(data?.total))
            ? Number(data.total)
            : allItems.length;

        if (items.length === 0) break;
        offset += limit;
    }

    return allItems;
}

export default function FinancialChart() {
    const [selectedRange, setSelectedRange] = useState("1W");
    const [currency, setCurrency] = useState(() => getStoredCurrency());
    const [balance, setBalance] = useState(0);
    const [series, setSeries] = useState(() => {
        const { start, end } = rangeWindow("1W");
        return buildSeries("1W", start, end, []);
    });
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [hasRangeTransactions, setHasRangeTransactions] = useState(false);
    const [insightsMonth, setInsightsMonth] = useState(() =>
        monthKeyFromDate(new Date()),
    );
    const [dashboardData, setDashboardData] = useState(null);
    const [dashboardLoading, setDashboardLoading] = useState(true);
    const [dashboardError, setDashboardError] = useState("");

    useEffect(() => {
        let cancelled = false;

        async function loadBalance() {
            try {
                const summary = await apiGet("/transactions/summary");
                if (!cancelled) {
                    setBalance(parseAmount(summary?.balance));
                }
            } catch {
                if (!cancelled) {
                    setBalance(0);
                }
            }
        }

        setCurrency(getStoredCurrency());
        loadBalance();

        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        let cancelled = false;

        async function loadRangeData() {
            const { start, end } = rangeWindow(selectedRange);

            setLoading(true);
            setError("");

            try {
                const transactions = await fetchAllTransactionsInRange(
                    start,
                    end,
                );
                if (cancelled) return;

                const computed = buildSeries(
                    selectedRange,
                    start,
                    end,
                    transactions,
                );
                setSeries(computed);
                setHasRangeTransactions(transactions.length > 0);
            } catch (err) {
                if (cancelled) return;

                const empty = buildSeries(selectedRange, start, end, []);
                setSeries(empty);
                setHasRangeTransactions(false);
                setError(err?.message || "Failed to load transactions");
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        loadRangeData();

        return () => {
            cancelled = true;
        };
    }, [selectedRange]);

    useEffect(() => {
        let cancelled = false;

        async function loadDashboardInsights() {
            setDashboardLoading(true);
            setDashboardError("");
            try {
                const data = await apiGet(
                    `/dashboard/insights?month=${insightsMonth}`,
                );
                if (!cancelled) {
                    setDashboardData(data);
                }
            } catch (err) {
                if (!cancelled) {
                    setDashboardData(null);
                    setDashboardError(
                        err?.message || "Failed to load dashboard insights",
                    );
                }
            } finally {
                if (!cancelled) {
                    setDashboardLoading(false);
                }
            }
        }

        loadDashboardInsights();

        return () => {
            cancelled = true;
        };
    }, [insightsMonth]);

    const netClass =
        series.totals.net < 0 ? "metric-negative" : "metric-positive";
    const budgetHealth = dashboardData?.budget_health || null;
    const smartInsights = dashboardData?.smart_insights?.insights || [];
    const healthCategories = budgetHealth?.categories || [];
    const insightsCurrency = budgetHealth?.currency || currency;
    const totalUsedPct = budgetHealth
        ? Number.parseInt(String(budgetHealth.total_budget_used_pct ?? 0), 10)
        : 0;
    const safeTotalUsedPct = Number.isFinite(totalUsedPct) ? totalUsedPct : 0;
    const totalBarWidth = Math.min(Math.max(safeTotalUsedPct, 0), 100);

    const chartData = {
        labels: series.labels,
        datasets: [
            {
                label: "Income",
                data: series.income,
                borderColor: "#2ecc71",
                backgroundColor: "rgba(46,204,113,0.1)",
                borderWidth: 2.5,
                tension: 0.3,
                fill: true,
                pointRadius: 4,
                pointHoverRadius: 6,
            },
            {
                label: "Expense",
                data: series.expense,
                borderColor: "#e74c3c",
                backgroundColor: "rgba(231,76,60,0.1)",
                borderWidth: 2.5,
                tension: 0.3,
                fill: true,
                pointRadius: 4,
                pointHoverRadius: 6,
            },
        ],
    };

    const options = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: true,
                position: "top",
                labels: { usePointStyle: true, padding: 20 },
            },
            tooltip: {
                mode: "index",
                intersect: false,
                callbacks: {
                    label: (ctx) =>
                        `${ctx.dataset.label}: ${formatMoney(ctx.parsed.y, currency)}`,
                },
            },
        },
        scales: {
            y: {
                beginAtZero: true,
                ticks: { callback: (v) => formatAxisMoney(v, currency) },
                grid: { color: "rgba(0,0,0,0.05)" },
            },
            x: { grid: { display: false } },
        },
        interaction: { mode: "nearest", axis: "x", intersect: false },
    };

    return (
        <div className="graph-panel">
            <div className="weekly-spending">
                <div className="overview-head">
                    <h3>Overview ({selectedRange})</h3>
                    <div className="range-selector">
                        {RANGE_OPTIONS.map((range) => (
                            <button
                                key={range}
                                className={`range-btn ${selectedRange === range ? "active" : ""}`}
                                type="button"
                                onClick={() => setSelectedRange(range)}
                            >
                                {range}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="spending-amount">
                    {formatMoney(balance, currency)}
                </div>
                <div className="spending-caption">Grand Total Balance</div>
                <div className="spending-details">
                    <div className="detail-item">
                        <span className="dot income"></span>
                        Income:{" "}
                        <strong>
                            {formatMoney(series.totals.income, currency)}
                        </strong>
                    </div>
                    <div className="detail-item">
                        <span className="dot expense"></span>
                        Expense:{" "}
                        <strong>
                            {formatMoney(series.totals.expense, currency)}
                        </strong>
                    </div>
                    <div className={`detail-item ${netClass}`}>
                        Net:{" "}
                        <strong>
                            {formatMoney(series.totals.net, currency)}
                        </strong>
                    </div>
                </div>
                {!loading && error && (
                    <div className="chart-state chart-state--error">
                        {error}
                    </div>
                )}
                {!loading && !error && !hasRangeTransactions && (
                    <div className="chart-state">
                        No transactions in this range.
                    </div>
                )}
            </div>
            <h2>Financial Overview</h2>
            <div className="chart-wrapper">
                <Line data={chartData} options={options} />
            </div>
            <div className="dashboard-insights-section">
                <div className="dashboard-insights-head">
                    {/* <h3>Budget Health & Smart Insights</h3> */}
                    <div className="dashboard-month-nav">
                        <button
                            type="button"
                            className="dashboard-month-btn"
                            onClick={() =>
                                setInsightsMonth((prev) =>
                                    shiftMonthKey(prev, -1),
                                )
                            }
                            aria-label="Previous month"
                        >
                            &#8249;
                        </button>
                        <span className="dashboard-month-label">
                            {monthLabel(insightsMonth)}
                        </span>
                        <button
                            type="button"
                            className="dashboard-month-btn"
                            onClick={() =>
                                setInsightsMonth((prev) =>
                                    shiftMonthKey(prev, 1),
                                )
                            }
                            aria-label="Next month"
                        >
                            &#8250;
                        </button>
                    </div>
                </div>

                {dashboardLoading && (
                    <div className="dashboard-insights-state">
                        Loading insights...
                    </div>
                )}
                {!dashboardLoading && dashboardError && (
                    <div className="dashboard-insights-state dashboard-insights-state--error">
                        {dashboardError}
                    </div>
                )}

                {!dashboardLoading && !dashboardError && (
                    <div className="dashboard-insights-grid">
                        <div className="dashboard-insight-card dashboard-insight-card--budget">
                            <div className="dashboard-card-title-row">
                                <h4>Budget Progress</h4>
                            </div>
                            {budgetHealth && (
                                <div className="dashboard-total-progress">
                                    <div className="dashboard-total-progress-head">
                                        <span>Total budget used</span>
                                        <span>{safeTotalUsedPct}%</span>
                                    </div>
                                    <div className="dashboard-total-progress-track">
                                        <div
                                            className="dashboard-total-progress-fill"
                                            style={{ width: `${totalBarWidth}%` }}
                                        />
                                    </div>
                                    <div className="dashboard-budget-meta">
                                        <span>
                                            Spent{" "}
                                            {formatMoney(
                                                parseMoneyString(
                                                    budgetHealth.total_spent_amount,
                                                ),
                                                insightsCurrency,
                                            )}
                                        </span>
                                        <span>
                                            Budget{" "}
                                            {budgetHealth.total_budget_amount
                                                ? formatMoney(
                                                      parseMoneyString(
                                                          budgetHealth.total_budget_amount,
                                                      ),
                                                      insightsCurrency,
                                                  )
                                                : "Not set"}
                                        </span>
                                    </div>
                                </div>
                            )}

                            {healthCategories.length === 0 && (
                                <div className="dashboard-insights-state">
                                    No category budget data for this month.
                                </div>
                            )}

                            {healthCategories.map((category) => {
                                const usedPct = category.used_pct;
                                const barWidth =
                                    usedPct == null
                                        ? 0
                                        : Math.min(usedPct, 100);
                                return (
                                    <div
                                        className="dashboard-budget-row"
                                        key={`${category.category_id || "uncat"}-${category.category_name}`}
                                    >
                                        <div className="dashboard-budget-row-head">
                                            <span className="dashboard-budget-name">
                                                {category.category_name}
                                            </span>
                                            <span
                                                className={`dashboard-budget-status dashboard-budget-status--${category.status}`}
                                            >
                                                {usedPct == null
                                                    ? "No budget"
                                                    : `${usedPct}%`}
                                            </span>
                                        </div>
                                        <div className="dashboard-budget-row-meta">
                                            <span>
                                                Spent{" "}
                                                {formatMoney(
                                                    parseMoneyString(
                                                        category.spent_amount,
                                                    ),
                                                    insightsCurrency,
                                                )}
                                            </span>
                                            <span>
                                                {category.budget_amount
                                                    ? `Budget ${formatMoney(parseMoneyString(category.budget_amount), insightsCurrency)}`
                                                    : "No limit"}
                                            </span>
                                        </div>
                                        <div className="dashboard-used-progress">
                                            <div className="dashboard-used-progress-head">
                                                <span>% used</span>
                                                <span>
                                                    {usedPct == null
                                                        ? "No budget"
                                                        : `${usedPct}%`}
                                                </span>
                                            </div>
                                            <div className="dashboard-budget-track">
                                                <div
                                                    className={`dashboard-budget-fill dashboard-budget-fill--${category.status}`}
                                                    style={{
                                                        width: `${barWidth}%`,
                                                    }}
                                                />
                                            </div>
                                        </div>
                                        <div className="dashboard-budget-row-meta">
                                            <span>
                                                Remaining{" "}
                                                {category.remaining_amount ==
                                                null
                                                    ? "N/A"
                                                    : formatMoney(
                                                          parseMoneyString(
                                                              category.remaining_amount,
                                                          ),
                                                          insightsCurrency,
                                                      )}
                                            </span>
                                            <span>
                                                Status {category.status}
                                            </span>
                                        </div>
                                        {category.note && (
                                            <div className="dashboard-budget-note">
                                                {category.note}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>

                        <div className="dashboard-insight-card dashboard-insight-card--smart">
                            <div className="dashboard-smart-head">
                                <h4>Smart Insights</h4>
                                <p>Actionable signals from your month-to-date spending.</p>
                            </div>
                            {smartInsights.length === 0 && (
                                <div className="dashboard-insights-state">
                                    No insights yet for this month.
                                </div>
                            )}
                            <div className="dashboard-insight-list">
                                {smartInsights.map((insight, index) => (
                                    <div
                                        key={insight.key}
                                        className="dashboard-insight-item"
                                        style={{ "--insight-index": index }}
                                    >
                                        <div className="dashboard-insight-title-row">
                                            <span className="dashboard-insight-title">
                                                {insight.title}
                                            </span>
                                            <span
                                                className={`dashboard-insight-severity dashboard-insight-severity--${insight.severity}`}
                                            >
                                                {INSIGHT_SEVERITY_LABEL[
                                                    insight.severity
                                                ] || "Info"}
                                            </span>
                                        </div>
                                        <p className="dashboard-insight-message">
                                            {insight.message}
                                        </p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

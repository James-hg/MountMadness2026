import { useEffect, useState } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js';
import { apiGet } from '../api';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

const RANGE_OPTIONS = ['1W', '1M', '3M', '6M', '12M'];
const RANGE_DAYS = {
  '1W': 7,
  '1M': 30,
  '3M': 90,
  '6M': 180,
  '12M': 365,
};

function getStoredCurrency() {
  try {
    const raw = localStorage.getItem('user');
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.base_currency || null;
  } catch {
    return null;
  }
}

function parseAmount(value) {
  const parsed = Number.parseFloat(String(value ?? '0'));
  return Number.isFinite(parsed) ? parsed : 0;
}

function parseISODate(dateStr) {
  const [y, m, d] = String(dateStr).split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function formatDateISO(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function startOfWeekMonday(date) {
  const d = startOfDay(date);
  const weekday = d.getDay();
  const diff = weekday === 0 ? -6 : (1 - weekday);
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
  return date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

function weekLabel(weekStart) {
  return `Wk of ${weekStart.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
}

function createBuckets(rangeKey, start, end) {
  const buckets = [];

  if (rangeKey === '1W') {
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

    if (txn.type === 'income') incomeTotal += amount;
    if (txn.type === 'expense') expenseTotal += amount;

    const key = rangeKey === '1W'
      ? formatDateISO(txnDate)
      : formatDateISO(startOfWeekMonday(txnDate));

    const bucket = bucketMap.get(key);
    if (!bucket) continue;

    if (txn.type === 'income') bucket.income += amount;
    if (txn.type === 'expense') bucket.expense += amount;
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
        style: 'currency',
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
        style: 'currency',
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
      sort_by: 'date_asc',
    });

    const data = await apiGet(`/transactions?${query.toString()}`);
    const items = Array.isArray(data?.items) ? data.items : [];

    allItems.push(...items);
    total = Number.isFinite(Number(data?.total)) ? Number(data.total) : allItems.length;

    if (items.length === 0) break;
    offset += limit;
  }

  return allItems;
}

export default function FinancialChart() {
  const [selectedRange, setSelectedRange] = useState('1W');
  const [currency, setCurrency] = useState(() => getStoredCurrency());
  const [balance, setBalance] = useState(0);
  const [series, setSeries] = useState(() => {
    const { start, end } = rangeWindow('1W');
    return buildSeries('1W', start, end, []);
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [hasRangeTransactions, setHasRangeTransactions] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadBalance() {
      try {
        const summary = await apiGet('/transactions/summary');
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
      setError('');

      try {
        const transactions = await fetchAllTransactionsInRange(start, end);
        if (cancelled) return;

        const computed = buildSeries(selectedRange, start, end, transactions);
        setSeries(computed);
        setHasRangeTransactions(transactions.length > 0);
      } catch (err) {
        if (cancelled) return;

        const empty = buildSeries(selectedRange, start, end, []);
        setSeries(empty);
        setHasRangeTransactions(false);
        setError(err?.message || 'Failed to load transactions');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadRangeData();

    return () => {
      cancelled = true;
    };
  }, [selectedRange]);

  const netClass = series.totals.net < 0 ? 'metric-negative' : 'metric-positive';

  const chartData = {
    labels: series.labels,
    datasets: [
      {
        label: 'Income', data: series.income,
        borderColor: '#2ecc71', backgroundColor: 'rgba(46,204,113,0.1)',
        borderWidth: 2.5, tension: 0.3, fill: true, pointRadius: 4, pointHoverRadius: 6,
      },
      {
        label: 'Expense', data: series.expense,
        borderColor: '#e74c3c', backgroundColor: 'rgba(231,76,60,0.1)',
        borderWidth: 2.5, tension: 0.3, fill: true, pointRadius: 4, pointHoverRadius: 6,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: true, position: 'top', labels: { usePointStyle: true, padding: 20 } },
      tooltip: {
        mode: 'index', intersect: false,
        callbacks: {
          label: (ctx) => `${ctx.dataset.label}: ${formatMoney(ctx.parsed.y, currency)}`,
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { callback: (v) => formatAxisMoney(v, currency) },
        grid: { color: 'rgba(0,0,0,0.05)' },
      },
      x: { grid: { display: false } },
    },
    interaction: { mode: 'nearest', axis: 'x', intersect: false },
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
                className={`range-btn ${selectedRange === range ? 'active' : ''}`}
                type="button"
                onClick={() => setSelectedRange(range)}
              >
                {range}
              </button>
            ))}
          </div>
        </div>
        <div className="spending-amount">{formatMoney(balance, currency)}</div>
        <div className="spending-caption">Grand Total Balance</div>
        <div className="spending-details">
          <div className="detail-item">
            <span className="dot income"></span>
            Income: <strong>{formatMoney(series.totals.income, currency)}</strong>
          </div>
          <div className="detail-item">
            <span className="dot expense"></span>
            Expense: <strong>{formatMoney(series.totals.expense, currency)}</strong>
          </div>
          <div className={`detail-item ${netClass}`}>
            Net: <strong>{formatMoney(series.totals.net, currency)}</strong>
          </div>
        </div>
        {loading && <div className="chart-state">Loading data...</div>}
        {!loading && error && <div className="chart-state chart-state--error">{error}</div>}
        {!loading && !error && !hasRangeTransactions && (
          <div className="chart-state">No transactions in this range.</div>
        )}
      </div>
      <h2>Financial Overview</h2>
      <div className="chart-wrapper">
        <Line data={chartData} options={options} />
      </div>
    </div>
  );
}

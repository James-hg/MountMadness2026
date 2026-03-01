import { useState, useEffect } from 'react';
import { Doughnut, Line, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale,
  PointElement, LineElement,
  BarElement, ArcElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js';
import { apiGet, apiPatch } from '../api';
import NavBar from './NavBar';

ChartJS.register(
  CategoryScale, LinearScale,
  PointElement, LineElement,
  BarElement, ArcElement,
  Title, Tooltip, Legend, Filler,
);

const CATEGORY_COLORS = {
  'food': '#f97316',
  'housing / rent': '#2563eb',
  'transport': '#06b6d4',
  'bills / utilities': '#14b8a6',
  'shopping': '#f59e0b',
  'entertainment': '#f43f5e',
  'health': '#10b981',
  'insurance': '#0ea5e9',
  'tuition': '#ec4899',
  'other': '#94a3b8',
};

const FALLBACK_COLORS = ['#3b82f6', '#ef4444', '#22c55e', '#eab308', '#f472b6'];

function getCategoryColor(name, index) {
  return CATEGORY_COLORS[name.toLowerCase()] || FALLBACK_COLORS[index % FALLBACK_COLORS.length];
}

function toMonthKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function shiftMonth(monthKey, delta) {
  const [y, m] = monthKey.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return toMonthKey(d);
}

function formatMonthLabel(monthKey) {
  const [y, m] = monthKey.split('-');
  const d = new Date(Number(y), Number(m) - 1, 1);
  return d.toLocaleDateString('default', { month: 'long', year: 'numeric' });
}

function formatMoney(amount, currency) {
  const cur = currency || localStorage.getItem('user') && JSON.parse(localStorage.getItem('user')).base_currency || 'USD';
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: cur }).format(amount);
  } catch {
    return `$${amount.toFixed(2)}`;
  }
}

function formatAxisMoney(value, currency) {
  const cur = currency || 'USD';
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(value);
  } catch {
    return `$${Math.round(value)}`;
  }
}

export default function ReportsPage() {
  const [selectedMonth, setSelectedMonth] = useState(() => toMonthKey(new Date()));
  const [summary, setSummary] = useState(null);
  const [topCategories, setTopCategories] = useState(null);
  const [trends, setTrends] = useState(null);
  const [dailyBreakdown, setDailyBreakdown] = useState(null);
  const [budgetData, setBudgetData] = useState(null);
  const [recurringRules, setRecurringRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;

    async function loadReports() {
      setLoading(true);
      setError('');
      try {
        const monthStart = `${selectedMonth}-01`;
        const [summaryRes, categoriesRes, trendsRes, breakdownRes, budgetRes, rulesRes] = await Promise.all([
          apiGet(`/reports/summary?month=${selectedMonth}`),
          apiGet(`/reports/top-categories?month=${selectedMonth}&limit=5`),
          apiGet(`/reports/trends?months=6`),
          apiGet(`/reports/monthly-breakdown?month=${selectedMonth}`),
          apiGet(`/budget?month_start=${monthStart}`).catch(() => null),
          apiGet('/recurring-rules?is_active=true').catch(() => []),
        ]);
        if (!cancelled) {
          setSummary(summaryRes);
          setTopCategories(categoriesRes);
          setTrends(trendsRes);
          setDailyBreakdown(breakdownRes);
          setBudgetData(budgetRes);
          setRecurringRules(rulesRes);
        }
      } catch (err) {
        if (!cancelled) setError(err?.message || 'Failed to load reports');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadReports();
    return () => { cancelled = true; };
  }, [selectedMonth]);

  // -- Doughnut chart data --
  const categoryItems = topCategories?.items || [];
  const doughnutData = {
    labels: categoryItems.map(item => item.category),
    datasets: [{
      data: categoryItems.map(item => parseFloat(item.spent_amount)),
      backgroundColor: categoryItems.map((item, i) => getCategoryColor(item.category, i)),
      borderWidth: 2,
      borderColor: '#fff',
      hoverOffset: 6,
    }],
  };
  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '65%',
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => {
            const item = categoryItems[ctx.dataIndex];
            return `${item.category}: ${formatMoney(parseFloat(item.spent_amount), topCategories?.currency)} (${item.percentage}%)`;
          },
        },
      },
    },
  };

  // -- Trends line chart data --
  const trendItems = trends?.items || [];
  const trendsChartData = {
    labels: trendItems.map(item => {
      const [y, m] = item.month.split('-').map(Number);
      return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
    }),
    datasets: [
      {
        label: 'Income',
        data: trendItems.map(item => parseFloat(item.income_amount)),
        borderColor: '#2ecc71',
        backgroundColor: 'rgba(46, 204, 113, 0.1)',
        borderWidth: 2.5,
        tension: 0.3,
        fill: true,
        pointRadius: 4,
        pointHoverRadius: 6,
      },
      {
        label: 'Expenses',
        data: trendItems.map(item => parseFloat(item.expense_amount)),
        borderColor: '#e74c3c',
        backgroundColor: 'rgba(231, 76, 60, 0.1)',
        borderWidth: 2.5,
        tension: 0.3,
        fill: true,
        pointRadius: 4,
        pointHoverRadius: 6,
      },
    ],
  };
  const trendsCurrency = trends?.currency || null;
  const trendsOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: 'top',
        labels: { usePointStyle: true, padding: 20 },
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        callbacks: {
          label: (ctx) => `${ctx.dataset.label}: ${formatMoney(ctx.parsed.y, trendsCurrency)}`,
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { callback: (v) => formatAxisMoney(v, trendsCurrency) },
        grid: { color: 'rgba(0,0,0,0.05)' },
      },
      x: { grid: { display: false } },
    },
    interaction: { mode: 'nearest', axis: 'x', intersect: false },
  };

  // -- Budget vs Actual computed values --
  const hasBudget = budgetData?.total_budget_amount != null;
  const budgetCategories = budgetData?.category_budgets || [];
  const incomeCategories = budgetData?.income_budgets || [];
  const totalBudgetAmount = hasBudget ? Number(budgetData.total_budget_amount) : 0;
  const totalBudgetSpent = budgetCategories.reduce((sum, c) => sum + Number(c.spent_amount), 0);
  const totalBudgetRemaining = totalBudgetAmount - totalBudgetSpent;
  const budgetSpentRatio = totalBudgetAmount > 0 ? totalBudgetSpent / totalBudgetAmount : 0;
  const fixedExpenses = budgetCategories.filter(c => c.is_fixed);
  const flexibleExpenses = budgetCategories.filter(c => !c.is_fixed);
  const fixedIncome = incomeCategories.filter(c => c.is_fixed);
  const flexibleIncome = incomeCategories.filter(c => !c.is_fixed);

  const toggleRuleActive = async (ruleId, currentlyActive) => {
    try {
      await apiPatch(`/recurring-rules/${ruleId}`, { is_active: !currentlyActive });
      const rules = await apiGet('/recurring-rules?is_active=true').catch(() => []);
      setRecurringRules(rules);
    } catch {}
  };

  // -- Daily breakdown bar chart data --
  const breakdownItems = dailyBreakdown?.items || [];
  const barData = {
    labels: breakdownItems.map(item => String(parseInt(item.date.split('-')[2], 10))),
    datasets: [{
      label: 'Daily Spending',
      data: breakdownItems.map(item => parseFloat(item.expense_amount)),
      backgroundColor: 'rgba(13, 148, 136, 0.6)',
      hoverBackgroundColor: 'rgba(13, 148, 136, 0.85)',
      borderRadius: 4,
      borderSkipped: false,
    }],
  };
  const breakdownCurrency = dailyBreakdown?.currency || null;
  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => {
            const idx = items[0]?.dataIndex;
            if (idx != null && breakdownItems[idx]) {
              const d = new Date(breakdownItems[idx].date + 'T00:00:00');
              return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
            }
            return '';
          },
          label: (ctx) => `Spent: ${formatMoney(ctx.parsed.y, breakdownCurrency)}`,
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: { callback: (v) => formatAxisMoney(v, breakdownCurrency) },
        grid: { color: 'rgba(0,0,0,0.05)' },
      },
      x: {
        grid: { display: false },
        ticks: { font: { size: 10 } },
      },
    },
  };

  return (
    <>
      <NavBar />
      <div className="page-container">
        <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <h1 className="page-title">Reports &amp; Insights</h1>
          <div className="reports-month-nav">
            <button className="month-nav-btn" onClick={() => setSelectedMonth(prev => shiftMonth(prev, -1))} aria-label="Previous month">&#8249;</button>
            <span className="month-nav-label">{formatMonthLabel(selectedMonth)}</span>
            <button className="month-nav-btn" onClick={() => setSelectedMonth(prev => shiftMonth(prev, 1))} aria-label="Next month">&#8250;</button>
          </div>
        </div>

        {error && <div className="reports-error">{error}</div>}

        {loading ? (
          <div className="reports-loading">Loading reports...</div>
        ) : (
          <>
            {/* Summary Cards */}
            <div className="summary-cards">
              <div className="summary-card">
                <span className="summary-label">Current Balance</span>
                <span className="summary-value">
                  {summary ? formatMoney(parseFloat(summary.balance_amount), summary.currency) : '\u2014'}
                </span>
                <span className="summary-sub">Total income &minus; expenses</span>
              </div>
              <div className="summary-card">
                <span className="summary-label">Monthly Spend</span>
                <span className="summary-value">
                  {summary ? formatMoney(parseFloat(summary.monthly_spend_amount), summary.currency) : '\u2014'}
                </span>
                <span className="summary-sub">This month's total</span>
              </div>
              <div className="summary-card">
                <span className="summary-label">Burn Rate</span>
                <span className="summary-value">
                  {summary ? formatMoney(parseFloat(summary.burn_rate_amount_per_month), summary.currency) : '\u2014'}
                </span>
                <span className="summary-sub">Avg monthly spending</span>
              </div>
              <div className="summary-card accent">
                <span className="summary-label">Runway</span>
                <span className="summary-value">
                  {summary ? (summary.runway_days != null ? `${summary.runway_days} days` : 'N/A') : '\u2014'}
                </span>
                <span className="summary-sub">Days your money lasts</span>
              </div>
            </div>

            {/* Budget Overview */}
            {hasBudget && (
              <div className="reports-budget-overview">
                <h2 className="card-title" style={{ marginBottom: 16 }}>Budget Overview</h2>
                <div className="summary-cards">
                  <div className="summary-card">
                    <span className="summary-label">Total Budget</span>
                    <span className="summary-value">{formatMoney(totalBudgetAmount, budgetData?.currency)}</span>
                  </div>
                  <div className="summary-card">
                    <span className="summary-label">Total Spent</span>
                    <span className="summary-value" style={{ color: '#e74c3c' }}>
                      {formatMoney(totalBudgetSpent, budgetData?.currency)}
                    </span>
                  </div>
                  <div className="summary-card">
                    <span className="summary-label">Remaining</span>
                    <span className="summary-value" style={{ color: totalBudgetRemaining >= 0 ? '#2ecc71' : '#e74c3c' }}>
                      {totalBudgetRemaining < 0 ? '-' : ''}{formatMoney(Math.abs(totalBudgetRemaining), budgetData?.currency)}
                    </span>
                  </div>
                </div>

                {/* Health bar */}
                <div className="reports-health-bar-container">
                  <div className="reports-health-bar">
                    <div
                      className={`reports-health-fill${budgetSpentRatio >= 1 ? ' danger' : budgetSpentRatio >= 0.8 ? ' warning' : ''}`}
                      style={{ width: `${Math.min(budgetSpentRatio * 100, 100)}%` }}
                    />
                  </div>
                  <div className="reports-health-labels">
                    <span>{formatMoney(totalBudgetSpent, budgetData?.currency)} spent</span>
                    <span>{formatMoney(totalBudgetAmount, budgetData?.currency)} budget</span>
                  </div>
                </div>

                {/* Per-category budget vs actual */}
                {(fixedExpenses.length > 0 || flexibleExpenses.length > 0) && (
                  <div className="card" style={{ marginTop: 16 }}>
                    <h3 className="card-title">Expense Categories</h3>
                    {fixedExpenses.length > 0 && (
                      <>
                        <h4 className="reports-budget-group-title">Fixed Expenses</h4>
                        {fixedExpenses.map(cat => {
                          const limit = Number(cat.limit_amount);
                          const spent = Number(cat.spent_amount);
                          const remaining = limit - spent;
                          const pct = limit > 0 ? Math.round((spent / limit) * 100) : (spent > 0 ? 100 : 0);
                          const barWidth = Math.min(pct, 100);
                          let fillClass = pct >= 100 ? ' danger' : pct >= 80 ? ' warning' : '';
                          return (
                            <div key={cat.category_id} className="reports-budget-item">
                              <div className="reports-budget-item-header">
                                <span className="reports-budget-category">
                                  <span className="reports-budget-dot" style={{ backgroundColor: getCategoryColor(cat.category_name, 0) }} />
                                  {cat.category_name}
                                </span>
                                <div className="reports-budget-amounts">
                                  <span style={{ color: '#e74c3c' }}>{formatMoney(spent, budgetData?.currency)}</span>
                                  <span style={{ color: '#888' }}> / {formatMoney(limit, budgetData?.currency)}</span>
                                  <span style={{ color: remaining >= 0 ? '#2ecc71' : '#e74c3c', marginLeft: 8 }}>
                                    {remaining >= 0 ? `${formatMoney(remaining, budgetData?.currency)} left` : `${formatMoney(Math.abs(remaining), budgetData?.currency)} over`}
                                  </span>
                                </div>
                              </div>
                              <div className="reports-budget-bar-row">
                                <div className="progress-bar">
                                  <div className={`progress-fill${fillClass}`} style={{ width: `${barWidth}%`, ...(fillClass === '' ? { backgroundColor: getCategoryColor(cat.category_name, 0) } : {}) }} />
                                </div>
                                <span className="reports-budget-pct">{pct}% used</span>
                              </div>
                            </div>
                          );
                        })}
                      </>
                    )}
                    {flexibleExpenses.length > 0 && (
                      <>
                        <h4 className="reports-budget-group-title">{fixedExpenses.length > 0 ? 'Flexible Expenses' : ''}</h4>
                        {flexibleExpenses.map(cat => {
                          const limit = Number(cat.limit_amount);
                          const spent = Number(cat.spent_amount);
                          const remaining = limit - spent;
                          const pct = limit > 0 ? Math.round((spent / limit) * 100) : (spent > 0 ? 100 : 0);
                          const barWidth = Math.min(pct, 100);
                          let fillClass = pct >= 100 ? ' danger' : pct >= 80 ? ' warning' : '';
                          return (
                            <div key={cat.category_id} className="reports-budget-item">
                              <div className="reports-budget-item-header">
                                <span className="reports-budget-category">
                                  <span className="reports-budget-dot" style={{ backgroundColor: getCategoryColor(cat.category_name, 0) }} />
                                  {cat.category_name}
                                </span>
                                <div className="reports-budget-amounts">
                                  <span style={{ color: '#e74c3c' }}>{formatMoney(spent, budgetData?.currency)}</span>
                                  <span style={{ color: '#888' }}> / {formatMoney(limit, budgetData?.currency)}</span>
                                  <span style={{ color: remaining >= 0 ? '#2ecc71' : '#e74c3c', marginLeft: 8 }}>
                                    {remaining >= 0 ? `${formatMoney(remaining, budgetData?.currency)} left` : `${formatMoney(Math.abs(remaining), budgetData?.currency)} over`}
                                  </span>
                                </div>
                              </div>
                              <div className="reports-budget-bar-row">
                                <div className="progress-bar">
                                  <div className={`progress-fill${fillClass}`} style={{ width: `${barWidth}%`, ...(fillClass === '' ? { backgroundColor: getCategoryColor(cat.category_name, 0) } : {}) }} />
                                </div>
                                <span className="reports-budget-pct">{pct}% used</span>
                              </div>
                            </div>
                          );
                        })}
                      </>
                    )}
                  </div>
                )}

                {/* Income tracking */}
                {(fixedIncome.length > 0 || flexibleIncome.length > 0) && (
                  <div className="card" style={{ marginTop: 16 }}>
                    <h3 className="card-title">Income Tracking</h3>
                    {[...fixedIncome, ...flexibleIncome].map(cat => {
                      const expected = Number(cat.limit_amount);
                      const received = Number(cat.spent_amount);
                      const pending = expected - received;
                      const pct = expected > 0 ? Math.round((received / expected) * 100) : (received > 0 ? 100 : 0);
                      const barWidth = Math.min(pct, 100);
                      return (
                        <div key={cat.category_id} className="reports-budget-item">
                          <div className="reports-budget-item-header">
                            <span className="reports-budget-category">
                              <span className="reports-budget-dot" style={{ backgroundColor: '#2ecc71' }} />
                              {cat.category_name}
                            </span>
                            <div className="reports-budget-amounts">
                              <span style={{ color: '#2ecc71' }}>{formatMoney(received, budgetData?.currency)}</span>
                              <span style={{ color: '#888' }}> / {formatMoney(expected, budgetData?.currency)}</span>
                              <span style={{ color: pending > 0 ? '#888' : '#2ecc71', marginLeft: 8 }}>
                                {pending > 0 ? `${formatMoney(pending, budgetData?.currency)} pending` : 'Received'}
                              </span>
                            </div>
                          </div>
                          <div className="reports-budget-bar-row">
                            <div className="progress-bar">
                              <div className="progress-fill" style={{ width: `${barWidth}%`, backgroundColor: '#2ecc71' }} />
                            </div>
                            <span className="reports-budget-pct">{pct}% received</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {/* Recurring Transactions */}
            {recurringRules.length > 0 && (
              <div className="card">
                <h2 className="card-title">Recurring Transactions</h2>
                <div className="reports-recurring-list">
                  {recurringRules.map((rule) => (
                    <div key={rule.id} className="reports-recurring-item">
                      <div className="reports-recurring-header">
                        <span className="reports-budget-category">
                          <span className="reports-budget-dot" style={{ backgroundColor: getCategoryColor(rule.category_name, 0) }} />
                          {rule.merchant || rule.category_name}
                          <span className="reports-recurring-badge">{rule.frequency}</span>
                        </span>
                        <span className="reports-recurring-amount">{formatMoney(Number(rule.amount), budgetData?.currency || summary?.currency)}</span>
                      </div>
                      <div className="reports-recurring-details">
                        <span>Next: {rule.next_due_date}</span>
                        <span>{rule.category_name}</span>
                        <button className="reports-recurring-btn" onClick={() => toggleRuleActive(rule.id, rule.is_active)}>
                          {rule.is_active ? 'Pause' : 'Resume'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Top Spending Categories */}
            <div className="card">
              <h2 className="card-title">Top Spending Categories</h2>
              {categoryItems.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon">📊</div>
                  <h3>No data yet</h3>
                  <p>Add transactions to see your top spending categories here.</p>
                </div>
              ) : (
                <div className="reports-categories-layout">
                  <div className="reports-doughnut-container">
                    <Doughnut data={doughnutData} options={doughnutOptions} />
                  </div>
                  <div className="reports-category-legend">
                    {categoryItems.map((item, i) => (
                      <div className="reports-legend-item" key={item.category}>
                        <span className="reports-legend-dot" style={{ backgroundColor: getCategoryColor(item.category, i) }} />
                        <span className="reports-legend-name">{item.category}</span>
                        <span className="reports-legend-amount">{formatMoney(parseFloat(item.spent_amount), topCategories?.currency)}</span>
                        <span className="reports-legend-pct">{item.percentage}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Charts Grid */}
            <div className="reports-charts-grid">
              {/* Income vs Expense Trends */}
              <div className="card">
                <h2 className="card-title">Income vs Expense Trends</h2>
                {trendItems.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-state-icon">📈</div>
                    <h3>No trend data yet</h3>
                    <p>Spending trends over time will appear here once you have transaction data.</p>
                  </div>
                ) : (
                  <div className="reports-chart-container">
                    <Line data={trendsChartData} options={trendsOptions} />
                  </div>
                )}
              </div>

              {/* Daily Spending Breakdown */}
              <div className="card">
                <h2 className="card-title">Daily Spending</h2>
                {breakdownItems.length === 0 || breakdownItems.every(d => parseFloat(d.expense_amount) === 0) ? (
                  <div className="empty-state">
                    <div className="empty-state-icon">📅</div>
                    <h3>No spending data</h3>
                    <p>Daily spending for this month will appear here.</p>
                  </div>
                ) : (
                  <div className="reports-chart-container">
                    <Bar data={barData} options={barOptions} />
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}

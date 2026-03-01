import { useState, useEffect, useCallback } from 'react';
import NavBar from './NavBar';
import { apiGet } from '../api';

function formatDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}


function getWeekStart(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const day = d.getDay();
  const diff = d.getDate() - day;
  const sun = new Date(d.getFullYear(), d.getMonth(), diff);
  return formatDate(sun);
}

function groupTransactions(txns, aggregation) {
  if (aggregation === 'default') return [{ label: null, items: txns }];

  const groups = {};
  const order = [];

  for (const t of txns) {
    let key;
    let label;
    const d = new Date(t.occurred_on + 'T00:00:00');

    switch (aggregation) {
      case 'daily':
        key = t.occurred_on;
        label = d.toLocaleDateString('default', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
        break;
      case 'weekly': {
        key = getWeekStart(t.occurred_on);
        const ws = new Date(key + 'T00:00:00');
        label = `Week of ${ws.toLocaleDateString('default', { month: 'short', day: 'numeric' })}`;
        break;
      }
      case 'monthly':
        key = t.occurred_on.slice(0, 7);
        label = d.toLocaleDateString('default', { month: 'long', year: 'numeric' });
        break;
      case 'yearly':
        key = t.occurred_on.slice(0, 4);
        label = key;
        break;
      default:
        key = 'all';
        label = null;
    }

    if (!groups[key]) {
      groups[key] = { label, items: [] };
      order.push(key);
    }
    groups[key].items.push(t);
  }

  return order.map((k) => groups[k]);
}

function compareBy(key, a, b) {
  switch (key) {
    case 'date_asc': return a.occurred_on.localeCompare(b.occurred_on);
    case 'date_desc': return b.occurred_on.localeCompare(a.occurred_on);
    case 'amount_desc': return Number(b.amount) - Number(a.amount);
    case 'amount_asc': return Number(a.amount) - Number(b.amount);
    case 'merchant_asc': return (a.merchant || '').localeCompare(b.merchant || '');
    case 'merchant_desc': return (b.merchant || '').localeCompare(a.merchant || '');
    default: return 0;
  }
}

function sortTransactions(txns, criteria) {
  const keys = criteria.length > 0 ? criteria : ['date_desc'];
  return [...txns].sort((a, b) => {
    for (const key of keys) {
      const cmp = compareBy(key, a, b);
      if (cmp !== 0) return cmp;
    }
    return 0;
  });
}

// ── Calendar helpers ──

function getCalendarDays(year, month) {
  const firstOfMonth = new Date(year, month, 1);
  const startDay = firstOfMonth.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const daysInPrevMonth = new Date(year, month, 0).getDate();
  const days = [];
  for (let i = startDay - 1; i >= 0; i--) {
    days.push({ date: new Date(year, month - 1, daysInPrevMonth - i), isCurrentMonth: false });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    days.push({ date: new Date(year, month, d), isCurrentMonth: true });
  }
  const remaining = 42 - days.length;
  for (let d = 1; d <= remaining; d++) {
    days.push({ date: new Date(year, month + 1, d), isCurrentMonth: false });
  }
  return days;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

export default function TransactionsPage() {
  const [showForm, setShowForm] = useState(false);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [amountMin, setAmountMin] = useState('');
  const [amountMax, setAmountMax] = useState('');
  const [sortBy, setSortBy] = useState(['date_desc']);

  // View options
  const [viewMode, setViewMode] = useState('list');
  const [aggregation, setAggregation] = useState('default');

  // Calendar state
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerYear, setPickerYear] = useState(new Date().getFullYear());
  const [pickerMode, setPickerMode] = useState('month');
  const [yearRangeStart, setYearRangeStart] = useState(Math.floor(new Date().getFullYear() / 12) * 12);

  const calYear = currentDate.getFullYear();
  const calMonth = currentDate.getMonth();

  // ── Fetch transactions ──
  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    try {
      let params = [];
      if (viewMode === 'calendar') {
        const firstDay = `${calYear}-${String(calMonth + 1).padStart(2, '0')}-01`;
        const lastDay = formatDate(new Date(calYear, calMonth + 1, 0));
        params.push(`date_from=${firstDay}`, `date_to=${lastDay}`);
      } else {
        if (dateFrom) params.push(`date_from=${dateFrom}`);
        if (dateTo) params.push(`date_to=${dateTo}`);
      }
      if (filterType) params.push(`type=${filterType}`);
      if (searchQuery.trim()) params.push(`q=${encodeURIComponent(searchQuery.trim())}`);

      let allItems = [];
      let offset = 0;
      const limit = 100;
      let hasMore = true;
      while (hasMore) {
        const qstr = [...params, `limit=${limit}`, `offset=${offset}`].join('&');
        const data = await apiGet(`/transactions?${qstr}`);
        allItems = allItems.concat(data.items);
        offset += limit;
        hasMore = allItems.length < data.total;
      }

      // client-side amount filter
      const minVal = amountMin !== '' ? Number(amountMin) : null;
      const maxVal = amountMax !== '' ? Number(amountMax) : null;
      if (minVal !== null || maxVal !== null) {
        allItems = allItems.filter((t) => {
          const amt = Number(t.amount);
          if (minVal !== null && amt < minVal) return false;
          if (maxVal !== null && amt > maxVal) return false;
          return true;
        });
      }

      setTransactions(allItems);
    } catch {
      setTransactions([]);
    } finally {
      setLoading(false);
    }
  }, [viewMode, calYear, calMonth, dateFrom, dateTo, filterType, searchQuery, amountMin, amountMax]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  // ── List helpers ──
  const sorted = sortTransactions(transactions, sortBy);
  const groups = groupTransactions(sorted, aggregation);

  // ── Calendar helpers ──
  function transactionsForDate(dateObj) {
    const dateStr = formatDate(dateObj);
    return transactions.filter((t) => t.occurred_on === dateStr);
  }

  const goToPrevMonth = () => { setCurrentDate(new Date(calYear, calMonth - 1, 1)); setSelectedDate(null); };
  const goToNextMonth = () => { setCurrentDate(new Date(calYear, calMonth + 1, 1)); setSelectedDate(null); };
  const goToToday = () => { setCurrentDate(new Date()); setSelectedDate(new Date()); };

  const openPicker = () => { setPickerYear(calYear); setPickerMode('month'); setPickerOpen(true); };
  const selectMonth = (m) => { setCurrentDate(new Date(pickerYear, m, 1)); setSelectedDate(null); setPickerOpen(false); };
  const openYearPicker = () => { setYearRangeStart(Math.floor(pickerYear / 12) * 12); setPickerMode('year'); };
  const selectYear = (y) => { setPickerYear(y); setPickerMode('month'); };

  const calendarDays = getCalendarDays(calYear, calMonth);
  const todayStr = new Date().toDateString();
  const selectedTxns = selectedDate ? transactionsForDate(selectedDate) : [];

  return (
    <>
      <NavBar />
      <div className="page-container page-container--wide">
        <div className="page-header">
          <h1 className="page-title">Transactions</h1>
          <button className="primary-btn" onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancel' : '+ Add Transaction'}
          </button>
        </div>

        {showForm && (
          <div className="card">
            <h2 className="card-title">New Transaction</h2>
            <form className="page-form" onSubmit={(e) => e.preventDefault()}>
              <div className="form-row">
                <div className="form-group">
                  <label>Type</label>
                  <select className="form-select" disabled>
                    <option>Expense</option>
                    <option>Income</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Amount</label>
                  <input type="number" placeholder="0.00" disabled />
                </div>
                <div className="form-group">
                  <label>Date</label>
                  <input type="date" disabled />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Category</label>
                  <select className="form-select" disabled>
                    <option value="">Select category...</option>
                    <option>Food</option>
                    <option>Housing/Rent</option>
                    <option>Transport</option>
                    <option>Insurance</option>
                    <option>Tuition</option>
                    <option>Bills/Utilities</option>
                    <option>Shopping</option>
                    <option>Entertainment</option>
                    <option>Health</option>
                    <option>Other</option>
                  </select>
                </div>
                <div className="form-group" style={{ flex: 2 }}>
                  <label>Note</label>
                  <input type="text" placeholder="Optional note..." disabled />
                </div>
              </div>
              <button className="primary-btn" disabled>Save Transaction</button>
            </form>
          </div>
        )}

        <div className="txn-layout">
          {/* ── Column 1: Filter + Sort ── */}
          <aside className="txn-sidebar-left">
            <div className="card">
              <h3 className="card-title">Filter</h3>
              <div className="txn-filter-group">
                <label>Search</label>
                <input
                  type="text"
                  className="txn-search-input"
                  placeholder="Merchant or note..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>

              <div className="txn-filter-group">
                <label>Type</label>
                <div className="txn-type-btns">
                  {[{ value: '', label: 'All' }, { value: 'expense', label: 'Expense' }, { value: 'income', label: 'Income' }].map((opt) => (
                    <button
                      key={opt.value}
                      className={`txn-type-btn${filterType === opt.value ? ' active' : ''}`}
                      onClick={() => setFilterType(opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="txn-filter-group">
                <label>From</label>
                <input
                  type="date"
                  className="txn-search-input"
                  value={dateFrom}
                  onChange={(e) => setDateFrom(e.target.value)}
                />
              </div>
              <div className="txn-filter-group">
                <label>To</label>
                <input
                  type="date"
                  className="txn-search-input"
                  value={dateTo}
                  onChange={(e) => setDateTo(e.target.value)}
                />
              </div>

              <div className="txn-filter-group">
                <label>Price Range</label>
                <div className="txn-range-row">
                  <input
                    type="number"
                    className="txn-search-input"
                    placeholder="Min"
                    min="0"
                    value={amountMin}
                    onChange={(e) => setAmountMin(e.target.value)}
                  />
                  <span className="txn-range-sep">–</span>
                  <input
                    type="number"
                    className="txn-search-input"
                    placeholder="Max"
                    min="0"
                    value={amountMax}
                    onChange={(e) => setAmountMax(e.target.value)}
                  />
                </div>
              </div>
            </div>

            <div className="card">
              <h3 className="card-title">Sort</h3>
              {[
                { label: 'Date', options: [{ value: 'date_desc', label: 'Newest' }, { value: 'date_asc', label: 'Oldest' }] },
                { label: 'Amount', options: [{ value: 'amount_desc', label: 'High → Low' }, { value: 'amount_asc', label: 'Low → High' }] },
                { label: 'Merchant', options: [{ value: 'merchant_asc', label: 'A → Z' }, { value: 'merchant_desc', label: 'Z → A' }] },
              ].map((group) => (
                <div key={group.label} className="txn-filter-group">
                  <label>{group.label}</label>
                  <div className="txn-type-btns">
                    {group.options.map((opt) => (
                      <button
                        key={opt.value}
                        className={`txn-type-btn${sortBy.includes(opt.value) ? ' active' : ''}`}
                        onClick={() => {
                          const groupValues = group.options.map((o) => o.value);
                          setSortBy((prev) =>
                            prev.includes(opt.value)
                              ? prev.filter((v) => v !== opt.value)
                              : [...prev.filter((v) => !groupValues.includes(v)), opt.value]
                          );
                        }}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </aside>

          {/* ── Column 2: Main Content ── */}
          <main className="txn-main">
            {viewMode === 'list' ? (
              <div className="card">
                {loading && <p style={{ textAlign: 'center', padding: 12, color: '#888' }}>Loading...</p>}
                {transactions.length === 0 && !loading ? (
                  <div className="empty-state">
                    <div className="empty-state-icon">📋</div>
                    <h3>No transactions yet</h3>
                    <p>Add your first transaction to start tracking your spending.</p>
                  </div>
                ) : (
                  <div className="txn-list">
                    {groups.map((group, gi) => (
                      <div key={gi}>
                        {group.label && <div className="txn-date-header">{group.label}</div>}
                        {group.items.map((t) => (
                          <div key={t.id} className="txn-item">
                            <div className="txn-item-left">
                              <span className={`txn-item-type ${t.type}`}>
                                {t.type === 'income' ? '+' : '-'}
                              </span>
                              <div className="txn-item-details">
                                <span className="txn-item-merchant">
                                  {t.merchant || t.note || 'Transaction'}
                                </span>
                                <span className="txn-item-date">{t.occurred_on}</span>
                              </div>
                            </div>
                            <span className={`txn-item-amount ${t.type}`}>
                              {t.type === 'income' ? '+' : '-'}${Number(t.amount).toFixed(2)}
                            </span>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <>
                <div className="card">
                  <div className="calendar-nav">
                    <button className="icon-btn" onClick={goToPrevMonth}>&larr;</button>
                    <div className="calendar-title-wrapper">
                      <button className="calendar-month-title" onClick={openPicker}>
                        {currentDate.toLocaleString('default', { month: 'long', year: 'numeric' })}
                      </button>
                      {pickerOpen && (
                        <div className="calendar-picker">
                          {pickerMode === 'month' ? (
                            <>
                              <div className="calendar-picker-header">
                                <button className="icon-btn" onClick={() => setPickerYear(pickerYear - 1)}>&larr;</button>
                                <button className="calendar-picker-year" onClick={openYearPicker}>{pickerYear}</button>
                                <button className="icon-btn" onClick={() => setPickerYear(pickerYear + 1)}>&rarr;</button>
                              </div>
                              <div className="calendar-picker-grid">
                                {MONTHS.map((m, i) => (
                                  <button
                                    key={m}
                                    className={`calendar-picker-month${i === calMonth && pickerYear === calYear ? ' active' : ''}`}
                                    onClick={() => selectMonth(i)}
                                  >
                                    {m}
                                  </button>
                                ))}
                              </div>
                            </>
                          ) : (
                            <>
                              <div className="calendar-picker-header">
                                <button className="icon-btn" onClick={() => setYearRangeStart(yearRangeStart - 12)}>&larr;</button>
                                <span className="calendar-picker-range">{yearRangeStart} – {yearRangeStart + 11}</span>
                                <button className="icon-btn" onClick={() => setYearRangeStart(yearRangeStart + 12)}>&rarr;</button>
                              </div>
                              <div className="calendar-picker-grid">
                                {Array.from({ length: 12 }, (_, i) => yearRangeStart + i).map((y) => (
                                  <button
                                    key={y}
                                    className={`calendar-picker-month${y === calYear ? ' active' : ''}`}
                                    onClick={() => selectYear(y)}
                                  >
                                    {y}
                                  </button>
                                ))}
                              </div>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                    <button className="icon-btn" onClick={goToNextMonth}>&rarr;</button>
                    <button className="secondary-btn calendar-today-btn" onClick={goToToday}>Today</button>
                  </div>

                  <div className="calendar-grid">
                    {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
                      <div key={day} className="calendar-weekday">{day}</div>
                    ))}
                    {calendarDays.map((dayObj, idx) => {
                      const dayTxns = transactionsForDate(dayObj.date);
                      const isSelected = selectedDate && dayObj.date.toDateString() === selectedDate.toDateString();
                      const isToday = dayObj.date.toDateString() === todayStr;
                      return (
                        <div
                          key={idx}
                          className={[
                            'calendar-day',
                            !dayObj.isCurrentMonth && 'calendar-day--outside',
                            isSelected && 'calendar-day--selected',
                            isToday && 'calendar-day--today',
                          ].filter(Boolean).join(' ')}
                          onClick={() => setSelectedDate(dayObj.date)}
                        >
                          <span className="calendar-day-number">{dayObj.date.getDate()}</span>
                          {dayTxns.length > 0 && (
                            <div className="calendar-day-indicators">
                              {dayTxns.length <= 3
                                ? dayTxns.map((t) => (
                                    <span key={t.id} className={`calendar-dot ${t.type === 'income' ? 'income' : 'outcome'}`} />
                                  ))
                                : <span className="calendar-day-count">{dayTxns.length}</span>
                              }
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {loading && <p style={{ textAlign: 'center', padding: 12, color: '#888' }}>Loading...</p>}
                </div>

                {selectedDate && (
                  <div className="card">
                    <h2 className="card-title">
                      {selectedDate.toLocaleDateString('default', {
                        weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
                      })}
                    </h2>
                    {selectedTxns.length === 0 ? (
                      <div className="empty-state">
                        <div className="empty-state-icon">📅</div>
                        <h3>No transactions</h3>
                        <p>No transactions recorded for this date.</p>
                      </div>
                    ) : (
                      <div className="calendar-txn-list">
                        {selectedTxns.map((t) => (
                          <div key={t.id} className="calendar-txn-item">
                            <div className="calendar-txn-info">
                              <span className={`calendar-txn-type ${t.type}`}>
                                {t.type === 'income' ? '+' : '-'}
                              </span>
                              <span className="calendar-txn-merchant">
                                {t.merchant || t.note || 'Transaction'}
                              </span>
                            </div>
                            <span className={`calendar-txn-amount ${t.type}`}>
                              {t.type === 'income' ? '+' : '-'}${Number(t.amount).toFixed(2)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </main>

          {/* ── Column 3: View Options ── */}
          <aside className="txn-sidebar-right card">
            <div className="txn-filter-group">
              <label>View</label>
              <div className="txn-toggle">
                <button
                  className={`txn-toggle-btn${viewMode === 'list' ? ' active' : ''}`}
                  onClick={() => setViewMode('list')}
                >
                  List
                </button>
                <button
                  className={`txn-toggle-btn${viewMode === 'calendar' ? ' active' : ''}`}
                  onClick={() => setViewMode('calendar')}
                >
                  Calendar
                </button>
              </div>
            </div>

            {viewMode === 'list' && (
              <div className="txn-filter-group">
                <label>Group By</label>
                <div className="txn-radio-group">
                  {[
                    { value: 'default', label: 'Default' },
                    { value: 'daily', label: 'Daily' },
                    { value: 'weekly', label: 'Weekly' },
                    { value: 'monthly', label: 'Monthly' },
                    { value: 'yearly', label: 'Yearly' },
                  ].map((opt) => (
                    <button
                      key={opt.value}
                      className={`txn-radio-option${aggregation === opt.value ? ' active' : ''}`}
                      onClick={() => setAggregation(opt.value)}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>
    </>
  );
}

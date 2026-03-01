import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import NavBar from './NavBar';
import { apiGet, apiPost, apiPatch, API_BASE } from '../api';

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

const SORT_LABELS = {
  date_desc: 'Newest',
  date_asc: 'Oldest',
  amount_desc: 'High → Low',
  amount_asc: 'Low → High',
  merchant_asc: 'A → Z',
  merchant_desc: 'Z → A',
  category_asc: 'A → Z',
  category_desc: 'Z → A',
};

function formatRangeDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('default', { month: 'short', day: 'numeric', year: 'numeric' });
}

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

  // New Transaction form
  const [formType, setFormType] = useState('expense');
  const [formAmount, setFormAmount] = useState('');
  const [formDate, setFormDate] = useState(formatDate(new Date()));
  const [formCategoryId, setFormCategoryId] = useState('');
  const [formMerchant, setFormMerchant] = useState('');
  const [formNote, setFormNote] = useState('');
  const [formRecurring, setFormRecurring] = useState(false);
  const [formFrequency, setFormFrequency] = useState('monthly');
  const [formError, setFormError] = useState('');
  const [formSaving, setFormSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef(null);
  const [categories, setCategories] = useState([]);

  // Inline edit state
  const [editingId, setEditingId] = useState(null);
  const [editType, setEditType] = useState('expense');
  const [editAmount, setEditAmount] = useState('');
  const [editDate, setEditDate] = useState('');
  const [editCategoryId, setEditCategoryId] = useState('');
  const [editMerchant, setEditMerchant] = useState('');
  const [editNote, setEditNote] = useState('');
  const [editError, setEditError] = useState('');
  const [editSaving, setEditSaving] = useState(false);

  // View options
  const [viewMode, setViewMode] = useState('list');
  const [aggregation, setAggregation] = useState('default');
  const [cashFlowOpen, setCashFlowOpen] = useState(true);
  const [categorySummaryOpen, setCategorySummaryOpen] = useState(true);

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
      if (amountMin !== '') params.push(`amount_min=${amountMin}`);
      if (amountMax !== '') params.push(`amount_max=${amountMax}`);
      if (sortBy.length > 0) params.push(`sort_by=${sortBy.join(',')}`);

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

      setTransactions(allItems);
    } catch {
      setTransactions([]);
    } finally {
      setLoading(false);
    }
  }, [viewMode, calYear, calMonth, dateFrom, dateTo, filterType, searchQuery, amountMin, amountMax, sortBy]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  // ── Fetch categories ──
  useEffect(() => {
    apiGet('/categories').then(setCategories).catch(() => setCategories([]));
  }, []);

  const filteredCategories = categories.filter((c) => c.kind === formType);
  const editFilteredCategories = categories.filter((c) => c.kind === editType);

  const resetForm = () => {
    setFormType('expense');
    setFormAmount('');
    setFormDate(formatDate(new Date()));
    setFormCategoryId('');
    setFormMerchant('');
    setFormNote('');
    setFormRecurring(false);
    setFormFrequency('monthly');
    setFormError('');
  };

  const handleFileSelect = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    setFormError('');

    const token = localStorage.getItem('access_token');
    if (!token) {
      setFormError("Authentication error: No token found.");
      setUploading(false);
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${API_BASE}/transactions/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to upload and process receipt.');
      }

      const data = await response.json();

      // Autofill the form
      setFormType('expense');
      setFormAmount(data.amount || '0.00');
      setFormDate(data.occurred_on || formatDate(new Date()));
      setFormCategoryId(data.category_id || '');
      setFormMerchant(data.merchant || '');
      setFormNote(data.note || 'Imported from receipt');
    } catch (err) {
      setFormError(err.message);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleSubmitTransaction = async (e) => {
    e.preventDefault();
    setFormError('');

    if (!formAmount || Number(formAmount) <= 0) { setFormError('You can only put a positive value for amount'); return; }
    if (!formDate) { setFormError('Date is required'); return; }
    if (!formCategoryId) { setFormError('Please select a category'); return; }

    setFormSaving(true);
    try {
      const body = {
        type: formType,
        amount: formAmount,
        occurred_on: formDate,
        category_id: formCategoryId,
        merchant: formMerchant || null,
        note: formNote || null,
      };
      if (formRecurring) {
        body.make_recurring = true;
        body.recurring_frequency = formFrequency;
      }
      await apiPost('/transactions', body);
      resetForm();
      setShowForm(false);
      fetchTransactions();
    } catch (err) {
      setFormError(err.message || 'Failed to create transaction');
    } finally {
      setFormSaving(false);
    }
  };

  const startEditing = (t) => {
    setEditingId(t.id);
    setEditType(t.type);
    setEditAmount(Math.abs(Number(t.amount)).toString());
    setEditDate(t.occurred_on);
    setEditCategoryId(t.category_id);
    setEditMerchant(t.merchant || '');
    setEditNote(t.note || '');
    setEditError('');
  };

  const cancelEditing = () => {
    setEditingId(null);
    setEditError('');
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    setEditError('');

    if (!editAmount || Number(editAmount) <= 0) { setEditError('You can only put a positive value for amount'); return; }
    if (!editDate) { setEditError('Date is required'); return; }
    if (!editCategoryId) { setEditError('Please select a category'); return; }

    setEditSaving(true);
    try {
      await apiPatch(`/transactions/${editingId}`, {
        type: editType,
        amount: editAmount,
        occurred_on: editDate,
        category_id: editCategoryId,
        merchant: editMerchant || null,
        note: editNote || null,
      });
      setEditingId(null);
      fetchTransactions();
    } catch (err) {
      setEditError(err.message || 'Failed to update transaction');
    } finally {
      setEditSaving(false);
    }
  };

  // ── List helpers ──
  const groups = groupTransactions(transactions, aggregation);

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

  // ── Category summary for sidebar ──
  const categorySummary = useMemo(() => {
    const map = {};
    for (const t of transactions) {
      const cat = categories.find(c => c.id === t.category_id);
      const name = cat ? cat.name : 'Uncategorized';
      const amt = Math.abs(Number(t.amount));
      if (!map[name]) map[name] = { income: 0, expense: 0 };
      if (t.type === 'income') map[name].income += amt;
      else map[name].expense += amt;
    }
    return Object.entries(map).sort((a, b) => (b[1].expense + b[1].income) - (a[1].expense + a[1].income));
  }, [transactions, categories]);

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
            {formError && <div style={{ color: '#e74c3c', background: '#fdecea', border: '1px solid #e74c3c', borderRadius: 8, padding: '8px 12px', marginBottom: 12 }}>{formError}</div>}
            <form className="page-form" onSubmit={handleSubmitTransaction}>
              <div className="form-row">
                <div className="form-group">
                  <label>Type</label>
                  <select className="form-select" value={formType} onChange={(e) => { setFormType(e.target.value); setFormCategoryId(''); }}>
                    <option value="expense">Expense</option>
                    <option value="income">Income</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Amount</label>
                  <input type="number" step="0.01" min="0.01" placeholder="0.00" value={formAmount} onChange={(e) => { const v = e.target.value; setFormAmount(v !== '' && Number(v) < 0 ? '' : v); }} />
                </div>
                <div className="form-group">
                  <label>Date</label>
                  <input type="date" value={formDate} onChange={(e) => setFormDate(e.target.value)} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Category</label>
                  <select className="form-select" value={formCategoryId} onChange={(e) => setFormCategoryId(e.target.value)}>
                    <option value="">Select category...</option>
                    {filteredCategories.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Name</label>
                  <input type="text" placeholder="Transaction name..." value={formMerchant} onChange={(e) => setFormMerchant(e.target.value)} />
                </div>
                <div className="form-group" style={{ flex: 2 }}>
                  <label>Note</label>
                  <input type="text" placeholder="Optional note..." value={formNote} onChange={(e) => setFormNote(e.target.value)} />
                </div>
              </div>
              <div className="form-row" style={{ alignItems: 'center', gap: 16 }}>
                <label className="recurring-toggle-label">
                  <input type="checkbox" checked={formRecurring} onChange={(e) => setFormRecurring(e.target.checked)} />
                  Make this recurring
                </label>
                {formRecurring && (
                  <div className="form-group" style={{ marginBottom: 0, minWidth: 160 }}>
                    <select className="form-select" value={formFrequency} onChange={(e) => setFormFrequency(e.target.value)}>
                      <option value="monthly">Monthly</option>
                      <option value="biweekly">Every 2 Weeks</option>
                      <option value="weekly">Weekly</option>
                    </select>
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <button className="primary-btn" disabled={formSaving || uploading}>
                  {formSaving ? 'Saving...' : 'Save Transaction'}
                </button>
                <button type="button" className="secondary-btn" onClick={() => fileInputRef.current.click()} disabled={uploading || formSaving}>
                  {uploading ? 'Uploading...' : 'Upload files/Take a photo'}
                </button>
              </div>
              <div style={{ fontSize: '0.85rem', color: '#666', marginTop: '4px' }}>
                Tap the button to snap a photo or choose an existing file
              </div>
              <input type="file" ref={fileInputRef} onChange={handleFileSelect} style={{ display: 'none' }} accept="image/*,application/pdf" capture="environment" />
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
                <label>Date Range</label>
                <div className="txn-date-range">
                  <div className="txn-date-field">
                    <span className="txn-date-label">From</span>
                    <input
                      type="date"
                      className={`txn-search-input${dateFrom ? ' txn-date-active' : ''}`}
                      value={dateFrom}
                      onChange={(e) => setDateFrom(e.target.value)}
                    />
                  </div>
                  <div className="txn-date-field">
                    <span className="txn-date-label">To</span>
                    <input
                      type="date"
                      className={`txn-search-input${dateTo ? ' txn-date-active' : ''}`}
                      value={dateTo}
                      onChange={(e) => setDateTo(e.target.value)}
                    />
                  </div>
                  {(dateFrom || dateTo) && (
                    <div className="txn-date-range-footer">
                      {dateFrom && dateTo && (
                        <span className="txn-date-range-badge">
                          {formatRangeDate(dateFrom)} – {formatRangeDate(dateTo)}
                        </span>
                      )}
                      <button
                        className="txn-date-clear"
                        onClick={() => { setDateFrom(''); setDateTo(''); }}
                      >
                        Clear
                      </button>
                    </div>
                  )}
                </div>
              </div>

              <div className="txn-filter-group">
                <label>Price Range</label>
                <div className="txn-range-row">
                  <input
                    type="number"
                    className="txn-search-input"
                    placeholder="Min"
                    min="0"
                    step="0.01"
                    value={amountMin}
                    onChange={(e) => { const v = e.target.value; setAmountMin(v !== '' && Number(v) < 0 ? '' : v); }}
                  />
                  <span className="txn-range-sep">–</span>
                  <input
                    type="number"
                    className="txn-search-input"
                    placeholder="Max"
                    min="0"
                    step="0.01"
                    value={amountMax}
                    onChange={(e) => { const v = e.target.value; setAmountMax(v !== '' && Number(v) < 0 ? '' : v); }}
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
                { label: 'Category', options: [{ value: 'category_asc', label: 'A → Z' }, { value: 'category_desc', label: 'Z → A' }] },
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

              {sortBy.length > 0 && (
                <div className="txn-sort-order">
                  <label>Order</label>
                  <div className="txn-sort-order-list">
                    {sortBy.map((key, idx) => (
                      <div key={key} className="txn-sort-chip">
                        <span className="txn-sort-chip-num">{idx + 1}</span>
                        <span className="txn-sort-chip-label">{SORT_LABELS[key]}</span>
                        <div className="txn-sort-chip-actions">
                          <button
                            className="txn-sort-chip-btn"
                            disabled={idx === 0}
                            onClick={() => setSortBy((prev) => {
                              const next = [...prev];
                              [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
                              return next;
                            })}
                            title="Move up"
                          >&#8593;</button>
                          <button
                            className="txn-sort-chip-btn"
                            disabled={idx === sortBy.length - 1}
                            onClick={() => setSortBy((prev) => {
                              const next = [...prev];
                              [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
                              return next;
                            })}
                            title="Move down"
                          >&#8595;</button>
                          <button
                            className="txn-sort-chip-btn txn-sort-chip-remove"
                            onClick={() => setSortBy((prev) => prev.filter((v) => v !== key))}
                            title="Remove"
                          >&times;</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
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
                        {group.items.map((t) => {
                          const isEditing = editingId === t.id;
                          const displayType = isEditing ? editType : t.type;
                          const displayMerchant = isEditing ? (editMerchant || editNote || 'Transaction') : (t.merchant || t.note || 'Transaction');
                          const displayDate = isEditing ? editDate : t.occurred_on;
                          const displayAmount = Math.abs(isEditing ? (Number(editAmount) || 0) : Number(t.amount));
                          const cat = categories.find(c => c.id === t.category_id);
                          const categoryName = cat ? cat.name : null;
                          return (
                            <div key={t.id} className={isEditing ? 'txn-item-wrapper' : ''}>
                              <div className="txn-item" onClick={() => !isEditing && startEditing(t)} style={{ cursor: isEditing ? 'default' : 'pointer' }}>
                                <div className="txn-item-left">
                                  <span className={`txn-item-type ${displayType}`}>
                                    {displayType === 'income' ? '+' : '-'}
                                  </span>
                                  <div className="txn-item-details">
                                    <div className="txn-item-merchant-row">
                                      <span className="txn-item-merchant">{displayMerchant}</span>
                                      {t.recurring_rule_id && <span className="recurring-badge">recurring</span>}
                                      {categoryName && <span className="txn-item-category">{categoryName}</span>}
                                    </div>
                                    <span className="txn-item-date">{displayDate}</span>
                                  </div>
                                </div>
                                <span className={`txn-item-amount ${displayType}`}>
                                  {displayType === 'income' ? '+' : '-'}${displayAmount.toFixed(2)}
                                </span>
                              </div>
                              {isEditing && (
                                <div className="txn-item-edit">
                                  {editError && <div className="txn-edit-error">{editError}</div>}
                                  <form onSubmit={handleSaveEdit}>
                                    <div className="txn-edit-row">
                                      <select className="txn-edit-input" value={editType} onChange={(e) => { setEditType(e.target.value); setEditCategoryId(''); }}>
                                        <option value="expense">Expense</option>
                                        <option value="income">Income</option>
                                      </select>
                                      <input type="number" className="txn-edit-input" step="0.01" min="0.01" placeholder="Amount" value={editAmount} onChange={(e) => setEditAmount(e.target.value)} />
                                      <input type="date" className="txn-edit-input" value={editDate} onChange={(e) => setEditDate(e.target.value)} />
                                    </div>
                                    <div className="txn-edit-row">
                                      <select className="txn-edit-input" value={editCategoryId} onChange={(e) => setEditCategoryId(e.target.value)}>
                                        <option value="">Select category...</option>
                                        {editFilteredCategories.map((c) => (
                                          <option key={c.id} value={c.id}>{c.name}</option>
                                        ))}
                                      </select>
                                      <input type="text" className="txn-edit-input" placeholder="Name..." value={editMerchant} onChange={(e) => setEditMerchant(e.target.value)} />
                                      <input type="text" className="txn-edit-input" placeholder="Note..." value={editNote} onChange={(e) => setEditNote(e.target.value)} />
                                    </div>
                                    <div className="txn-edit-actions">
                                      <button type="submit" className="primary-btn txn-edit-btn" disabled={editSaving}>{editSaving ? 'Saving...' : 'Save'}</button>
                                      <button type="button" className="secondary-btn txn-edit-btn" onClick={cancelEditing}>Cancel</button>
                                    </div>
                                  </form>
                                </div>
                              )}
                            </div>
                          );
                        })}
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
                      const dayNet = dayTxns.reduce((sum, t) => {
                        const amt = Math.abs(Number(t.amount));
                        return sum + (t.type === 'income' ? amt : -amt);
                      }, 0);
                      return (
                        <div
                          key={idx}
                          className={[
                            'calendar-day',
                            !dayObj.isCurrentMonth && 'calendar-day--outside',
                            isSelected && 'calendar-day--selected',
                            isToday && 'calendar-day--today',
                            dayTxns.length > 0 && dayNet > 0 && 'calendar-day--positive',
                            dayTxns.length > 0 && dayNet < 0 && 'calendar-day--negative',
                          ].filter(Boolean).join(' ')}
                          onClick={() => setSelectedDate(dayObj.date)}
                        >
                          <span className="calendar-day-number">{dayObj.date.getDate()}</span>
                          {dayTxns.length > 0 && (
                              <>
                                <span className={`calendar-day-cashflow ${dayNet >= 0 ? 'positive' : 'negative'}`}>
                                  {dayNet >= 0 ? '+' : '-'}${Math.abs(dayNet).toFixed(2)}
                                </span>
                                <div className="calendar-day-indicators">
                                  {dayTxns.length <= 3
                                    ? dayTxns.map((t) => (
                                        <span key={t.id} className={`calendar-dot ${t.type === 'income' ? 'income' : 'outcome'}`} />
                                      ))
                                    : <span className="calendar-day-count">{dayTxns.length}</span>
                                  }
                                </div>
                              </>
                          )}
                        </div>
                      );
                    })}
                  </div>

                  {loading && <p style={{ textAlign: 'center', padding: 12, color: '#888' }}>Loading...</p>}
                </div>

                {aggregation !== 'default' && transactions.length > 0 && (
                  <div className="card">
                    <div className="collapsible-header" onClick={() => setCashFlowOpen(!cashFlowOpen)}>
                      <h2 className="card-title">
                        {aggregation.charAt(0).toUpperCase() + aggregation.slice(1)} Cash Flow
                      </h2>
                      <span className={`collapsible-arrow${cashFlowOpen ? ' open' : ''}`}>&#9662;</span>
                    </div>
                    {cashFlowOpen && (
                      <div className="calendar-summary-list">
                        {groupTransactions(transactions, aggregation).map((group, gi) => {
                          const groupNet = group.items.reduce((sum, t) => {
                            const amt = Math.abs(Number(t.amount));
                            return sum + (t.type === 'income' ? amt : -amt);
                          }, 0);
                          const groupIncome = group.items.filter(t => t.type === 'income').reduce((s, t) => s + Math.abs(Number(t.amount)), 0);
                          const groupExpense = group.items.filter(t => t.type === 'expense').reduce((s, t) => s + Math.abs(Number(t.amount)), 0);
                          return (
                            <div key={gi} className="calendar-summary-row">
                              <span className="calendar-summary-label">{group.label}</span>
                              <div className="calendar-summary-amounts">
                                {groupIncome > 0 && <span className="calendar-summary-amount income">+${groupIncome.toFixed(2)}</span>}
                                {groupExpense > 0 && <span className="calendar-summary-amount expense">-${groupExpense.toFixed(2)}</span>}
                                <span className={`calendar-summary-net ${groupNet >= 0 ? 'income' : 'expense'}`}>
                                  {groupNet >= 0 ? '+' : '-'}${Math.abs(groupNet).toFixed(2)}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}

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
                        {selectedTxns.map((t) => {
                          const isEditing = editingId === t.id;
                          const displayType = isEditing ? editType : t.type;
                          const displayMerchant = isEditing ? (editMerchant || editNote || 'Transaction') : (t.merchant || t.note || 'Transaction');
                          const displayAmount = Math.abs(isEditing ? (Number(editAmount) || 0) : Number(t.amount));
                          const calCat = categories.find(c => c.id === t.category_id);
                          const calCategoryName = calCat ? calCat.name : null;
                          return (
                            <div key={t.id} className={isEditing ? 'txn-item-wrapper' : ''}>
                              <div className="calendar-txn-item" onClick={() => !isEditing && startEditing(t)} style={{ cursor: isEditing ? 'default' : 'pointer' }}>
                                <div className="calendar-txn-info">
                                  <span className={`calendar-txn-type ${displayType}`}>
                                    {displayType === 'income' ? '+' : '-'}
                                  </span>
                                  <span className="calendar-txn-merchant">{displayMerchant}</span>
                                  {calCategoryName && <span className="txn-item-category">{calCategoryName}</span>}
                                </div>
                                <span className={`calendar-txn-amount ${displayType}`}>
                                  {displayType === 'income' ? '+' : '-'}${displayAmount.toFixed(2)}
                                </span>
                              </div>
                              {isEditing && (
                                <div className="txn-item-edit">
                                  {editError && <div className="txn-edit-error">{editError}</div>}
                                  <form onSubmit={handleSaveEdit}>
                                    <div className="txn-edit-row">
                                      <select className="txn-edit-input" value={editType} onChange={(e) => { setEditType(e.target.value); setEditCategoryId(''); }}>
                                        <option value="expense">Expense</option>
                                        <option value="income">Income</option>
                                      </select>
                                      <input type="number" className="txn-edit-input" step="0.01" min="0.01" placeholder="Amount" value={editAmount} onChange={(e) => setEditAmount(e.target.value)} />
                                      <input type="date" className="txn-edit-input" value={editDate} onChange={(e) => setEditDate(e.target.value)} />
                                    </div>
                                    <div className="txn-edit-row">
                                      <select className="txn-edit-input" value={editCategoryId} onChange={(e) => setEditCategoryId(e.target.value)}>
                                        <option value="">Select category...</option>
                                        {editFilteredCategories.map((c) => (
                                          <option key={c.id} value={c.id}>{c.name}</option>
                                        ))}
                                      </select>
                                      <input type="text" className="txn-edit-input" placeholder="Name..." value={editMerchant} onChange={(e) => setEditMerchant(e.target.value)} />
                                      <input type="text" className="txn-edit-input" placeholder="Note..." value={editNote} onChange={(e) => setEditNote(e.target.value)} />
                                    </div>
                                    <div className="txn-edit-actions">
                                      <button type="submit" className="primary-btn txn-edit-btn" disabled={editSaving}>{editSaving ? 'Saving...' : 'Save'}</button>
                                      <button type="button" className="secondary-btn txn-edit-btn" onClick={cancelEditing}>Cancel</button>
                                    </div>
                                  </form>
                                </div>
                              )}
                            </div>
                          );
                        })}
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

            <div className="txn-filter-group">
              <label>Group By</label>
              <div className="txn-radio-group">
                {[
                  { value: 'default', label: 'Default' },
                  { value: 'daily', label: 'Daily' },
                  { value: 'weekly', label: 'Weekly' },
                  { value: 'monthly', label: 'Monthly' },
                  { value: 'yearly', label: 'Yearly' },
                ].filter((opt) => viewMode === 'list' || opt.value !== 'default').map((opt) => (
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

            {viewMode === 'calendar' && categorySummary.length > 0 && (
              <div className="category-summary">
                <div className="collapsible-header" onClick={() => setCategorySummaryOpen(!categorySummaryOpen)}>
                  <h3 className="card-title">Category Summary</h3>
                  <span className={`collapsible-arrow${categorySummaryOpen ? ' open' : ''}`}>&#9662;</span>
                </div>
                {categorySummaryOpen && (
                  <>
                    {categorySummary.map(([name, totals]) => {
                      return (
                        <div key={name} className="category-summary-item">
                          <span className="category-summary-name">{name}</span>
                          <div className="category-summary-amounts">
                            {totals.expense > 0 && (
                              <span className="category-summary-amount expense">-${totals.expense.toFixed(2)}</span>
                            )}
                            {totals.income > 0 && (
                              <span className="category-summary-amount income">+${totals.income.toFixed(2)}</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                    {(() => {
                      const totalIncome = categorySummary.reduce((s, [, t]) => s + t.income, 0);
                      const totalExpense = categorySummary.reduce((s, [, t]) => s + t.expense, 0);
                      const monthNet = totalIncome - totalExpense;
                      return (
                        <div className="category-summary-total">
                          <span className="category-summary-name">Monthly Total</span>
                          <span className={`category-summary-amount ${monthNet >= 0 ? 'income' : 'expense'}`}>
                            {monthNet >= 0 ? '+' : '-'}${Math.abs(monthNet).toFixed(2)}
                          </span>
                        </div>
                      );
                    })()}
                  </>
                )}
              </div>
            )}
          </aside>
        </div>
      </div>
    </>
  );
}

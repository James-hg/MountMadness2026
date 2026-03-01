import { useState, useEffect, useCallback, useRef } from 'react';
import NavBar from './NavBar';
import { apiGet, apiPost, apiPut } from '../api';

function toMonthStart(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
}

function formatMonthLabel(monthStr) {
  const [y, m] = monthStr.split('-');
  const d = new Date(Number(y), Number(m) - 1, 1);
  return d.toLocaleDateString('default', { month: 'long', year: 'numeric' });
}

function shiftMonth(monthStr, delta) {
  const [y, m] = monthStr.split('-').map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return toMonthStart(d);
}

export default function BudgetPage() {
  const [monthStart, setMonthStart] = useState(toMonthStart(new Date()));
  const [budget, setBudget] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Total budget form
  const [totalInput, setTotalInput] = useState('');

  // Per-category limit inputs: { [category_id]: string }
  const [limits, setLimits] = useState({});
  const [savingCatId, setSavingCatId] = useState(null);
  const [focusedCatId, setFocusedCatId] = useState(null);
  const originalLimits = useRef({});

  // Allocation mode: 'dollar' or 'percent'
  const [allocMode, setAllocMode] = useState('dollar');
  const allocModeRef = useRef('dollar');

  const fetchBudget = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiGet(`/budget?month_start=${monthStart}`);
      setBudget(data);
      if (data.total_budget_amount) {
        setTotalInput(data.total_budget_amount);
      } else {
        setTotalInput('');
      }
      // Initialize per-category limits (always store originals as dollars)
      const dollarLimits = {};
      for (const cat of data.category_budgets || []) {
        dollarLimits[cat.category_id] = cat.limit_amount;
      }
      originalLimits.current = { ...dollarLimits };
      // Convert to display mode
      if (allocModeRef.current === 'percent' && data.total_budget_amount) {
        const total = Number(data.total_budget_amount);
        const displayLimits = {};
        for (const [catId, val] of Object.entries(dollarLimits)) {
          displayLimits[catId] = ((Number(val) / total) * 100).toFixed(1);
        }
        setLimits(displayLimits);
      } else {
        setLimits(dollarLimits);
      }
    } catch (err) {
      setError(err.message);
      setBudget(null);
    } finally {
      setLoading(false);
    }
  }, [monthStart]);

  useEffect(() => {
    fetchBudget();
  }, [fetchBudget]);

  const handleSetTotal = async (e) => {
    e.preventDefault();
    const amount = parseFloat(totalInput);
    if (!amount || amount <= 0) {
      setError('Enter a valid budget amount.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const data = await apiPost('/budget/total', {
        month_start: monthStart,
        total_budget_amount: amount.toFixed(2),
        use_active_categories: true,
      });
      setBudget(data);
      if (data.total_budget_amount) setTotalInput(data.total_budget_amount);
      const dollarLimits = {};
      for (const cat of data.category_budgets || []) {
        dollarLimits[cat.category_id] = cat.limit_amount;
      }
      originalLimits.current = { ...dollarLimits };
      if (allocModeRef.current === 'percent' && data.total_budget_amount) {
        const total = Number(data.total_budget_amount);
        const displayLimits = {};
        for (const [catId, val] of Object.entries(dollarLimits)) {
          displayLimits[catId] = ((Number(val) / total) * 100).toFixed(1);
        }
        setLimits(displayLimits);
      } else {
        setLimits(dollarLimits);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleLimitChange = (catId, value) => {
    setLimits((prev) => ({ ...prev, [catId]: value }));
  };

  const toLimitDollar = (catId) => {
    // Convert displayed value to dollar amount based on mode
    const val = limits[catId];
    if (allocMode === 'percent') {
      const pctVal = parseFloat(val);
      if (isNaN(pctVal) || pctVal < 0) return NaN;
      return (pctVal / 100) * totalBudget;
    }
    return parseFloat(val);
  };

  const toDisplayValue = (dollarAmount) => {
    // Convert a dollar amount to the display value for current mode
    if (allocMode === 'percent' && totalBudget > 0) {
      return ((dollarAmount / totalBudget) * 100).toFixed(1);
    }
    return dollarAmount;
  };

  const handleLimitSave = async (catId) => {
    const origVal = originalLimits.current[catId];
    const dollarAmount = toLimitDollar(catId);

    // Check if effectively unchanged
    const origDollar = parseFloat(origVal);
    if (!isNaN(dollarAmount) && !isNaN(origDollar) && Math.abs(dollarAmount - origDollar) < 0.005) return;

    if (isNaN(dollarAmount) || dollarAmount < 0) {
      setLimits((prev) => ({ ...prev, [catId]: toDisplayValue(origVal) }));
      return;
    }

    // Sum-based validation: all categories' limits must not exceed total budget
    const otherCatsTotal = Object.entries(originalLimits.current)
      .filter(([id]) => id !== catId)
      .reduce((sum, [, val]) => sum + Number(val), 0);

    if (otherCatsTotal + dollarAmount > totalBudget && dollarAmount > origDollar) {
      const available = Math.max(0, totalBudget - otherCatsTotal);
      setError(allocMode === 'percent'
        ? `Total exceeds 100%. Available: ${totalBudget > 0 ? ((available / totalBudget) * 100).toFixed(1) : 0}%`
        : `Total exceeds budget. Available: $${available.toFixed(2)}`);
      setLimits((prev) => ({ ...prev, [catId]: toDisplayValue(origVal) }));
      return;
    }

    setSavingCatId(catId);
    try {
      await apiPut('/budget/category', {
        month_start: monthStart,
        category_id: catId,
        limit_amount: dollarAmount.toFixed(2),
      });
      await fetchBudget();
    } catch {
      // Revert on error
      setLimits((prev) => ({ ...prev, [catId]: toDisplayValue(origVal) }));
    } finally {
      setSavingCatId(null);
    }
  };

  const handleModeSwitch = (mode) => {
    if (mode === allocMode) return;
    // Convert all displayed values
    const newLimits = {};
    for (const [catId, val] of Object.entries(limits)) {
      const dollar = allocMode === 'percent' && totalBudget > 0
        ? (parseFloat(val) / 100) * totalBudget
        : parseFloat(val);
      if (mode === 'percent' && totalBudget > 0) {
        newLimits[catId] = ((dollar / totalBudget) * 100).toFixed(1);
      } else {
        newLimits[catId] = isNaN(dollar) ? val : dollar.toFixed(2);
      }
    }
    setLimits(newLimits);
    setAllocMode(mode);
    allocModeRef.current = mode;
  };

  const handleRebalance = async () => {
    if (!totalBudget) return;
    setSaving(true);
    setError('');
    try {
      const data = await apiPost('/budget/total', {
        month_start: monthStart,
        total_budget_amount: totalBudget.toFixed(2),
        use_active_categories: true,
        force_reset: true,
      });
      setBudget(data);
      if (data.total_budget_amount) setTotalInput(data.total_budget_amount);
      const dollarLimits = {};
      for (const cat of data.category_budgets || []) {
        dollarLimits[cat.category_id] = cat.limit_amount;
      }
      originalLimits.current = { ...dollarLimits };
      if (allocModeRef.current === 'percent' && data.total_budget_amount) {
        const total = Number(data.total_budget_amount);
        const displayLimits = {};
        for (const [catId, val] of Object.entries(dollarLimits)) {
          displayLimits[catId] = ((Number(val) / total) * 100).toFixed(1);
        }
        setLimits(displayLimits);
      } else {
        setLimits(dollarLimits);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  // Computed values
  const categories = budget?.category_budgets || [];
  const totalBudget = budget?.total_budget_amount ? Number(budget.total_budget_amount) : 0;
  const totalSpent = categories.reduce((sum, c) => sum + Number(c.spent_amount), 0);
  const totalAllocated = categories.reduce((sum, c) => sum + Number(c.limit_amount), 0);
  const totalRemaining = totalBudget - totalSpent;
  const unallocated = totalBudget - totalAllocated;
  const hasBudget = budget?.total_budget_amount != null;

  return (
    <>
      <NavBar />
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Budget</h1>
        </div>

        {/* Month Navigator */}
        <div className="budget-month-nav">
          <button className="month-nav-btn" onClick={() => setMonthStart(shiftMonth(monthStart, -1))}>&#8249;</button>
          <span className="month-nav-label">{formatMonthLabel(monthStart)}</span>
          <button className="month-nav-btn" onClick={() => setMonthStart(shiftMonth(monthStart, 1))}>&#8250;</button>
        </div>

        {error && <p className="form-error">{error}</p>}

        {/* Set Total Budget */}
        <div className="card">
          <h2 className="card-title">{hasBudget ? 'Update Monthly Budget' : 'Set Monthly Budget'}</h2>
          <form className="budget-total-form" onSubmit={handleSetTotal}>
            <div className="form-group" style={{ flex: 1 }}>
              <label>Total Budget ({budget?.currency || 'CAD'})</label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                placeholder="e.g. 2000.00"
                value={totalInput}
                onChange={(e) => setTotalInput(e.target.value)}
                disabled={saving}
              />
            </div>
            <button className="primary-btn" type="submit" disabled={saving || loading}>
              {saving ? 'Saving...' : hasBudget ? 'Update Budget' : 'Set Budget'}
            </button>
          </form>
        </div>

        {loading && <p style={{ textAlign: 'center', padding: 16, color: '#888' }}>Loading...</p>}

        {/* Overview Summary */}
        {hasBudget && (
          <div className="summary-cards">
            <div className="summary-card">
              <span className="summary-label">Total Budget</span>
              <span className="summary-value">${totalBudget.toFixed(2)}</span>
            </div>
            <div className="summary-card">
              <span className="summary-label">Total Spent</span>
              <span className="summary-value" style={{ color: '#e74c3c' }}>
                ${totalSpent.toFixed(2)}
              </span>
            </div>
            <div className="summary-card">
              <span className="summary-label">Remaining</span>
              <span className="summary-value" style={{ color: totalRemaining >= 0 ? '#2ecc71' : '#e74c3c' }}>
                {totalRemaining < 0 ? '-' : ''}${Math.abs(totalRemaining).toFixed(2)}
              </span>
            </div>
            <div className="summary-card">
              <span className="summary-label">Unallocated</span>
              <span className="summary-value" style={{ color: unallocated < 0 ? '#e74c3c' : unallocated > 0 ? '#888' : '#2ecc71' }}>
                {unallocated < 0 ? '-' : ''}${Math.abs(unallocated).toFixed(2)}
              </span>
              {unallocated < 0 && (
                <button className="rebalance-btn" onClick={handleRebalance} disabled={saving}>
                  {saving ? 'Rebalancing...' : 'Rebalance'}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Category Budgets */}
        {hasBudget && categories.length > 0 && (
          <div className="card">
            <div className="budget-card-header">
              <h2 className="card-title">Category Budgets</h2>
              <div className="budget-mode-toggle">
                <button
                  className={`budget-mode-btn${allocMode === 'dollar' ? ' active' : ''}`}
                  onClick={() => handleModeSwitch('dollar')}
                >$</button>
                <button
                  className={`budget-mode-btn${allocMode === 'percent' ? ' active' : ''}`}
                  onClick={() => handleModeSwitch('percent')}
                >%</button>
              </div>
            </div>
            <div className="budget-list">
              {categories.map((cat) => {
                const limit = Number(cat.limit_amount);
                const spent = Number(cat.spent_amount);
                const remaining = limit - spent;
                const pct = limit > 0 ? Math.round((spent / limit) * 100) : (spent > 0 ? 100 : 0);
                const barWidth = Math.min(pct, 100);
                const isSaving = savingCatId === cat.category_id;

                let fillClass = '';
                if (pct >= 100) fillClass = ' danger';
                else if (pct >= 80) fillClass = ' warning';

                return (
                  <div key={cat.category_id} className="budget-item">
                    <div className="budget-item-header">
                      <span className="budget-category">
                        {cat.category_name}
                        {cat.is_user_modified && <span className="budget-modified-badge">edited</span>}
                      </span>
                      <div className="budget-amounts-group">
                        <span className="budget-amounts" style={{ color: '#e74c3c' }}>
                          -${spent.toFixed(2)}
                        </span>
                        <span className="budget-amounts" style={{ color: remaining >= 0 ? '#2ecc71' : '#e74c3c' }}>
                          {remaining >= 0 ? `$${remaining.toFixed(2)} left` : `-$${Math.abs(remaining).toFixed(2)} over`}
                        </span>
                      </div>
                    </div>
                    <div className="budget-allocator-row">
                      <label className="budget-allocator-label">{allocMode === 'percent' ? '%' : 'Limit'}</label>
                      <input
                        className="budget-limit-input"
                        type="number"
                        step={allocMode === 'percent' ? '0.1' : '0.01'}
                        min="0"
                        value={limits[cat.category_id] ?? ''}
                        onChange={(e) => handleLimitChange(cat.category_id, e.target.value)}
                        onFocus={() => setFocusedCatId(cat.category_id)}
                        onBlur={() => { setFocusedCatId(null); handleLimitSave(cat.category_id); }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') { e.target.blur(); }
                        }}
                        disabled={isSaving}
                      />
                      {isSaving && <span className="budget-saving-indicator">saving...</span>}
                      <span className="budget-available-label">
                        {focusedCatId === cat.category_id
                          ? (allocMode === 'percent' && totalBudget > 0
                              ? `${((Math.max(0, unallocated) / totalBudget) * 100).toFixed(1)}% available fund`
                              : `$${Math.max(0, unallocated).toFixed(2)} available fund`)
                          : (remaining >= 0
                              ? `$${remaining.toFixed(2)} left`
                              : `-$${Math.abs(remaining).toFixed(2)} over`)}
                      </span>
                    </div>
                    <div className="progress-bar">
                      <div className={`progress-fill${fillClass}`} style={{ width: `${barWidth}%` }} />
                    </div>
                    <span className="budget-percent">{pct}% used</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Empty State */}
        {!loading && !hasBudget && (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">💰</div>
              <h3>No budget set for {formatMonthLabel(monthStart)}</h3>
              <p>Enter a total budget above to automatically allocate spending limits across your expense categories.</p>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import NavBar from './NavBar';
import GoalsChatPanel from './GoalsChatPanel';
import {
  createGoal,
  deleteGoal,
  getGoal,
  getGoals,
  updateGoal,
} from '../services/goalsClient';

const STATUS_OPTIONS = ['active', 'paused', 'completed', 'cancelled', 'all'];

function getStoredCurrency() {
  try {
    const raw = localStorage.getItem('user');
    if (!raw) return 'CAD';
    const parsed = JSON.parse(raw);
    return parsed?.base_currency || 'CAD';
  } catch {
    return 'CAD';
  }
}

function toMoneyInput(value) {
  const parsed = Number.parseFloat(String(value ?? '0'));
  if (!Number.isFinite(parsed)) return '';
  return parsed.toFixed(2);
}

function parseAmount(value) {
  const parsed = Number.parseFloat(String(value ?? '0'));
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatMoney(value, currency) {
  const amount = parseAmount(value);
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency || 'CAD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `$${amount.toFixed(2)}`;
  }
}

function statusLabel(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export default function GoalsPage() {
  const [statusFilter, setStatusFilter] = useState('active');
  const [goals, setGoals] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [currency, setCurrency] = useState('CAD');

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createSaving, setCreateSaving] = useState(false);
  const [createError, setCreateError] = useState('');
  const [createName, setCreateName] = useState('');
  const [createTarget, setCreateTarget] = useState('');
  const [createSaved, setCreateSaved] = useState('0.00');
  const [createDeadline, setCreateDeadline] = useState('');

  const [selectedGoal, setSelectedGoal] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailSaving, setDetailSaving] = useState(false);
  const [detailError, setDetailError] = useState('');

  const refreshGoals = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getGoals(statusFilter);
      setGoals(Array.isArray(data) ? data : []);
    } catch (err) {
      setGoals([]);
      setError(err?.message || 'Failed to load goals');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    setCurrency(getStoredCurrency());
    refreshGoals();
  }, [refreshGoals]);

  const openCreateModal = () => {
    setCreateName('');
    setCreateTarget('');
    setCreateSaved('0.00');
    setCreateDeadline('');
    setCreateError('');
    setShowCreateModal(true);
  };

  const handleCreateGoal = async (e) => {
    e.preventDefault();
    setCreateError('');

    const payload = {
      name: createName.trim(),
      target_amount: toMoneyInput(createTarget),
      saved_amount: toMoneyInput(createSaved || '0'),
      deadline_date: createDeadline,
    };

    if (!payload.name || !payload.target_amount || !payload.deadline_date) {
      setCreateError('Please fill name, target amount, and deadline.');
      return;
    }

    setCreateSaving(true);
    try {
      await createGoal(payload);
      setShowCreateModal(false);
      await refreshGoals();
    } catch (err) {
      setCreateError(err?.message || 'Failed to create goal');
    } finally {
      setCreateSaving(false);
    }
  };

  const openGoalDetail = async (goalId) => {
    setDetailLoading(true);
    setDetailError('');
    setSelectedGoal(null);
    try {
      const goal = await getGoal(goalId);
      setSelectedGoal(goal);
    } catch (err) {
      setDetailError(err?.message || 'Failed to load goal details');
    } finally {
      setDetailLoading(false);
    }
  };

  const closeGoalDetail = () => {
    setSelectedGoal(null);
    setDetailError('');
  };

  const applyGoalPatch = async (patch) => {
    if (!selectedGoal) return;
    setDetailSaving(true);
    setDetailError('');
    try {
      const updated = await updateGoal(selectedGoal.id, patch);
      setSelectedGoal(updated);
      await refreshGoals();
    } catch (err) {
      setDetailError(err?.message || 'Failed to update goal');
    } finally {
      setDetailSaving(false);
    }
  };

  const handleAddFifty = async () => {
    if (!selectedGoal) return;
    const nextSaved = parseAmount(selectedGoal.saved_amount) + 50;
    await applyGoalPatch({ saved_amount: toMoneyInput(nextSaved) });
  };

  const handleMarkCompleted = async () => {
    await applyGoalPatch({ status: 'completed' });
  };

  const handleDeleteGoal = async () => {
    if (!selectedGoal) return;
    setDetailSaving(true);
    setDetailError('');
    try {
      await deleteGoal(selectedGoal.id);
      closeGoalDetail();
      await refreshGoals();
    } catch (err) {
      setDetailError(err?.message || 'Failed to delete goal');
    } finally {
      setDetailSaving(false);
    }
  };

  const listContent = useMemo(() => {
    if (loading) {
      return <div className="goals-state">Loading goals...</div>;
    }

    if (error) {
      return <div className="goals-state goals-state--error">{error}</div>;
    }

    if (goals.length === 0) {
      return (
        <div className="empty-state">
          <div className="empty-state-icon">🎯</div>
          <h3>No goals yet</h3>
          <p>Create your first goal to track your progress.</p>
        </div>
      );
    }

    return (
      <div className="goals-list">
        {goals.map((goal) => {
          const progress = Math.max(0, Math.min(100, Number(goal.progress_pct || 0)));
          const trackState =
            goal.on_track === null ? 'na' : goal.on_track ? 'on-track' : 'behind';
          const trackLabel =
            goal.on_track === null ? 'N/A' : goal.on_track ? 'On track' : 'Behind';

          return (
            <button
              type="button"
              key={goal.id}
              className="goal-card"
              onClick={() => openGoalDetail(goal.id)}
            >
              <div className="goal-card-head">
                <span className="goal-name">{goal.name}</span>
                <span className={`goal-chip goal-chip--status goal-chip--${goal.status}`}>
                  {statusLabel(goal.status)}
                </span>
              </div>

              <div className="goal-progress-track" aria-label={`${goal.progress_pct}% progress`}>
                <div className="goal-progress-fill" style={{ width: `${progress}%` }} />
              </div>

              <div className="goal-amount-row">
                <span>{formatMoney(goal.saved_amount, currency)} saved</span>
                <span>{formatMoney(goal.target_amount, currency)} target</span>
              </div>
              <div className="goal-amount-row">
                <span>Remaining {formatMoney(goal.remaining_amount, currency)}</span>
                <span>
                  Monthly required {formatMoney(goal.recommended_monthly_save_amount, currency)}
                </span>
              </div>

              <div className="goal-foot-row">
                <span className={`goal-chip goal-chip--track goal-chip--${trackState}`}>
                  {trackLabel}
                </span>
                <span className="goal-months-left">
                  {goal.months_left} month{goal.months_left === 1 ? '' : 's'} left
                </span>
              </div>
            </button>
          );
        })}
      </div>
    );
  }, [currency, error, goals, loading]);

  return (
    <>
      <NavBar />
      <div className="page-container goals-page">
        <div className="page-header">
          <h1 className="page-title">Goals</h1>
          <button type="button" className="primary-btn" onClick={openCreateModal}>
            Create Goal
          </button>
        </div>

        <div className="goals-filter-row">
          {STATUS_OPTIONS.map((status) => (
            <button
              key={status}
              type="button"
              className={`goals-filter-btn ${statusFilter === status ? 'active' : ''}`}
              onClick={() => setStatusFilter(status)}
            >
              {status === 'all' ? 'All' : statusLabel(status)}
            </button>
          ))}
        </div>

        {listContent}
        <GoalsChatPanel />
      </div>

      {showCreateModal && (
        <div className="goals-modal-backdrop" onClick={() => setShowCreateModal(false)}>
          <div className="goals-modal" onClick={(e) => e.stopPropagation()}>
            <div className="goals-modal-head">
              <h3>Create Goal</h3>
              <button type="button" className="icon-btn" onClick={() => setShowCreateModal(false)}>
                ✕
              </button>
            </div>
            <form className="page-form" onSubmit={handleCreateGoal}>
              <div className="form-group">
                <label>Goal Name</label>
                <input
                  value={createName}
                  onChange={(e) => setCreateName(e.target.value)}
                  placeholder="Trip to Japan"
                  maxLength={120}
                />
              </div>
              <div className="form-group">
                <label>Target Amount</label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={createTarget}
                  onChange={(e) => setCreateTarget(e.target.value)}
                  placeholder="2000.00"
                />
              </div>
              <div className="form-group">
                <label>Already Saved</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={createSaved}
                  onChange={(e) => setCreateSaved(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label>Deadline</label>
                <input
                  type="date"
                  value={createDeadline}
                  onChange={(e) => setCreateDeadline(e.target.value)}
                />
              </div>
              {createError && <div className="goals-state goals-state--error">{createError}</div>}
              <div className="goals-modal-actions">
                <button type="button" className="secondary-btn" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="primary-btn" disabled={createSaving}>
                  {createSaving ? 'Creating...' : 'Create Goal'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {(detailLoading || selectedGoal || detailError) && (
        <div className="goals-modal-backdrop" onClick={closeGoalDetail}>
          <div className="goals-modal goals-modal--detail" onClick={(e) => e.stopPropagation()}>
            <div className="goals-modal-head">
              <h3>Goal Details</h3>
              <button type="button" className="icon-btn" onClick={closeGoalDetail}>
                ✕
              </button>
            </div>

            {detailLoading && <div className="goals-state">Loading details...</div>}
            {!detailLoading && detailError && (
              <div className="goals-state goals-state--error">{detailError}</div>
            )}

            {!detailLoading && selectedGoal && (
              <div className="goal-detail">
                <div className="goal-detail-name-row">
                  <h4>{selectedGoal.name}</h4>
                  <span className={`goal-chip goal-chip--status goal-chip--${selectedGoal.status}`}>
                    {statusLabel(selectedGoal.status)}
                  </span>
                </div>

                <div className="goal-progress-track">
                  <div
                    className="goal-progress-fill"
                    style={{ width: `${Math.max(0, Math.min(100, Number(selectedGoal.progress_pct || 0)))}%` }}
                  />
                </div>

                <div className="goal-detail-grid">
                  <div className="goal-detail-item">
                    <span>Saved</span>
                    <strong>{formatMoney(selectedGoal.saved_amount, currency)}</strong>
                  </div>
                  <div className="goal-detail-item">
                    <span>Target</span>
                    <strong>{formatMoney(selectedGoal.target_amount, currency)}</strong>
                  </div>
                  <div className="goal-detail-item">
                    <span>Remaining</span>
                    <strong>{formatMoney(selectedGoal.remaining_amount, currency)}</strong>
                  </div>
                  <div className="goal-detail-item">
                    <span>Monthly Required</span>
                    <strong>{formatMoney(selectedGoal.recommended_monthly_save_amount, currency)}</strong>
                  </div>
                  <div className="goal-detail-item">
                    <span>Shortfall</span>
                    <strong>{formatMoney(selectedGoal.shortfall_amount, currency)}</strong>
                  </div>
                  <div className="goal-detail-item">
                    <span>Progress</span>
                    <strong>{selectedGoal.progress_pct}%</strong>
                  </div>
                </div>

                <div className="goals-modal-actions">
                  <button
                    type="button"
                    className="secondary-btn"
                    disabled={detailSaving}
                    onClick={handleAddFifty}
                  >
                    Add $50 to Saved
                  </button>
                  <button
                    type="button"
                    className="secondary-btn"
                    disabled={detailSaving}
                    onClick={handleMarkCompleted}
                  >
                    Mark Completed
                  </button>
                  <button
                    type="button"
                    className="secondary-btn goals-danger-btn"
                    disabled={detailSaving}
                    onClick={handleDeleteGoal}
                  >
                    Delete Goal
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

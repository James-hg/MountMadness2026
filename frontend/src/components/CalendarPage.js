import { useState, useEffect, useCallback } from 'react';
import NavBar from './NavBar';
import { apiGet } from '../api';

function formatDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

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

export default function CalendarPage() {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedDate, setSelectedDate] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerYear, setPickerYear] = useState(new Date().getFullYear());
  const [pickerMode, setPickerMode] = useState('month'); // 'month' or 'year'
  const [yearRangeStart, setYearRangeStart] = useState(Math.floor(new Date().getFullYear() / 12) * 12);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    try {
      const firstDay = `${year}-${String(month + 1).padStart(2, '0')}-01`;
      const lastDay = new Date(year, month + 1, 0);
      const lastDayStr = formatDate(lastDay);

      let allItems = [];
      let offset = 0;
      const limit = 100;
      let hasMore = true;

      while (hasMore) {
        const data = await apiGet(
          `/transactions?date_from=${firstDay}&date_to=${lastDayStr}&limit=${limit}&offset=${offset}`
        );
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
  }, [year, month]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  function transactionsForDate(dateObj) {
    const dateStr = formatDate(dateObj);
    return transactions.filter((t) => t.occurred_on === dateStr);
  }

  const goToPrevMonth = () => {
    setCurrentDate(new Date(year, month - 1, 1));
    setSelectedDate(null);
  };

  const goToNextMonth = () => {
    setCurrentDate(new Date(year, month + 1, 1));
    setSelectedDate(null);
  };

  const goToToday = () => {
    setCurrentDate(new Date());
    setSelectedDate(new Date());
  };

  const openPicker = () => {
    setPickerYear(year);
    setPickerMode('month');
    setPickerOpen(true);
  };

  const selectMonth = (m) => {
    setCurrentDate(new Date(pickerYear, m, 1));
    setSelectedDate(null);
    setPickerOpen(false);
  };

  const openYearPicker = () => {
    setYearRangeStart(Math.floor(pickerYear / 12) * 12);
    setPickerMode('year');
  };

  const selectYear = (y) => {
    setPickerYear(y);
    setPickerMode('month');
  };

  const calendarDays = getCalendarDays(year, month);
  const todayStr = new Date().toDateString();
  const selectedTxns = selectedDate ? transactionsForDate(selectedDate) : [];

  return (
    <>
      <NavBar />
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Calendar</h1>
        </div>

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
                            className={`calendar-picker-month${i === month && pickerYear === year ? ' active' : ''}`}
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
                            className={`calendar-picker-month${y === year ? ' active' : ''}`}
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
                            <span
                              key={t.id}
                              className={`calendar-dot ${t.type === 'income' ? 'income' : 'outcome'}`}
                            />
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
      </div>
    </>
  );
}

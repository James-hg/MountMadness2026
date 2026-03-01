import { useState, useRef } from 'react';
import NavBar from './NavBar';
import { apiPost, API_BASE, apiUpload } from '../api';

// Helper to get auth token
const getAuthToken = () => localStorage.getItem('access_token');

export default function StatementUploadPage() {
  const [file, setFile] = useState(null);
  const [extracted, setExtracted] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const fileInputRef = useRef(null);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files && e.target.files[0];
    if (selectedFile) {
      setFile(selectedFile);
      handleUpload(selectedFile);
    }
  };

  const handleUpload = async (fileToUpload) => {
    setLoading(true);
    setError('');
    setSuccess('');
    setExtracted([]);
    setCategories([]);

    const token = getAuthToken();
    if (!token) {
      setError("Authentication error: No token found.");
      setLoading(false);
      return;
    }

    const formData = new FormData();
    formData.append('file', fileToUpload);

    try {
      const response = await fetch(`${API_BASE}/transactions/upload-statement`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to process statement.');
      }

      const data = await response.json();
      // Give each extracted item a unique temp ID for state management
      const itemsWithIds = data.extracted_transactions.map((item, index) => ({
        ...item,
        id: `temp-${index}`,
        category_id: '', // Default to empty category
        include: true, // Default to include
      }));
      setExtracted(itemsWithIds);
      setCategories(data.all_expense_categories || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleItemChange = (id, field, value) => {
    setExtracted(prev =>
      prev.map(item => (item.id === id ? { ...item, [field]: value } : item))
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    setSuccess('');

    const transactionsToSave = extracted
      .filter(item => item.include && item.category_id)
      .map(item => ({
        type: 'expense',
        amount: item.amount,
        occurred_on: item.occurred_on,
        category_id: item.category_id,
        merchant: item.merchant,
        note: `Imported from ${file.name}`,
      }));

    if (transactionsToSave.length === 0) {
      setError("No transactions selected or no categories assigned.");
      setSaving(false);
      return;
    }

    try {
      const result = await apiPost('/transactions/bulk', { transactions: transactionsToSave });
      setSuccess(`Successfully imported ${result.created_count} transactions!`);
      // Clear the form
      reset();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const reset = () => {
    setFile(null);
    setExtracted([]);
    setCategories([]);
    setError('');
    setSuccess('');
    setLoading(false);
    setSaving(false);
  };

  return (
    <>
      <NavBar />
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Import Bank Statement</h1>
        </div>

        {success && <div className="form-success">{success}</div>}
        {error && <div className="form-error">{error}</div>}

        {!file && !loading && (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">📄</div>
              <h3>Upload a Statement</h3>
              <p>Select a PDF or image of your bank statement to begin.</p>
              <button className="primary-btn" onClick={() => fileInputRef.current.click()}>
                Select File
              </button>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileChange}
                style={{ display: 'none' }}
                accept="application/pdf,image/png,image/jpeg,image/webp"
              />
            </div>
          </div>
        )}

        {loading && (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">🤖</div>
              <h3>Analyzing Statement...</h3>
              <p>The AI is reading your document. This may take a moment for large files.</p>
            </div>
          </div>
        )}

        {extracted.length > 0 && !loading && (
          <div className="card">
            <div className="card-title-row">
              <h2 className="card-title">Confirm Transactions</h2>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button className="secondary-btn" onClick={reset}>Cancel</button>
                <button className="primary-btn" onClick={handleSave} disabled={saving}>
                  {saving ? 'Saving...' : `Save ${extracted.filter(i => i.include).length} Transactions`}
                </button>
              </div>
            </div>
            <p>Review the extracted transactions below. Uncheck any you don't want to import and assign a category to each.</p>
            
            <div className="import-table-wrapper">
              <table className="import-table">
                <thead>
                  <tr>
                    <th>Include</th>
                    <th>Date</th>
                    <th>Merchant</th>
                    <th>Amount</th>
                    <th>Category</th>
                  </tr>
                </thead>
                <tbody>
                  {extracted.map(item => (
                    <tr key={item.id}>
                      <td>
                        <input
                          type="checkbox"
                          checked={item.include}
                          onChange={e => handleItemChange(item.id, 'include', e.target.checked)}
                        />
                      </td>
                      <td><input type="date" value={item.occurred_on} onChange={e => handleItemChange(item.id, 'occurred_on', e.target.value)} className="import-table-input" /></td>
                      <td><input type="text" value={item.merchant} onChange={e => handleItemChange(item.id, 'merchant', e.target.value)} className="import-table-input" /></td>
                      <td><input type="number" step="0.01" value={item.amount} onChange={e => handleItemChange(item.id, 'amount', e.target.value)} className="import-table-input" /></td>
                      <td>
                        <select value={item.category_id} onChange={e => handleItemChange(item.id, 'category_id', e.target.value)} className="import-table-input" required>
                          <option value="">-- Select --</option>
                          {categories.map(cat => (<option key={cat.id} value={cat.id}>{cat.name}</option>))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

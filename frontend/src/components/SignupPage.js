import { useState, useMemo } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function SignupPage() {
  const { register, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const strength = useMemo(() => {
    const hasLength = password.length >= 8;
    const hasUpper = /[A-Z]/.test(password);
    const hasNumber = /[0-9]/.test(password);
    const hasSpecial = /[^A-Za-z0-9]/.test(password);
    let score = 0;
    if (hasLength) score++;
    if (hasUpper) score++;
    if (hasNumber) score++;
    if (hasSpecial) score++;
    const colors = ['#e74c3c', '#e67e22', '#f1c40f', '#2ecc71'];
    return { hasLength, hasUpper, hasNumber, hasSpecial, score, color: score > 0 ? colors[score - 1] : '#e0dde8' };
  }, [password]);

  if (isAuthenticated) return <Navigate to="/" replace />;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!name.trim() || !email.trim() || !password) {
      setError('Please fill in all fields.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    setSubmitting(true);
    try {
      await register(name, email, password);
      navigate('/');
    } catch (err) {
      setError(err.message);
      setSubmitting(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-panel">
        <div className="auth-logo">
          <img src="/MountainFinance.png" alt="Mountain Finance" />
        </div>
        <div className="auth-tabs">
          <Link className="auth-tab" to="/auth/login">Login</Link>
          <Link className="auth-tab active" to="/auth/signup">Register</Link>
        </div>
        {error && <div className="auth-error">{error}</div>}
        <form onSubmit={handleSubmit} noValidate>
          <div className="form-group">
            <label htmlFor="name">Full name</label>
            <input
              type="text"
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your full name"
              autoComplete="name"
            />
          </div>
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              type="email"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="password-wrapper">
              <input
                type={showPw ? 'text' : 'password'}
                id="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min 8 chars incl. uppercase, number, special"
                autoComplete="new-password"
              />
              <button type="button" className="show-password-btn" onClick={() => setShowPw(!showPw)}>
                {showPw ? 'Hide' : 'Show'}
              </button>
            </div>
            <div className="password-strength">
              <div className="strength-bar">
                <div
                  className="strength-bar-fill"
                  style={{ width: `${(strength.score / 4) * 100}%`, background: strength.color }}
                />
              </div>
              <div className="strength-requirements">
                <span className={strength.hasLength ? 'met' : ''}>Use at least 8 characters</span>
                <span className={strength.hasUpper ? 'met' : ''}>Add an uppercase letter</span>
                <span className={strength.hasNumber ? 'met' : ''}>Add a number</span>
                <span className={strength.hasSpecial ? 'met' : ''}>Add a special character</span>
              </div>
            </div>
          </div>
          <button type="submit" className="auth-btn" disabled={submitting}>
            {submitting ? 'Creating account...' : 'Create account'}
          </button>
        </form>
        <p className="auth-switch">
          Already have an account? <Link to="/auth/login">Login</Link>
        </p>
      </div>
    </div>
  );
}

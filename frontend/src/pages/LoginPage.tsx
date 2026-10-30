import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import TiltCard from '../components/TiltCard';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, signup, user, isLoading } = useAuth();

  const [mode, setMode] = useState<'signin' | 'signup'>('signin');

  // Form states
  const [selectedRole, setSelectedRole] = useState<'Creator' | 'Reviewer' | 'Administrator'>('Creator');
  const [signupRole, setSignupRole] = useState<'Creator' | 'Reviewer' | 'Administrator'>('Creator');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showSupportModal, setShowSupportModal] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // If already authenticated, redirect directly into the dashboard
  if (user && !isLoading) {
    navigate('/dashboard', { replace: true });
    return null;
  }

  const handleSelectRole = (role: 'Creator' | 'Reviewer' | 'Administrator') => {
    setSelectedRole(role);
    setError(null);
    if (role === 'Creator') {
      setEmail('creator@acme.com');
      setPassword('DemoSecure2026!');
    } else if (role === 'Reviewer') {
      setEmail('reviewer@acme.com');
      setPassword('DemoSecure2026!');
    } else if (role === 'Administrator') {
      setEmail('admin@acme.com');
      setPassword('DemoSecure2026!');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setError('Please provide your email address.');
      return;
    }
    if (!password) {
      setError('Please provide your password.');
      return;
    }
    if (mode === 'signup') {
      if (!firstName.trim() || !lastName.trim()) {
        setError('Please provide your first and last name.');
        return;
      }
      if (password.length < 8) {
        setError('Password must be at least 8 characters long.');
        return;
      }
    }

    setSubmitting(true);
    try {
      if (mode === 'signin') {
        await login(trimmedEmail, password);
      } else {
        const fullName = `${firstName.trim()} ${lastName.trim()}`.trim();
        await signup({
          email: trimmedEmail,
          password,
          full_name: fullName,
          role: 'CREATOR',
        });
      }
      navigate('/dashboard', { replace: true });
    } catch (err: any) {
      const isNetworkIssue =
        err.code === 'ERR_NETWORK' ||
        err.message === 'Network Error' ||
        !err.response ||
        (err.message && err.message.toLowerCase().includes('network'));
      if (isNetworkIssue) {
        setError("Can't reach the server. It may be waking up, try again in a minute.");
      } else {
        const msg = err.message || (mode === 'signup' ? 'Registration failed.' : 'Authentication failed.');
        setError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetry = () => {
    const fakeEvent = { preventDefault: () => {} } as React.FormEvent;
    handleSubmit(fakeEvent);
  };

  return (
    <div className="signin-page-wrapper">
      {/* 3D Geometric Floating Scene */}
      <div className="signin-geom-scene" aria-hidden="true">
        {/* Top-Left 3D Torus */}
        <div className="geom-torus-tl">
          <svg width="140" height="140" viewBox="0 0 150 150" fill="none">
            <defs>
              <radialGradient id="torusTLGrad" cx="35%" cy="30%" r="75%">
                <stop offset="0%" stopColor="#5b86ff" />
                <stop offset="50%" stopColor="#2c5bf0" />
                <stop offset="100%" stopColor="#14349a" />
              </radialGradient>
              <filter id="torusTLShadow" x="-20%" y="-20%" width="150%" height="150%">
                <feDropShadow dx="-6" dy="14" stdDeviation="16" floodColor="#1a2d72" floodOpacity="0.45" />
              </filter>
            </defs>
            <g filter="url(#torusTLShadow)">
              <path
                d="M 75 18 C 108 18 134 42 134 75 C 134 108 108 132 75 132 C 42 132 16 108 16 75 C 16 42 42 18 75 18 Z M 75 48 C 60 48 48 60 48 75 C 48 90 60 102 75 102 C 90 102 102 90 102 75 C 102 60 90 48 75 48 Z"
                fill="url(#torusTLGrad)"
                transform="rotate(-15 75 75)"
              />
            </g>
          </svg>
        </div>

        {/* Bottom-Left 3D Torus */}
        <div className="geom-torus-bl">
          <svg width="150" height="150" viewBox="0 0 150 150" fill="none">
            <g filter="url(#torusTLShadow)">
              <path
                d="M 75 18 C 108 18 134 42 134 75 C 134 108 108 132 75 132 C 42 132 16 108 16 75 C 16 42 42 18 75 18 Z M 75 48 C 60 48 48 60 48 75 C 48 90 60 102 75 102 C 90 102 102 90 102 75 C 102 60 90 48 75 48 Z"
                fill="url(#torusTLGrad)"
                transform="rotate(-30 75 75)"
              />
            </g>
          </svg>
        </div>

        {/* Top-Right 3D Cube */}
        <div className="geom-cube-tr">
          <svg width="140" height="140" viewBox="0 0 140 140" fill="none">
            <defs>
              <linearGradient id="cTop" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#7da2ff" />
                <stop offset="100%" stopColor="#4f79f5" />
              </linearGradient>
              <linearGradient id="cLeft" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#3b66e8" />
                <stop offset="100%" stopColor="#254bc4" />
              </linearGradient>
              <linearGradient id="cRight" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#2950d6" />
                <stop offset="100%" stopColor="#1a359e" />
              </linearGradient>
              <filter id="cShadow" x="-20%" y="-20%" width="150%" height="150%">
                <feDropShadow dx="8" dy="16" stdDeviation="14" floodColor="#1e327b" floodOpacity="0.4" />
              </filter>
            </defs>
            <g filter="url(#cShadow)">
              <polygon points="70,18 122,46 70,74 18,46" fill="url(#cTop)" />
              <polygon points="18,46 70,74 70,126 18,98" fill="url(#cLeft)" />
              <polygon points="70,74 122,46 122,98 70,126" fill="url(#cRight)" />
            </g>
          </svg>
        </div>

        {/* Bottom-Right 3D Pyramid */}
        <div className="geom-pyramid-br">
          <svg width="110" height="110" viewBox="0 0 100 100" fill="none">
            <defs>
              <linearGradient id="pyrTop" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#5580f8" />
                <stop offset="100%" stopColor="#2c5bf0" />
              </linearGradient>
              <linearGradient id="pyrSide" x1="0%" y1="0%" x2="0%" y2="100%">
                <stop offset="0%" stopColor="#1f44c4" />
                <stop offset="100%" stopColor="#132c86" />
              </linearGradient>
            </defs>
            <polygon points="50,15 88,68 50,88" fill="url(#pyrTop)" />
            <polygon points="50,15 12,68 50,88" fill="url(#pyrSide)" />
          </svg>
        </div>

        {/* Floating Depth Sphere */}
        <div className="geom-sphere-br" />

        {/* Sparkle Star Bottom Right */}
        <div className="geom-sparkle-br">
          <svg width="34" height="34" viewBox="0 0 40 40" fill="none">
            <path d="M 20 0 Q 20 20 40 20 Q 20 20 20 40 Q 20 20 0 20 Q 20 20 20 0 Z" fill="#ffffff" opacity="0.9" />
          </svg>
        </div>
      </div>

      {/* Top Bar */}
      <div className="signin-top-bar">
        {/* Back to Home Pill Button */}
        <button
          type="button"
          className="signin-back-pill"
          onClick={() => navigate('/')}
        >
          <span style={{ fontSize: 15 }}>←</span> Back to Home
        </button>

        {/* Floating Center/Right Pill Navbar */}
        <div className="signin-nav-pill">
          <div className="signin-nav-brand" onClick={() => navigate('/')}>
            <span className="signin-brand-icon" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 22, height: 22, borderRadius: 5, background: '#4f46e5', color: '#fff', fontSize: 11, fontWeight: 800 }}>BS</span>
            <span className="signin-brand-title">BrandShield AI</span>
          </div>

          <div className="signin-nav-links">
            <button type="button" className="signin-nav-item" onClick={() => navigate('/')}>
              Features
            </button>
            <button type="button" className="signin-nav-item" onClick={() => navigate('/')}>
              How It Works
            </button>
            <button type="button" className="signin-nav-item" onClick={() => navigate('/')}>
              Governance
            </button>
            <button
              type="button"
              className="signin-nav-item"
              onClick={() => setShowSupportModal(true)}
            >
              Contact
            </button>
          </div>
        </div>
      </div>

      {/* Main Container: Single Centered Card */}
      <div className="signin-main-container">
        <div style={{ maxWidth: 440, margin: '0 auto', width: '100%' }}>
          {/* Global Error Banner */}
          {error && (
            <div className="signin-error-toast" role="alert" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 13, fontWeight: 700, padding: '2px 7px', background: '#ef4444', color: '#fff', borderRadius: '50%', flexShrink: 0 }}>!</span>
              <div style={{ flex: 1, fontSize: 13, lineHeight: 1.4 }}>{error}</div>
              <button
                type="button"
                onClick={handleRetry}
                disabled={submitting}
                className="btn btn-secondary btn-sm"
                style={{ padding: '4px 10px', fontSize: 12, fontWeight: 600, flexShrink: 0 }}
              >
                Retry
              </button>
              <button
                type="button"
                onClick={() => setError(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, fontWeight: 700, flexShrink: 0, color: '#991b1b' }}
                aria-label="Dismiss error"
              >
                ✕
              </button>
            </div>
          )}

          <TiltCard maxTilt={6} glare={true} style={{ borderRadius: 'var(--radius-xl)' }}>
            <form onSubmit={handleSubmit} className="signin-glass-card" style={{ width: '100%', boxSizing: 'border-box' }}>
              {/* Mode Switcher Tabs */}
              <div style={{ display: 'flex', background: 'rgba(0,0,0,0.06)', borderRadius: 10, padding: 4, marginBottom: 20 }}>
                <button
                  type="button"
                  onClick={() => { setMode('signin'); setError(null); }}
                  style={{
                    flex: 1,
                    padding: '9px 12px',
                    borderRadius: 8,
                    border: 'none',
                    fontWeight: 600,
                    fontSize: 13,
                    cursor: 'pointer',
                    background: mode === 'signin' ? '#ffffff' : 'transparent',
                    color: mode === 'signin' ? '#1e293b' : 'var(--text-secondary)',
                    boxShadow: mode === 'signin' ? '0 2px 6px rgba(0,0,0,0.08)' : 'none',
                    transition: 'all 0.2s',
                  }}
                >
                  Sign In
                </button>
                <button
                  type="button"
                  onClick={() => { setMode('signup'); setError(null); }}
                  style={{
                    flex: 1,
                    padding: '9px 12px',
                    borderRadius: 8,
                    border: 'none',
                    fontWeight: 600,
                    fontSize: 13,
                    cursor: 'pointer',
                    background: mode === 'signup' ? '#ffffff' : 'transparent',
                    color: mode === 'signup' ? '#1e293b' : 'var(--text-secondary)',
                    boxShadow: mode === 'signup' ? '0 2px 6px rgba(0,0,0,0.08)' : 'none',
                    transition: 'all 0.2s',
                  }}
                >
                  Sign Up
                </button>
              </div>

            <h1 className="signin-main-heading" style={{ marginBottom: 16 }}>
              {mode === 'signup' ? 'Create Account' : 'Sign In'}
            </h1>

            {/* Role Selection Row */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <label style={{ fontSize: 11, fontWeight: 700, color: '#475569', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                  {mode === 'signin' ? 'Role Quick-Select:' : 'Account Role:'}
                </label>
                {mode === 'signin' && (
                  <span style={{ fontSize: 11, color: '#4f46e5', fontWeight: 600 }}>Demo accounts</span>
                )}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
                {(['Creator', 'Reviewer', 'Administrator'] as const).map((r) => {
                  const isSelected = mode === 'signin' ? selectedRole === r : signupRole === r;
                  return (
                    <button
                      key={r}
                      type="button"
                      onClick={() => {
                        if (mode === 'signin') {
                          handleSelectRole(r);
                        } else {
                          setSignupRole(r);
                        }
                      }}
                      style={{
                        padding: '8px 4px',
                        borderRadius: 8,
                        border: isSelected ? '1.5px solid #4f46e5' : '1px solid rgba(0,0,0,0.1)',
                        background: isSelected ? '#4f46e5' : 'rgba(255,255,255,0.7)',
                        color: isSelected ? '#ffffff' : '#1e293b',
                        fontWeight: 700,
                        fontSize: 12,
                        cursor: 'pointer',
                        transition: 'all 0.15s',
                        textAlign: 'center',
                      }}
                    >
                      {r}
                    </button>
                  );
                })}
              </div>
              {mode === 'signup' && signupRole !== 'Creator' && (
                <div style={{ fontSize: 11.5, color: '#92400e', marginTop: 8, padding: '8px 10px', background: 'rgba(254,243,199,0.9)', borderRadius: 8, border: '1px solid rgba(245,158,11,0.3)', lineHeight: 1.4 }}>
                  {signupRole} privileges are managed. To test as a <strong>{signupRole}</strong>, switch to the <strong>Sign In</strong> tab and select <strong>{signupRole}</strong> to authenticate immediately.
                </div>
              )}
            </div>

            {/* In Sign Up mode: First Name & Last Name */}
            {mode === 'signup' && (
              <>
                <fieldset className="legend-fieldset" style={{ marginBottom: 14 }}>
                  <legend className="legend-tag">First Name</legend>
                  <input
                    type="text"
                    className="legend-input"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="First Name"
                    required
                  />
                </fieldset>

                <fieldset className="legend-fieldset" style={{ marginBottom: 14 }}>
                  <legend className="legend-tag">Last Name</legend>
                  <input
                    type="text"
                    className="legend-input"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Last Name"
                    required
                  />
                </fieldset>
              </>
            )}

            {/* Email Field */}
            <fieldset className="legend-fieldset" style={{ marginBottom: 14 }}>
              <legend className="legend-tag">Email</legend>
              <input
                type="email"
                className="legend-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Work Email"
                required
                autoComplete="email"
              />
            </fieldset>

            {/* Password Field with Show/Hide */}
            <fieldset className="legend-fieldset password-fieldset" style={{ marginBottom: 16 }}>
              <legend className="legend-tag">Password</legend>
              <div className="password-input-wrap">
                <input
                  type={showPassword ? 'text' : 'password'}
                  className="legend-input password-inner-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={mode === 'signup' ? 'Password (min. 8 characters)' : 'Password'}
                  required
                />
                <button
                  type="button"
                  className="password-toggle-icon"
                  onClick={() => setShowPassword(!showPassword)}
                  title={showPassword ? 'Hide password' : 'Show password'}
                  style={{ fontSize: 11, fontWeight: 700, padding: '2px 6px' }}
                >
                  {showPassword ? 'Hide' : 'Show'}
                </button>
              </div>
            </fieldset>

            {/* Action Button */}
            <button
              type="submit"
              className="create-account-or-signin-btn"
              disabled={submitting}
              style={{ marginTop: 4 }}
            >
              {submitting
                ? (mode === 'signup' ? 'Creating Account…' : 'Authenticating…')
                : (mode === 'signup' ? 'Create Account & Sign In   →' : 'Sign In   →')}
            </button>

            {/* Mode Switcher Footer */}
            <div className="signin-support-footer" style={{ marginTop: 18 }}>
              {mode === 'signin' ? (
                <>
                  <span>Don't have an account? </span>
                  <button
                    type="button"
                    className="contact-support-link"
                    onClick={() => {
                      setMode('signup');
                      setError(null);
                    }}
                    style={{ fontWeight: 700, color: '#4f46e5' }}
                  >
                    Sign Up
                  </button>
                </>
              ) : (
                <>
                  <span>Already have an account? </span>
                  <button
                    type="button"
                    className="contact-support-link"
                    onClick={() => { setMode('signin'); setError(null); }}
                    style={{ fontWeight: 700, color: '#4f46e5' }}
                  >
                    Sign In
                  </button>
                </>
              )}
            </div>
          </form>
        </TiltCard>
        </div>
      </div>

      {/* Contact Support Modal */}
      {showSupportModal && (
        <div className="modal-overlay" onClick={() => setShowSupportModal(false)}>
          <div className="support-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="support-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, borderRadius: 6, background: '#4f46e5', color: '#fff', fontSize: 12, fontWeight: 800 }}>BS</span>
                <h3 style={{ fontSize: 18, fontWeight: 800, color: '#0f172a' }}>
                  Workspace Access &amp; Support
                </h3>
              </div>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setShowSupportModal(false)}
              >
                ✕
              </button>
            </div>
            <div className="support-modal-body">
              <p style={{ fontSize: 14, color: '#334155', lineHeight: 1.6, marginBottom: 16 }}>
                BrandShield AI uses <strong>Managed Role-Based Access</strong>. New registrations receive
                Creator privileges. Reviewer and Administrator roles are assigned by workspace administrators.
              </p>
              <div className="support-box">
                <div style={{ fontWeight: 700, color: '#0f172a', marginBottom: 4 }}>
                  Contact Administrator
                </div>
                <div style={{ fontSize: 13, color: '#475569' }}>
                  Reach your organization administrator or support at:{' '}
                  <a href="mailto:support@brandshield.ai" style={{ color: '#4f46e5', fontWeight: 600 }}>
                    support@brandshield.ai
                  </a>
                </div>
              </div>
            </div>
            <div className="support-modal-footer">
              <button
                type="button"
                className="modal-dismiss-btn"
                onClick={() => setShowSupportModal(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

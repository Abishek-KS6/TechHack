import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const navItems = [
  { path: '/dashboard', icon: '⬡', label: 'Dashboard' },
  { path: '/analysis', icon: '◈', label: 'Brand Analysis' },
  { path: '/submissions', icon: '≡', label: 'Submissions' },
  { path: '/guidelines', icon: '§', label: 'Guidelines & Facts' },
  { path: '/governance', icon: '▲', label: 'Governance' },
  { path: '/audit', icon: '◉', label: 'Audit Log' },
];

const bottomItems = [
  { path: '/settings', icon: '◎', label: 'Settings' },
];

export default function Sidebar() {
  const { user, role, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isCreator = role === 'CREATOR';
  const isReviewer = role === 'REVIEWER';

  // Role-based navigation visibility
  const visibleNavItems = navItems.filter((item) => {
    if (isCreator && (item.path === '/governance' || item.path === '/audit')) {
      return false;
    }
    if (isReviewer && item.path === '/audit') {
      return false;
    }
    return true;
  });

  return (
    <aside className={`sidebar ${isCollapsed ? 'sidebar-collapsed' : ''}`}>
      {/* ── Sidebar Header / Logo with Collapse Toggle ── */}
      <div className="sidebar-logo">
        <div
          className="logo-icon-link"
          onClick={() => navigate('/')}
          style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12 }}
          title="Back to Landing Page"
        >
          <div className="logo-icon" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, borderRadius: 6, background: '#4f46e5', color: '#fff', fontWeight: 800, fontSize: 13 }}>
            BS
          </div>
          {!isCollapsed && (
            <div>
              <div className="logo-text">BrandShield</div>
              <div className="logo-sub">AI Content Governance</div>
            </div>
          )}
        </div>

        {/* Toggle Collapse Button */}
        <button
          type="button"
          className="sidebar-collapse-toggle"
          onClick={() => {
            const nextState = !isCollapsed;
            setIsCollapsed(nextState);
            const mainEl = document.querySelector('.main');
            if (mainEl) {
              if (nextState) {
                mainEl.classList.add('main-collapsed');
              } else {
                mainEl.classList.remove('main-collapsed');
              }
            }
          }}
          title={isCollapsed ? 'Expand sidebar (show labels)' : 'Collapse to icons-only sidebar'}
        >
          {isCollapsed ? '⇥' : '⇤'}
        </button>
      </div>

      {/* ── Navigation Items with Floating Glassmorphic Tooltip ── */}
      <nav className="nav">
        {!isCollapsed && <div className="nav-section-label">Navigation</div>}
        {visibleNavItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <button
              key={item.path}
              type="button"
              className={`nav-item ${isActive ? 'active' : ''}`}
              onClick={() => navigate(item.path)}
            >
              <span className="nav-icon">{item.icon}</span>
              {!isCollapsed && <span className="nav-label">{item.label}</span>}

              {/* Floating Glassmorphic Tooltip Card (always visible on hover in icons-only mode) */}
              <div className="floating-glass-tooltip" role="tooltip">
                <span className="tooltip-text">{item.label}</span>
                <span className="tooltip-arrow" />
              </div>
            </button>
          );
        })}

        {!isCollapsed && <div className="nav-section-label" style={{ marginTop: 16 }}>System</div>}
        {bottomItems.map((item) => {
          const isActive = location.pathname === item.path;
          return (
            <button
              key={item.path}
              type="button"
              className={`nav-item ${isActive ? 'active' : ''}`}
              onClick={() => navigate(item.path)}
            >
              <span className="nav-icon">{item.icon}</span>
              {!isCollapsed && <span className="nav-label">{item.label}</span>}

              {/* Floating Glassmorphic Tooltip Card */}
              <div className="floating-glass-tooltip" role="tooltip">
                <span className="tooltip-text">{item.label}</span>
                <span className="tooltip-arrow" />
              </div>
            </button>
          );
        })}
      </nav>

      {/* ── Sidebar Footer / User Profile ── */}
      <div className="sidebar-footer">
        <div
          className="user-pill"
          onClick={handleLogout}
          title={isCollapsed ? `${user?.full_name || 'User'} (${role}) - Click to logout` : 'Click to log out'}
        >
          <div className="avatar">{user?.full_name?.charAt(0) || 'U'}</div>
          {!isCollapsed && (
            <div style={{ overflow: 'hidden', flex: 1 }}>
              <div className="user-name" style={{ whiteSpace: 'nowrap', textOverflow: 'ellipsis', overflow: 'hidden' }}>
                {user?.full_name || 'Loading…'}
              </div>
              <div className="user-role" style={{ fontSize: 10, color: 'var(--brand-300)' }}>
                {role} · Click to logout
              </div>
            </div>
          )}

          {isCollapsed && (
            <div className="floating-glass-tooltip" role="tooltip">
              <span className="tooltip-text">Log Out ({role})</span>
              <span className="tooltip-arrow" />
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

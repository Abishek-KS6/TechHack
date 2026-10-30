import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { apiClient } from '../api/client';

interface TopbarProps {
  title: string;
}

export default function Topbar({ title }: TopbarProps) {
  const { user, role } = useAuth();
  const [apiHealthy, setApiHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    let mounted = true;
    const checkHealth = async () => {
      try {
        await apiClient.get('/health', { timeout: 4000 });
        if (mounted) setApiHealthy(true);
      } catch {
        // also try root health or system
        try {
          await apiClient.get('/system/diagnostics', { timeout: 4000 });
          if (mounted) setApiHealthy(true);
        } catch {
          if (mounted) setApiHealthy(false);
        }
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="topbar">
      <h1 className="topbar-title">{title}</h1>

      <div className="topbar-right" style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        {/* API Liveness Status */}
        {apiHealthy === true && (
          <span className="badge badge-success" title="FastAPI backend connected and responding">● Live Backend</span>
        )}
        {apiHealthy === false && (
          <span className="badge badge-danger" title="Backend unreachable at http://localhost:8000">API Offline</span>
        )}
        {apiHealthy === null && (
          <span className="badge badge-info">Checking…</span>
        )}

        {/* User Avatar */}
        <div
          className="avatar"
          style={{ width: 34, height: 34, fontSize: 13, cursor: 'pointer', background: 'var(--brand-600)' }}
          title={`${user?.full_name || 'User'} (${user?.email || ''}) · Role: ${role || 'User'}`}
        >
          {user?.full_name?.charAt(0) || 'U'}
        </div>
      </div>
    </header>
  );
}

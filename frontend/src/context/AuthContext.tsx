import React, { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi, brandsApi, type CurrentUser } from '../api/client';

interface AuthContextType {
  user: CurrentUser | null;
  token: string | null;
  role: 'CREATOR' | 'REVIEWER' | 'ADMINISTRATOR';
  activeBrandProfileId: string;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (data: { email: string; password: string; full_name: string; role?: 'CREATOR' | 'REVIEWER' | 'ADMINISTRATOR' }) => Promise<void>;
  switchRole: (role: 'CREATOR' | 'REVIEWER' | 'ADMINISTRATOR') => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const ROLE_EMAILS: Record<'CREATOR' | 'REVIEWER' | 'ADMINISTRATOR', string> = {
  CREATOR: 'creator@acme.com',
  REVIEWER: 'reviewer@acme.com',
  ADMINISTRATOR: 'admin@acme.com',
};

// Seeded Acme FinTech Global Profile ID (fallback)
const DEFAULT_BRAND_PROFILE_ID = 'ad10bed0-7a4b-421e-ace0-b93000e5e6fc';

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('brandshield_token'));
  const [activeBrandProfileId, setActiveBrandProfileId] = useState<string>(DEFAULT_BRAND_PROFILE_ID);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refreshUser = async () => {
    try {
      const me = await authApi.getMe();
      setUser(me);
    } catch {
      setUser(null);
      setToken(null);
      localStorage.removeItem('brandshield_token');
    }
  };

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const data = await authApi.login(email, password);
      setToken(data.access_token);
      const me = await authApi.getMe();
      setUser(me);
      // Load brand profile
      try {
        const active = await brandsApi.getActiveProfile();
        if (active?.id) {
          setActiveBrandProfileId(active.id);
        } else {
          const profiles = await brandsApi.listProfiles();
          if (profiles.length > 0) {
            setActiveBrandProfileId(profiles[0].id);
          }
        }
      } catch {
        // keep default
      }
    } finally {
      setIsLoading(false);
    }
  };

  const signup = async (regData: { email: string; password: string; full_name: string; role?: 'CREATOR' | 'REVIEWER' | 'ADMINISTRATOR' }) => {
    setIsLoading(true);
    try {
      const data = await authApi.signup(regData);
      setToken(data.access_token);
      const me = await authApi.getMe();
      setUser(me);
      try {
        const active = await brandsApi.getActiveProfile();
        if (active?.id) {
          setActiveBrandProfileId(active.id);
        } else {
          const profiles = await brandsApi.listProfiles();
          if (profiles.length > 0) {
            setActiveBrandProfileId(profiles[0].id);
          }
        }
      } catch {
        // keep default
      }
    } finally {
      setIsLoading(false);
    }
  };

  const switchRole = async (targetRole: 'CREATOR' | 'REVIEWER' | 'ADMINISTRATOR') => {
    const email = ROLE_EMAILS[targetRole];
    await login(email, 'DemoSecure2026!');
  };

  const logout = () => {
    authApi.logout();
    setUser(null);
    setToken(null);
  };

  useEffect(() => {
    const init = async () => {
      const storedToken = localStorage.getItem('brandshield_token');
      if (storedToken) {
        try {
          const me = await authApi.getMe();
          setUser(me);
          try {
            const profiles = await brandsApi.listProfiles();
            if (profiles.length > 0) setActiveBrandProfileId(profiles[0].id);
          } catch { /* keep default */ }
        } catch {
          // Token invalid — user must log in
          localStorage.removeItem('brandshield_token');
          setToken(null);
        }
      }
      setIsLoading(false);
    };
    init();
  }, []);

  const role = user?.role || 'CREATOR';

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        role,
        activeBrandProfileId,
        isLoading,
        login,
        signup,
        switchRole,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

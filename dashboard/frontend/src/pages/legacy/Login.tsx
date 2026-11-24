/**
 * AirFed Dashboard - Login Page
 * Authentication entry point
 */

import { FC, memo } from 'react';
import { Navigate } from 'react-router-dom';
import { useDashboardStore } from '@/stores/dashboard';

export const LoginPage: FC = memo(() => {
  const { setActivePage } = useDashboardStore();

  // Simple login handler - in production this would authenticate with backend
  const handleLogin = () => {
    setActivePage('/overview');
  };

  // Redirect if already logged in (check localStorage)
  if (localStorage.getItem('airfed-auth')) {
    return <Navigate to="/overview" replace />;
  }

  return (
    <div className="flex h-screen w-full items-center justify-center bg-background">
      <div className="w-full max-w-md space-y-8 rounded-xl border border-border bg-background p-8 shadow-lg">
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-foreground">AirFed Dashboard</h1>
          <p className="text-muted-foreground">
            Federated Learning Experiment Tracker
          </p>
        </div>
        <button
          onClick={handleLogin}
          className="w-full rounded-lg bg-airfed-500 py-2.5 text-white transition-colors hover:bg-airfed-600"
        >
          Sign In
        </button>
      </div>
    </div>
  );
});

LoginPage.displayName = 'LoginPage';
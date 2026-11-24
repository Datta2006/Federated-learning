/**
 * AirFed Dashboard - 404 Page
 * Not Found error page
 */

import { FC, memo } from 'react';
import { Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';

export const NotFoundPage: FC = memo(() => {
  return (
    <div className="flex h-screen w-full items-center justify-center bg-background">
      <div className="text-center space-y-6 max-w-md mx-auto px-4">
        <div className="flex justify-center">
          <AlertCircle className="h-12 w-12 text-muted-foreground" />
        </div>
        <h1 className="text-3xl font-bold text-foreground">Page Not Found</h1>
        <p className="text-muted-foreground">
          The page you are looking for does not exist or has been moved.
        </p>
        <Link
          to="/overview"
          className="inline-flex items-center justify-center rounded-lg bg-airfed-500 px-4 py-2 text-white transition-colors hover:bg-airfed-600"
        >
          Go to Overview
        </Link>
      </div>
    </div>
  );
});

NotFoundPage.displayName = 'NotFoundPage';
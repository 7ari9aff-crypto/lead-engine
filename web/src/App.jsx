import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClientInstance } from '@/lib/query-client'
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import PageNotFound from './lib/PageNotFound';
import { AuthProvider, useAuth } from '@/lib/AuthContext';
import UserNotRegisteredError from '@/components/UserNotRegisteredError';
import ScrollToTop from './components/ScrollToTop';
import { LeadEngineProvider } from '@/lib/leadEngine/store';
import { AppShell } from '@/components/leadEngine/AppShell';
import CommandCenter from '@/pages/leadEngine/CommandCenter';
import Chat from '@/pages/leadEngine/Chat';
import ResearchJobs from '@/pages/leadEngine/ResearchJobs';
import JobDetail from '@/pages/leadEngine/JobDetail';
import ICP from '@/pages/leadEngine/ICP';
import Leads from '@/pages/leadEngine/Leads';
import LeadDetail from '@/pages/leadEngine/LeadDetail';
import ReviewQueue from '@/pages/leadEngine/ReviewQueue';
import Analytics from '@/pages/leadEngine/Analytics';
import Activity from '@/pages/leadEngine/Activity';
import Providers from '@/pages/leadEngine/Providers';
import Credentials from '@/pages/leadEngine/Credentials';
import Integrations from '@/pages/leadEngine/Integrations';
import Agents from '@/pages/leadEngine/Agents';
import Settings from '@/pages/leadEngine/Settings';
// Add page imports here

const AuthenticatedApp = () => {
  const { isLoadingAuth, isLoadingPublicSettings, authError, navigateToLogin } = useAuth();

  // Show loading spinner while checking app public settings or auth
  if (isLoadingPublicSettings || isLoadingAuth) {
    return (
      <div className="fixed inset-0 flex items-center justify-center">
        <div className="w-8 h-8 border-4 border-border border-t-primary rounded-full animate-spin"></div>
      </div>
    );
  }

  // Handle authentication errors
  if (authError) {
    if (authError.type === 'user_not_registered') {
      return <UserNotRegisteredError />;
    } else if (authError.type === 'auth_required') {
      // Redirect to login automatically
      navigateToLogin();
      return null;
    }
  }

  // Render the main app
  return (
    <LeadEngineProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<CommandCenter />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/jobs" element={<ResearchJobs />} />
          <Route path="/jobs/:id" element={<JobDetail />} />
          <Route path="/icp" element={<ICP />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/leads/:id" element={<LeadDetail />} />
          <Route path="/review" element={<ReviewQueue />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/providers" element={<Providers />} />
          <Route path="/credentials" element={<Credentials />} />
          <Route path="/integrations" element={<Integrations />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<PageNotFound />} />
      </Routes>
    </LeadEngineProvider>
  );
};


function App() {

  return (
    <AuthProvider>
      <QueryClientProvider client={queryClientInstance}>
        <Router>
          <ScrollToTop />
          <AuthenticatedApp />
        </Router>
        <Toaster />
      </QueryClientProvider>
    </AuthProvider>
  )
}

export default App
import { useEffect, useState, Component, type ReactNode } from "react";
import { Route, Switch, Redirect } from "wouter";
import { useLocation } from "wouter";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useUI } from "@/hooks/useTheme";
import { OverviewPage } from "@/pages/Overview";
import { ChatPage } from "@/pages/Chat";
import { KeysPage } from "@/pages/Keys";
import { JobsPage } from "@/pages/Jobs";
import { LeadsPage } from "@/pages/Leads";
import { VerifyPage } from "@/pages/Verify";
import { ConfigPage } from "@/pages/Config";
import { IntegrationsPage } from "@/pages/Integrations";
import { AgentsPage } from "@/pages/Agents";
import { CampaignDetailsPage } from "@/pages/CampaignDetails";
import { LandingPage } from "@/pages/Landing";
import { PricingPage } from "@/pages/Pricing";
import { LoginPage, SignupPage } from "@/pages/Auth";
import { ActivityPage } from "@/pages/Activity";
import { Link } from "wouter";
import { Button } from "@/components/ui/Button";
import { AlertTriangle, Home, RotateCcw, Zap } from "lucide-react";
import { Footer } from "@/components/layout/Footer";
import { BackToTop } from "@/components/layout/BackToTop";
import { apiGet } from "@/lib/api";

export default function App() {
  const { theme } = useUI();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
  }, [theme]);

  return (
    <ErrorBoundary>
      <Switch>
        {/* Public pages — full-viewport, no sidebar */}
        <Route path="/login" component={LoginPage} />
        <Route path="/signup" component={SignupPage} />
        <Route path="/pricing" component={PricingPage} />
        <Route path="/welcome" component={LandingPage} />

        {/* Root: dashboard for signed-in users, landing for visitors */}
        <Route path="/">
          <RootGate />
        </Route>

        {/* Dashboard layout */}
        <Route>
          <DashboardLayout>
            <Switch>
              <Route path="/chat" component={ChatPage} />
              <Route path="/keys" component={KeysPage} />
              <Route path="/providers" component={() => <Redirect to="/keys" />} />
              <Route path="/jobs" component={JobsPage} />
              <Route path="/jobs/:id" component={CampaignDetailsPage} />
              <Route path="/leads" component={LeadsPage} />
              <Route path="/verify" component={VerifyPage} />
              <Route path="/config" component={ConfigPage} />
              <Route path="/integrations" component={IntegrationsPage} />
              <Route path="/agents" component={AgentsPage} />
              <Route path="/activity" component={ActivityPage} />
              <Route>
                <NotFound />
              </Route>
            </Switch>
          </DashboardLayout>
        </Route>
      </Switch>
    </ErrorBoundary>
  );
}

function RootGate() {
  const [state, setState] = useState<"loading" | "authed" | "guest">("loading");

  useEffect(() => {
    apiGet.authSession()
      .then((r) => setState(r.authenticated ? "authed" : "guest"))
      .catch(() => setState("guest"));
  }, []);

  if (state === "loading") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-[var(--bg)]">
        <span className="h-12 w-12 rounded-2xl bg-[image:var(--gradient)] flex items-center justify-center shadow-[var(--shadow-lg)]">
          <Zap className="h-5 w-5 text-white" />
        </span>
        <span className="text-[12px] text-[var(--fg-muted)]">جارٍ التحقق من جلستك…</span>
      </div>
    );
  }
  if (state === "guest") return <LandingPage />;
  return (
    <DashboardLayout>
      <OverviewPage />
    </DashboardLayout>
  );
}

function DashboardLayout({ children }: { children: ReactNode }) {
  const [location] = useLocation();
  // Immersive pages (chat) take the full viewport height and scroll
  // internally — no page chrome below the topbar.
  const immersive = location === "/chat";
  return (
    <div className="flex h-screen overflow-hidden" dir="ltr">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-screen" dir="rtl">
        <Topbar />
        {immersive ? (
          <main className="flex-1 min-h-0 animate-fade-in">
            <AuthGate>{children}</AuthGate>
          </main>
        ) : (
          <>
            <main className="flex-1 overflow-y-auto px-4 sm:px-6 lg:px-10 py-6 max-w-[1500px] w-full mx-auto animate-fade-in">
              <AuthGate>{children}</AuthGate>
            </main>
            <Footer />
          </>
        )}
      </div>
    </div>
  );
}

function AuthGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    apiGet.authSession().then((result) => {
      setAuthenticated(result.authenticated);
      setReady(true);
    }).catch(() => setReady(true));
  }, []);

  if (!ready) return <div className="py-20 text-center text-sm text-[var(--fg-muted)]">جارٍ التحقق من الجلسة…</div>;
  if (authenticated) return <>{children}</>;
  // Not signed in → the dedicated login page (never raw dashboard content).
  return <Redirect to="/login" />;
}

function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="text-7xl font-bold gradient-text mb-4">404</div>
      <h2 className="text-xl font-semibold mb-2">الصفحة غير موجودة</h2>
      <p className="text-sm text-[var(--fg-muted)] mb-6 max-w-sm">
        الصفحة اللي تدوّر عليها مش موجودة. ارجع للرئيسية أو جرّب اللوحة.
      </p>
      <div className="flex gap-2">
        <Button variant="primary" asChild>
          <Link href="/">
            <Home className="h-4 w-4" />
            الرئيسية
          </Link>
        </Button>
        <Button variant="outline" asChild>
          <Link href="/welcome">الصفحة الرئيسية</Link>
        </Button>
      </div>
    </div>
  );
}

// === Error Boundary ===
class ErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    // eslint-disable-next-line no-console
    console.error("App error:", error, info);
    // expose the stack to the DOM so headless diagnostics can read it
    document.body.setAttribute("data-crash", `${error?.stack || error?.message || String(error)}`);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center p-4">
          <div className="max-w-md w-full text-center">
            <div className="h-16 w-16 rounded-full bg-[var(--danger)]/10 text-[var(--danger)] flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="h-8 w-8" />
            </div>
            <h1 className="text-2xl font-bold mb-2">حدث خطأ غير متوقع</h1>
            <p className="text-sm text-[var(--fg-muted)] mb-6">
              حصل خطأ في التطبيق — جرّب تحدّث الصفحة، ولو تكرر جرّب من تاني بعد لحظات.
            </p>
            <div className="flex gap-2 justify-center">
              <Button
                variant="primary"
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                  window.location.reload();
                }}
              >
                <RotateCcw className="h-4 w-4" />
                تحديث
              </Button>
              <Button variant="outline" asChild>
                <Link href="/">
                  <Home className="h-4 w-4" />
                  الرئيسية
                </Link>
              </Button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

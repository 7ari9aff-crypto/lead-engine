import { useEffect, useState, Component, type ReactNode } from "react";
import { Route, Switch, Redirect } from "wouter";
import { useLocation } from "wouter";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useUI } from "@/hooks/useTheme";
import { OverviewPage } from "@/pages/Overview";
import { CommandCenterPage } from "@/pages/CommandCenter";
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
import { ResearchPage } from "@/pages/Research";
import { ReviewPage } from "@/pages/Review";
import { IcpPage } from "@/pages/Icp";
import { DocsPage } from "@/pages/Docs";
import { Link } from "wouter";
import { Button } from "@/components/ui/Button";
import { AlertTriangle, Home, RotateCcw, Zap } from "lucide-react";
import { Footer } from "@/components/layout/Footer";
import { BackToTop } from "@/components/layout/BackToTop";
import { apiGet } from "@/lib/api";
import { supabase, supabaseConfigured } from "@/lib/supabase";

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
              <Route path="/analytics" component={OverviewPage} />
              <Route path="/research" component={ResearchPage} />
              <Route path="/review" component={ReviewPage} />
              <Route path="/icp" component={IcpPage} />
              <Route path="/docs" component={DocsPage} />
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
    // Use Supabase client-side session first — avoids race condition where
    // navigate("/") triggers RootGate before the Bearer token is ready.
    if (supabaseConfigured) {
      supabase.auth.getSession().then(({ data }) => {
        setState(data.session ? "authed" : "guest");
      }).catch(() => setState("guest"));
      const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
        setState(session ? "authed" : "guest");
      });
      return () => { listener.subscription.unsubscribe(); };
    } else {
      // Fallback for password/open modes — ask backend
      apiGet.authSession()
        .then((r) => setState(r.authenticated ? "authed" : "guest"))
        .catch(() => setState("guest"));
    }
  }, []);

  if (state === "loading") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-[var(--bg)]">
        <span className="h-12 w-12 rounded-2xl bg-[image:var(--gradient)] flex items-center justify-center shadow-[var(--shadow-lg)]">
          <Zap className="h-5 w-5 text-white" />
        </span>
        <span className="text-[12px] text-[var(--fg-muted)]">جارٍّ التحقق من الجلسة...</span>
      </div>
    );
  }
  // Guest: redirect to login (not Landing) so user knows they must sign in
  if (state === "guest") return <Redirect to="/login" />;
  return (
    <DashboardLayout>
      <CommandCenterPage />
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
            <BackToTop />
          </>
        )}
      </div>
    </div>
  );
}

function AuthGate({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [mode, setMode] = useState<string>("");

  useEffect(() => {
    if (supabaseConfigured) {
      // Optimistically assume authed (RootGate already checked) but verify
      supabase.auth.getSession().then(({ data }) => {
        setAuthenticated(Boolean(data.session));
        setMode("supabase");
      }).catch(() => setAuthenticated(false));
      const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => {
        setAuthenticated(Boolean(session));
        setMode("supabase");
      });
      return () => { listener.subscription.unsubscribe(); };
    } else {
      apiGet.authSession().then((result) => {
        setAuthenticated(result.authenticated);
        setMode(result.mode || "");
      }).catch(() => setAuthenticated(false));
    }
  }, []);

  // Still checking — show children optimistically to avoid flash
  // (RootGate already guarded; if not authed, onAuthStateChange will catch it)
  if (authenticated === null) return <>{children}</>;
  if (authenticated) return <>{children}</>;
  if (mode === "closed") {
    return (
      <div className="max-w-lg mx-auto mt-10 rounded-2xl border border-[var(--warn)]/40 bg-[color-mix(in_srgb,var(--warn)_8%,transparent)] p-6 text-center">
        <h2 className="text-lg font-bold mb-2">المنصة مغلقة — مطلوب حساب للدخول</h2>
        <p className="text-[13px] text-[var(--fg-muted)] leading-6">
          تواصل مع المسؤول للحصول على صلاحيات الدخول.
        </p>
      </div>
    );
  }
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

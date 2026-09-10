import { useEffect, Component, type ReactNode } from "react";
import { Route, Switch, Redirect } from "wouter";
import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";
import { useUI } from "@/hooks/useTheme";
import { OverviewPage } from "@/pages/Overview";
import { ChatPage } from "@/pages/Chat";
import { KeysPage } from "@/pages/Keys";
import { ProvidersPage } from "@/pages/Providers";
import { JobsPage } from "@/pages/Jobs";
import { LeadsPage } from "@/pages/Leads";
import { VerifyPage } from "@/pages/Verify";
import { ConfigPage } from "@/pages/Config";
import { WelcomePage } from "@/pages/Welcome";
import { PricingPage } from "@/pages/Pricing";
import { Link } from "wouter";
import { Button } from "@/components/ui/Button";
import { AlertTriangle, Home, RotateCcw } from "lucide-react";

export default function App() {
  const { theme } = useUI();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
  }, [theme]);

  return (
    <ErrorBoundary>
      <Switch>
        {/* Public marketing pages — no sidebar */}
        <Route path="/welcome" component={WelcomePage} />
        <Route path="/pricing" component={PricingPage} />

        {/* Dashboard layout with sidebar */}
        <Route>
          <DashboardLayout>
            <Switch>
              <Route path="/" component={OverviewPage} />
              <Route path="/chat" component={ChatPage} />
              <Route path="/keys" component={KeysPage} />
              <Route path="/providers" component={ProvidersPage} />
              <Route path="/jobs" component={JobsPage} />
              <Route path="/leads" component={LeadsPage} />
              <Route path="/verify" component={VerifyPage} />
              <Route path="/config" component={ConfigPage} />
              <Route path="/docs">
                <NotFound />
              </Route>
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

function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen" dir="rtl">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar />
        <main className="flex-1 px-4 sm:px-6 lg:px-8 py-6 max-w-[1600px] w-full mx-auto animate-fade-in">
          {children}
        </main>
      </div>
    </div>
  );
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
          <Link href="/welcome">صفحة الترحيب</Link>
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
              {this.state.error?.message || "حصل خطأ في التطبيق. حاول تحدّث الصفحة."}
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

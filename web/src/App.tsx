import { useEffect } from "react";
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

export default function App() {
  const { theme } = useUI();

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.classList.toggle("light", theme === "light");
  }, [theme]);

  return (
    <div className="flex min-h-screen" dir="rtl">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar />
        <main className="flex-1 px-4 sm:px-6 lg:px-8 py-6 max-w-[1600px] w-full mx-auto animate-fade-in">
          <Switch>
            <Route path="/" component={OverviewPage} />
            <Route path="/chat" component={ChatPage} />
            <Route path="/keys" component={KeysPage} />
            <Route path="/providers" component={ProvidersPage} />
            <Route path="/jobs" component={JobsPage} />
            <Route path="/leads" component={LeadsPage} />
            <Route path="/verify" component={VerifyPage} />
            <Route path="/config" component={ConfigPage} />
            <Route>
              <Redirect to="/" />
            </Route>
          </Switch>
        </main>
      </div>
    </div>
  );
}

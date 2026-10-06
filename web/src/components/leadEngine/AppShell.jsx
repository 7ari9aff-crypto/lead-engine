import React, { useState } from "react";
import { Outlet } from "react-router-dom";
import Layout from "./Layout";
import { Topbar } from "./Topbar";

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const toggleMobile = () => window.dispatchEvent(new Event("leadengine:toggleSidebar"));
  return (
    <Layout collapsed={collapsed} onToggleCollapse={() => setCollapsed((c) => !c)}>
      <Topbar onMenu={toggleMobile} />
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        <Outlet />
      </main>
    </Layout>
  );
}
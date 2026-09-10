import { create } from "zustand";
import { persist } from "zustand/middleware";

type Theme = "dark" | "light";
type Sidebar = "expanded" | "collapsed";

interface UIState {
  theme: Theme;
  sidebar: Sidebar;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  setSidebar: (s: Sidebar) => void;
  toggleSidebar: () => void;
}

export const useUI = create<UIState>()(
  persist(
    (set, get) => ({
      theme: "dark",
      sidebar: "expanded",
      setTheme: (t) => {
        set({ theme: t });
        document.documentElement.classList.toggle("dark", t === "dark");
        document.documentElement.classList.toggle("light", t === "light");
      },
      toggleTheme: () => {
        const t = get().theme === "dark" ? "light" : "dark";
        get().setTheme(t);
      },
      setSidebar: (s) => set({ sidebar: s }),
      toggleSidebar: () => set({ sidebar: get().sidebar === "expanded" ? "collapsed" : "expanded" }),
    }),
    {
      name: "lead-engine-ui",
      onRehydrateStorage: () => (state) => {
        if (state) {
          document.documentElement.classList.toggle("dark", state.theme === "dark");
          document.documentElement.classList.toggle("light", state.theme === "light");
        }
      },
    }
  )
);

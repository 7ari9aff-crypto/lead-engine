import { Sun, Moon } from "lucide-react";
import { useUI } from "@/hooks/useTheme";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useUI();
  return (
    <button
      onClick={toggleTheme}
      title={theme === "dark" ? "وضع نهاري" : "وضع ليلي"}
      aria-label="تبديل الثيم"
      className={`h-9 w-9 rounded-lg flex items-center justify-center text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors ${className}`}
    >
      {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

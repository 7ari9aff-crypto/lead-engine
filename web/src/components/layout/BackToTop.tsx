import { useEffect, useState } from "react";
import { ArrowUp } from "lucide-react";

export function BackToTop() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const onScroll = () => setShow(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <button
      onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      className={`fixed bottom-6 end-6 z-40 h-10 w-10 rounded-full bg-[var(--accent)] text-white shadow-lg flex items-center justify-center transition-all duration-300 hover:bg-[var(--accent-hover)] active:scale-95 ${
        show ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4 pointer-events-none"
      }`}
      aria-label="الرجوع للأعلى"
    >
      <ArrowUp className="h-4 w-4" />
    </button>
  );
}

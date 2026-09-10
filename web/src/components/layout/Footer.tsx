import { Link } from "wouter";
import { Zap, Github, Twitter, Linkedin, Heart, ExternalLink } from "lucide-react";

export function Footer() {
  return (
    <footer className="mt-auto border-t border-[var(--border-soft)] py-4 px-4 sm:px-6 lg:px-8">
      <div className="max-w-[1600px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-[var(--fg-soft)]">
        <div className="flex items-center gap-2">
          <div className="h-5 w-5 rounded bg-[image:var(--gradient)] flex items-center justify-center">
            <Zap className="h-3 w-3 text-white" />
          </div>
          <span className="font-medium gradient-text">محرّك الـLeads</span>
          <span className="text-[var(--fg-soft)]">v1.0</span>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/welcome" className="hover:text-[var(--fg-muted)] transition-colors">
            الرئيسية
          </Link>
          <Link href="/pricing" className="hover:text-[var(--fg-muted)] transition-colors">
            الأسعار
          </Link>
          <Link href="/docs" className="hover:text-[var(--fg-muted)] transition-colors">
            التوثيق
          </Link>
          <a
            href="https://github.com/7ari9aff-crypto/lead-engine"
            target="_blank"
            rel="noopener"
            className="hover:text-[var(--fg-muted)] transition-colors flex items-center gap-1"
          >
            GitHub <ExternalLink className="h-3 w-3" />
          </a>
        </div>

        <div className="flex items-center gap-3">
          <a href="#" className="hover:text-[var(--fg-muted)]" aria-label="GitHub"><Github className="h-3.5 w-3.5" /></a>
          <a href="#" className="hover:text-[var(--fg-muted)]" aria-label="Twitter"><Twitter className="h-3.5 w-3.5" /></a>
          <a href="#" className="hover:text-[var(--fg-muted)]" aria-label="LinkedIn"><Linkedin className="h-3.5 w-3.5" /></a>
          <span className="hidden sm:flex items-center gap-1">
            صنع بـ <Heart className="h-3 w-3 text-[var(--danger)] fill-current" /> في السعودية
          </span>
        </div>
      </div>
    </footer>
  );
}

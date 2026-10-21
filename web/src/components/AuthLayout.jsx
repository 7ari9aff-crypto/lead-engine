import React from "react";
import { Languages } from "lucide-react";

// `dir` is set on this subtree only. The signed-in app deliberately keeps
// <html dir="ltr"> and relies on dir="auto" per field; the auth pages are a
// separate, form-only surface where a real RTL layout is correct.
export default function AuthLayout({ icon: Icon, title, subtitle, footer, children, lang }) {
  return (
    <div dir={lang.dir} lang={lang.lang} className="min-h-screen flex items-center justify-center bg-background px-4 relative">
      <button
        type="button"
        onClick={lang.toggle}
        className="absolute top-4 end-4 inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
      >
        <Languages className="w-3.5 h-3.5" aria-hidden="true" />
        {lang.t("lang.switch")}
      </button>
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-primary mb-4">
            <Icon className="w-7 h-7 text-primary-foreground" aria-hidden="true" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground">{title}</h1>
          {subtitle && <p className="text-muted-foreground mt-2">{subtitle}</p>}
        </div>
        <div className="bg-card rounded-2xl shadow-sm border border-border p-8">
          {children}
        </div>
        {footer && (
          <p className="text-center text-sm text-muted-foreground mt-6">{footer}</p>
        )}
      </div>
    </div>
  );
}

import React, { useState } from "react";
import { Link } from "react-router-dom";
import { resetPasswordForEmail } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Mail, ArrowRight, Loader2 } from "lucide-react";
import AuthLayout from "@/components/AuthLayout";
import { useAuthLang } from "@/hooks/useAuthLang";

export default function ForgotPassword() {
  const lang = useAuthLang();
  const { t } = lang;
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await resetPasswordForEmail(email);
    } catch {
      // Always show success regardless
    } finally {
      setLoading(false);
      setSent(true);
    }
  };

  return (
    <AuthLayout
      lang={lang}
      icon={Mail}
      title={t("forgot.title")}
      subtitle={t("forgot.subtitle")}
      footer={
        <Link to="/login" className="text-primary font-medium hover:underline">
          {/* "back" points toward the start edge: rotate in RTL where start is right */}
          <ArrowRight className={"w-3 h-3 inline me-1 " + (lang.dir === "rtl" ? "" : "rotate-180")} aria-hidden="true" />
          {t("forgot.back")}
        </Link>
      }
    >
      {sent ? (
        <p role="status" className="text-sm text-foreground text-center">
          {t("forgot.sent")}
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="email">{t("forgot.emailLabel")}</Label>
            <div className="relative">
              <Mail className="absolute start-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" aria-hidden="true" />
              <Input
                id="email"
                type="email"
                dir="ltr"
                autoComplete="email"
                autoFocus
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="ps-10 h-12 text-start"
                required
              />
            </div>
          </div>
          <Button type="submit" className="w-full h-12 font-medium" disabled={loading}>
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 me-2 animate-spin" />
                {t("forgot.submitting")}
              </>
            ) : (
              t("forgot.submit")
            )}
          </Button>
        </form>
      )}
    </AuthLayout>
  );
}

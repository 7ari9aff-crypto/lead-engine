import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import {
  Zap, Mail, Lock, Eye, EyeOff, User as UserIcon, ArrowRight,
  ShieldCheck, MailCheck, KeyRound, Loader2, CheckCircle2,
} from "lucide-react";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { apiGet } from "@/lib/api";
import { friendlyError } from "@/lib/friendly";
import { supabase, supabaseConfigured } from "@/lib/supabase";
import { toast } from "sonner";

// Shared split layout: brand panel + form card.
export function AuthLayout({ children, title, subtitle }: {
  children: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="min-h-screen flex" dir="rtl">
      {/* Brand panel */}
      <div className="hidden lg:flex flex-col justify-between w-[42%] p-10 relative overflow-hidden bg-[image:var(--gradient)]">
        <div className="absolute inset-0 bg-black/35" />
        <div className="relative">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="h-9 w-9 rounded-lg bg-white/15 backdrop-blur flex items-center justify-center">
              <Zap className="h-4.5 w-4.5 text-white" />
            </span>
            <span className="font-bold text-white text-[16px]">Lead Engine</span>
          </Link>
        </div>
        <div className="relative text-white">
          <h2 className="text-3xl font-black leading-snug">
            محرك توليد عملاء محتملين
            <br />
            يشتغل بمفاتيحك
          </h2>
          <p className="text-white/75 text-[14px] mt-4 leading-7 max-w-sm">
            جولات استهداف حقيقية، تأهيل آلي، فحص إيميل، وحماية قانونية — كل ده من داشبورد عربي واحد بدون سطر كود واحد.
          </p>
          <div className="mt-8 space-y-3">
            {[
              { icon: ShieldCheck, text: "بوابة سياسات تحميك من الحظر قبل الإرسال" },
              { icon: MailCheck, text: "فحص إيميل بخمس حالات قبل ما تدخل أي قايمة" },
              { icon: KeyRound, text: "شفافية كاملة: الفشل ببلاش والكاش ببلاش" },
            ].map((r) => {
              const Icon = r.icon;
              return (
                <div key={r.text} className="flex items-center gap-3 text-[13px] text-white/90">
                  <span className="h-8 w-8 rounded-lg bg-white/10 backdrop-blur flex items-center justify-center shrink-0">
                    <Icon className="h-4 w-4" />
                  </span>
                  {r.text}
                </div>
              );
            })}
          </div>
        </div>
        <div className="relative text-white/60 text-[11px]">صنع في السعودية</div>
      </div>

      {/* Form side */}
      <div className="flex-1 flex items-center justify-center p-6 bg-[var(--bg)]">
        <div className="w-full max-w-sm">
          <Link href="/" className="lg:hidden flex items-center gap-2 mb-8 justify-center">
            <span className="h-8 w-8 rounded-lg bg-[image:var(--gradient)] flex items-center justify-center">
              <Zap className="h-4 w-4 text-white" />
            </span>
            <span className="font-bold">Lead Engine</span>
          </Link>
          <h1 className="text-2xl font-black mb-1.5">{title}</h1>
          <p className="text-[13px] text-[var(--fg-muted)] mb-6">{subtitle}</p>
          {children}
        </div>
      </div>
    </div>
  );
}

export function LoginPage() {
  const [, navigate] = useLocation();
  const [mode, setMode] = useState<"loading" | "supabase" | "password" | "open">("loading");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [resetSent, setResetSent] = useState(false);

  useEffect(() => {
    let alive = true;
    apiGet.authSession().then((r) => {
      if (!alive) return;
      setMode((r.mode as any) || "open");
      if (r.authenticated) navigate("/");
    }).catch(() => { if (alive) setMode("open"); });
    return () => { alive = false; };
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "supabase" && supabaseConfigured) {
        const { error } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
        if (error) throw error;
      } else if (mode === "password") {
        const { apiPost } = await import("@/lib/api");
        await apiPost.login(password);
      }
      navigate("/");
    } catch (err: unknown) {
      toast.error(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function sendReset() {
    if (!email.trim()) {
      toast.warning("اكتب بريدك الأول وبعدها اضغط استعادة");
      return;
    }
    setBusy(true);
    try {
      if (!supabaseConfigured) throw new Error("reset unavailable");
      await supabase.auth.resetPasswordForEmail(email.trim());
      setResetSent(true);
    } catch (err: unknown) {
      toast.error(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  if (mode === "loading") {
    return (
      <AuthLayout title="تسجيل الدخول" subtitle="جارٍ التحقق…">
        <div className="flex justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-[var(--accent)]" />
        </div>
      </AuthLayout>
    );
  }

  if (mode === "open") {
    return (
      <AuthLayout title="لوحة التحكم" subtitle="الوضع الحالي مفتوح — الدخول مباشر.">
        <Button variant="primary" className="w-full h-11" onClick={() => navigate("/")}>
          <ArrowRight className="h-4 w-4" />
          ادخل اللوحة
        </Button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="تسجيل الدخول" subtitle="ادخل بحسابك لتصل للوحة التحكم.">
      {resetSent ? (
        <div className="rounded-xl border border-[var(--success)]/40 bg-[color-mix(in_srgb,var(--success)_8%,transparent)] p-4 text-[13px] flex items-start gap-2.5">
          <CheckCircle2 className="h-4 w-4 text-[var(--success)] mt-0.5 shrink-0" />
          <span>
            بعتنا رسالة استعادة كلمة المرور على بريدك — افتحها واتبع الرابط، وبعدها سجّل دخول من هنا.
          </span>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3.5">
          {mode === "supabase" && (
            <div>
              <label className="text-[12px] font-medium text-[var(--fg-muted)] block mb-1.5">البريد الإلكتروني</label>
              <div className="relative">
                <Mail className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
                <Input
                  type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com" dir="ltr" className="ps-10" required autoFocus
                />
              </div>
            </div>
          )}
          <div>
            <label className="text-[12px] font-medium text-[var(--fg-muted)] block mb-1.5">
              {mode === "supabase" ? "كلمة المرور" : "كلمة مرور اللوحة"}
            </label>
            <div className="relative">
              <Lock className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
              <Input
                type={show ? "text" : "password"} value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••" dir="ltr" className="pe-10 ps-10" required autoFocus={mode === "password"}
              />
              <button
                type="button" onClick={() => setShow(!show)}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--fg-soft)] hover:text-[var(--fg)] transition-colors"
                title={show ? "إخفاء" : "إظهار"}
              >
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <Button type="submit" variant="primary" className="w-full h-11" loading={busy}>
            دخول
          </Button>
          <div className="flex items-center justify-between text-[12px] pt-1">
            {mode === "supabase" ? (
              <button type="button" onClick={sendReset} className="text-[var(--accent)] hover:underline">
                نسيت كلمة المرور؟
              </button>
            ) : <span />}
            {mode === "supabase" && (
              <Link href="/signup" className="text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors">
                ماعندكش حساب؟ سجّل الآن
              </Link>
            )}
          </div>
        </form>
      )}
    </AuthLayout>
  );
}

export function SignupPage() {
  const [, navigate] = useLocation();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [needsConfirm, setNeedsConfirm] = useState(false);

  const strong = password.length >= 8;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      if (!supabaseConfigured) throw new Error("التسجيل غير متاح حاليًا — جرّب الدخول أو تواصل معنا");
      const { data, error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: name.trim() ? { data: { full_name: name.trim() } } : undefined,
      });
      if (error) throw error;
      if (data.session) {
        navigate("/");
      } else {
        setNeedsConfirm(true);
      }
    } catch (err: unknown) {
      toast.error(friendlyError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="إنشاء حساب جديد" subtitle="دقيقة واحدة وتكون جاهز لأول جولة استهداف.">
      {needsConfirm ? (
        <div className="rounded-xl border border-[var(--success)]/40 bg-[color-mix(in_srgb,var(--success)_8%,transparent)] p-4 text-[13px] flex items-start gap-2.5">
          <MailCheck className="h-4 w-4 text-[var(--success)] mt-0.5 shrink-0" />
          <span>
            حسابك اتعمل — بعتنا رسالة تأكيد على بريدك. فعّل الحساب من الرابط وبعدها سجّل دخول عادي.
          </span>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-3.5">
          <div>
            <label className="text-[12px] font-medium text-[var(--fg-muted)] block mb-1.5">الاسم</label>
            <div className="relative">
              <UserIcon className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
              <Input
                value={name} onChange={(e) => setName(e.target.value)}
                placeholder="اسمك الكامل" className="ps-10" required autoFocus
              />
            </div>
          </div>
          <div>
            <label className="text-[12px] font-medium text-[var(--fg-muted)] block mb-1.5">البريد الإلكتروني</label>
            <div className="relative">
              <Mail className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
              <Input
                type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com" dir="ltr" className="ps-10" required
              />
            </div>
          </div>
          <div>
            <label className="text-[12px] font-medium text-[var(--fg-muted)] block mb-1.5">كلمة المرور</label>
            <div className="relative">
              <Lock className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--fg-soft)]" />
              <Input
                type={show ? "text" : "password"} value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="٨ أحرف على الأقل" dir="ltr" className="pe-10 ps-10" required minLength={8}
              />
              <button
                type="button" onClick={() => setShow(!show)}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--fg-soft)] hover:text-[var(--fg)] transition-colors"
                title={show ? "إخفاء" : "إظهار"}
              >
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {password.length > 0 && !strong && (
              <p className="text-[11px] text-[var(--warn)] mt-1.5">كلمة المرور محتاجة ٨ أحرف على الأقل</p>
            )}
          </div>
          <Button type="submit" variant="primary" className="w-full h-11" loading={busy} disabled={!strong}>
            إنشاء الحساب
          </Button>
          <p className="text-[11px] text-[var(--fg-soft)] leading-4">
            بإنشائك حساب انت موافق على استخدام المنصة لجمع بيانات أعمال العامة فقط ووفق سياسات القوانين المدمجة فيها.
          </p>
          <div className="text-[12px] text-center pt-1">
            عندك حساب بالفعل؟{" "}
            <Link href="/login" className="text-[var(--accent)] hover:underline font-medium">
              سجّل دخول
            </Link>
          </div>
        </form>
      )}
    </AuthLayout>
  );
}

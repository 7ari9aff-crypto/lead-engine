import { Link } from "wouter";
import {
  Zap, ArrowLeft, Play, Cpu, ShieldCheck, MailCheck, Scale, KeyRound,
  Plug, Search, Target, CheckCircle2, Github, Twitter, Linkedin, Globe2,
} from "lucide-react";
import { cn } from "@/lib/utils";

// Real numbers from the first live V0 run on Supabase — no invented stats.
const LIVE_STATS = [
  { value: "٨٤", label: "عميل محتمل في أول تشغيل حقيقي" },
  { value: "٣٢", label: "عميل مؤهل ومقبول تلقائيًا" },
  { value: "١٨", label: "مزوّد بيانات متصل" },
  { value: "٥", label: "حالات فحص لكل إيميل" },
];

const FEATURES = [
  {
    icon: Search,
    title: "توليد حقيقي، مش وعود",
    desc: "كل مهمة بتدوّر فعليًا في السوق السعودي عبر مزوّدين حقيقيين بمفاتيحك — من أول البحث لحد العميل المؤهل، وكل خطوة موثقة بمصدرها.",
  },
  {
    icon: Target,
    title: "تأهيل بأوزان انت تتحكم فيها",
    desc: "اضبط أهمية كل عامل — جاهزية العميل، قوة الأدلة، سهولة التواصل — من شاشة بسيطة، والدرجات تتغير فورًا في الجولة اللي بعدها.",
  },
  {
    icon: MailCheck,
    title: "فحص إيميل بخمس حالات",
    desc: "مفيش بريد وهمي يدخل قايمتك: موجود، موجود مع مخاطر، دومين مفتوح، غير موجود، أو غير معروف — وكل حالة بقرار واضح.",
  },
  {
    icon: ShieldCheck,
    title: "حماية من الحظر قبل الإرسال",
    desc: "بوابة سياسات بتمنع التواصل مع المحجوبين تلقائيًا، وسياسات قوانين لكل دولة قبل ما أي بيانات تتجمع أو تتخزن.",
  },
  {
    icon: KeyRound,
    title: "شفافية استهلاك كاملة",
    desc: "كل مفتاح وكل استدعاء مسجل بالتوكنز. الفشل ببلاش، والكاش ببلاش، ولما مفتاح يخلص الحصص بيتدور تلقائيًا على التاني.",
  },
  {
    icon: Plug,
    title: "تكاملات وربط بالذكاء الاصطناعي",
    desc: "جيميل وهاب سبوت ومايكروسوفت بتسجيل دخول آمن، وخادم MCP جاهز يخلي مساعدك الذكي يشغّل المنصة من بره.",
  },
];

const STEPS = [
  {
    n: "١",
    title: "اربط مفاتيحك",
    desc: "الصق مفاتيح المزوّدين اللي بتختارهم — أغلبهم فيه طبقة مجانية. المنصة تكتشفهم وتفعّلهم فورًا.",
  },
  {
    n: "٢",
    title: "شغّل أول جولة",
    desc: "اختر قالب التشغيل المناسب واضغط زر واحد. المهام بتشتغل في الخلفية وتقدر تتابعها لحظة بلحظة.",
  },
  {
    n: "٣",
    title: "استلم عملاء مؤهلين",
    desc: "النتائج توصل مرتبة بالدرجة، مفحوصة، ومصنفة — صدّرها أو كمّل معاها جوه المنصة.",
  },
];

export function LandingPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-[var(--fg)]" dir="rtl">
      {/* Nav */}
      <header className="sticky top-0 z-30 glass border-b border-[var(--border)]">
        <div className="max-w-6xl mx-auto px-5 h-14 flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2.5">
            <span className="h-8 w-8 rounded-lg bg-[image:var(--gradient)] flex items-center justify-center">
              <Zap className="h-4 w-4 text-white" />
            </span>
            <span className="font-bold text-[15px]">Lead Engine</span>
          </Link>
          <nav className="hidden md:flex items-center gap-5 text-[13px] text-[var(--fg-muted)] ms-6">
            <a href="#features" className="hover:text-[var(--fg)] transition-colors">المزايا</a>
            <a href="#how" className="hover:text-[var(--fg)] transition-colors">كيف يعمل</a>
            <Link href="/pricing" className="hover:text-[var(--fg)] transition-colors">الأسعار</Link>
          </nav>
          <div className="ms-auto flex items-center gap-2">
            <Link href="/login">
              <button className="h-9 px-4 rounded-lg text-[13px] font-medium text-[var(--fg-muted)] hover:text-[var(--fg)] hover:bg-[var(--bg-hover)] transition-colors">
                دخول
              </button>
            </Link>
            <Link href="/signup">
              <button className="h-9 px-4 rounded-lg bg-[image:var(--gradient)] text-white text-[13px] font-semibold hover:opacity-90 transition-opacity">
                ابدأ مجانًا
              </button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none opacity-40"
          style={{
            background:
              "radial-gradient(600px 300px at 70% 0%, color-mix(in srgb, var(--accent) 18%, transparent), transparent)",
          }}
        />
        <div className="max-w-6xl mx-auto px-5 pt-16 pb-10 md:pt-24 text-center relative">
          <span className="inline-flex items-center gap-1.5 h-7 px-3 rounded-full border border-[var(--accent)]/40 bg-[var(--accent-soft)] text-[var(--accent)] text-[11px] font-semibold mb-5">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--success)] animate-pulse" />
            شغّال فعليًا على السوق السعودي — بأرقام حقيقية
          </span>
          <h1 className="text-4xl md:text-6xl font-black leading-[1.15] max-w-3xl mx-auto">
            محرك توليد عملاء محتملين
            <span className="block mt-2 bg-[image:var(--gradient)] bg-clip-text text-transparent">
              يشتغل بمفاتيحك، ويرجعلك عملاء جاهزين
            </span>
          </h1>
          <p className="text-[15px] md:text-[17px] text-[var(--fg-muted)] max-w-2xl mx-auto mt-5 leading-7">
            بدون كود وبدون فريق تقني: اربط مفاتيحك، شغّل جولة استهداف، واستلم قايمة عملاء
            مؤهلين ومفحوصين — مع شفافية كاملة في كل استدعاء وكل قرش استهلاك.
          </p>
          <div className="flex items-center justify-center gap-3 mt-7 flex-wrap">
            <Link href="/signup">
              <button className="h-11 px-6 rounded-xl bg-[image:var(--gradient)] text-white text-[14px] font-bold flex items-center gap-2 hover:opacity-90 hover:shadow-[var(--shadow-lg)] transition-all">
                ابدأ مجانًا الآن
                <ArrowLeft className="h-4 w-4" />
              </button>
            </Link>
            <Link href="/login">
              <button className="h-11 px-6 rounded-xl border border-[var(--border)] text-[14px] font-semibold flex items-center gap-2 hover:bg-[var(--bg-hover)] transition-colors">
                <Play className="h-4 w-4 text-[var(--accent)]" />
                عندك حساب؟ دخول
              </button>
            </Link>
          </div>

          {/* Product mock — stylized from the real first run */}
          <div className="max-w-4xl mx-auto mt-14 rounded-2xl border border-[var(--border)] bg-[var(--bg-elev)] shadow-[var(--shadow-lg)] overflow-hidden text-right">
            <div className="h-9 border-b border-[var(--border-soft)] bg-[var(--bg-soft)] flex items-center gap-1.5 px-4" dir="ltr">
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--danger)]/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--warn)]/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--success)]/70" />
              <span className="ms-3 text-[10px] text-[var(--fg-soft)]">Lead Engine — نظرة عامة</span>
            </div>
            <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-3">
              {LIVE_STATS.map((s) => (
                <div key={s.label} className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-soft)] p-3.5">
                  <div className="text-2xl font-black tnum bg-[image:var(--gradient)] bg-clip-text text-transparent">{s.value}</div>
                  <div className="text-[10px] text-[var(--fg-soft)] mt-1 leading-3.5">{s.label}</div>
                </div>
              ))}
            </div>
            <div className="px-5 pb-5 grid grid-cols-3 gap-3">
              {[82, 56, 94, 68, 100, 74].map((h, i) => (
                <div key={i} className="h-16 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-soft)] flex items-end overflow-hidden">
                  <div
                    className="w-full rounded-t-md bg-[image:var(--gradient)] opacity-80"
                    style={{ height: `${h}%` }}
                  />
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="max-w-6xl mx-auto px-5 py-16">
        <div className="text-center mb-10">
          <h2 className="text-2xl md:text-3xl font-black">كل اللي محتاجه لتوليد عملاء — في مكان واحد</h2>
          <p className="text-[14px] text-[var(--fg-muted)] mt-3">
            المنصة بتديك خط إنتاج كامل: استهداف، بحث، تأهيل، فحص، وحماية قانونية — وإنت مش محتاج تفهم إزاي بيحصل.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <div
                key={f.title}
                className="rounded-2xl border border-[var(--border)] bg-[var(--bg-elev)] p-5 hover:border-[var(--accent)]/50 hover:shadow-[var(--shadow)] transition-all"
              >
                <div className="h-10 w-10 rounded-xl bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center mb-3.5">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="text-[15px] font-bold mb-1.5">{f.title}</h3>
                <p className="text-[13px] text-[var(--fg-muted)] leading-6">{f.desc}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="border-y border-[var(--border)] bg-[var(--bg-elev)]/40">
        <div className="max-w-6xl mx-auto px-5 py-16">
          <div className="text-center mb-10">
            <h2 className="text-2xl md:text-3xl font-black">تلات خطوات وأنت بتشتغل</h2>
            <p className="text-[14px] text-[var(--fg-muted)] mt-3">من التسجيل لأول قايمة عملاء في أقل من ساعة.</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {STEPS.map((s, i) => (
              <div key={s.n} className="relative rounded-2xl border border-[var(--border)] bg-[var(--bg-elev)] p-6">
                <span className="h-10 w-10 rounded-full bg-[image:var(--gradient)] text-white font-black text-[16px] flex items-center justify-center mb-4">
                  {s.n}
                </span>
                <h3 className="text-[15px] font-bold mb-2">{s.title}</h3>
                <p className="text-[13px] text-[var(--fg-muted)] leading-6">{s.desc}</p>
                {i < STEPS.length - 1 && (
                  <ArrowLeft className="hidden md:block h-5 w-5 text-[var(--fg-soft)] absolute top-1/2 -left-3.5 z-10" />
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Principles */}
      <section className="max-w-6xl mx-auto px-5 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-[var(--success)]/30 bg-[color-mix(in_srgb,var(--success)_6%,transparent)] p-6">
            <CheckCircle2 className="h-6 w-6 text-[var(--success)] mb-3" />
            <h3 className="text-[16px] font-bold mb-2">بيانات حقيقية ١٠٠٪</h3>
            <p className="text-[13px] text-[var(--fg-muted)] leading-6">
              مفيش بيانات تجريبية ولا نتائج مفبركة — كل عميل في قايمتك ليه مصدر حقيقي ورابط،
              والمنصة مش بتشتغل أصلًا غير لما المزوّد الحقيقي يرد.
            </p>
          </div>
          <div className="rounded-2xl border border-[var(--accent)]/30 bg-[var(--accent-soft)]/40 p-6">
            <Cpu className="h-6 w-6 text-[var(--accent)] mb-3" />
            <h3 className="text-[16px] font-bold mb-2">صفر كود للمستخدم</h3>
            <p className="text-[13px] text-[var(--fg-muted)] leading-6">
              كل الإعدادات بشاشات عربية بسيطة: سلايدرز، أزرار، وشرائح. مفيش ملفات ولا أوامر
              ولا حاجة تقنية — المصمم لغير المتخصصين.
            </p>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="max-w-6xl mx-auto px-5 pb-20">
        <div className="rounded-3xl border border-[var(--accent)]/40 bg-[image:var(--gradient)] p-10 md:p-14 text-center relative overflow-hidden">
          <div className="absolute inset-0 bg-black/30" />
          <div className="relative">
            <h2 className="text-2xl md:text-4xl font-black text-white">جولةك الأولى على بُعد ضغطة</h2>
            <p className="text-white/80 text-[14px] mt-3 max-w-xl mx-auto">
              أنشئ حسابك مجانًا، اربط أول مفتاح، وشغّل قالب الاستكشاف السريع — النتائج على الطاولة في دقائق.
            </p>
            <Link href="/signup" className="inline-block mt-7">
              <button className="h-12 px-8 rounded-xl bg-white text-black text-[15px] font-bold flex items-center gap-2 mx-auto hover:shadow-2xl transition-shadow">
                أنشئ حسابك مجانًا
                <ArrowLeft className="h-4 w-4" />
              </button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-[var(--border)]">
        <div className="max-w-6xl mx-auto px-5 py-8 flex items-center justify-between flex-wrap gap-4 text-[12px] text-[var(--fg-soft)]">
          <div className="flex items-center gap-2">
            <span className="h-6 w-6 rounded-md bg-[image:var(--gradient)] flex items-center justify-center">
              <Zap className="h-3 w-3 text-white" />
            </span>
            <span className="font-semibold text-[var(--fg-muted)]">Lead Engine</span>
            <span>·</span>
            <span className="flex items-center gap-1">
              <Globe2 className="h-3.5 w-3.5" />
              صنع في السعودية
            </span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/pricing" className="hover:text-[var(--fg)] transition-colors">الأسعار</Link>
            <Link href="/login" className="hover:text-[var(--fg)] transition-colors">دخول</Link>
            <a
              href="https://github.com/7ari9aff-crypto/lead-engine"
              target="_blank"
              rel="noreferrer"
              className="hover:text-[var(--fg)] transition-colors flex items-center gap-1"
            >
              <Github className="h-3.5 w-3.5" />
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}

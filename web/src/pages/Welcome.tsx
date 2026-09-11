import { Link } from "wouter";
import {
  Zap,
  Bot,
  Sparkles,
  ArrowLeft,
  ArrowDown,
  Network,
  MousePointerClick,
  Layers,
  Play,
  UserPlus,
  Headphones,
  PenLine,
  Target,
  Linkedin,
  Map,
  MessageCircle,
  Mail,
  Slack,
  Send,
  BookOpen,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Footer } from "@/components/layout/Footer";

type Pillar = { icon: typeof Bot; title: string; desc: string; color: string };
type Step = { num: string; icon: typeof Bot; title: string; desc: string };
type Domain = { icon: typeof Bot; title: string; desc: string };
type Integration = { icon: typeof Bot; label: string };
type Stat = { value: string; label: string };

const PILLARS: Pillar[] = [
  {
    icon: Network,
    title: "متعدد الوكلاء",
    desc: "وكيل مستقل لكل مهمة — leads، دعم، محتوى، مبيعات. شغّل اللي تحتاجه ووقّف الباقي.",
    color: "var(--accent)",
  },
  {
    icon: MousePointerClick,
    title: "بدون كود",
    desc: "كل شيء من لوحة مرئية: الإعدادات، الفلاتر، الكلمات المفتاحية، الـ prompts. بدون سطر كود.",
    color: "var(--info)",
  },
  {
    icon: Layers,
    title: "متعدد المجالات",
    desc: "نفس المنصة تخدم أي بيزنس: B2B، B2C، عقار، تعليم، مطاعم. الوكلاء يتكيّفوا مع مجالك.",
    color: "var(--success)",
  },
  {
    icon: Check,
    title: "APIs حقيقية 100%",
    desc: "كل البيانات والتكاملات من APIs مدفوعة فعلاً — لا placeholders ولا mocks في الـ demos.",
    color: "var(--warn)",
  },
];

const STEPS: Step[] = [
  {
    num: "1",
    icon: MousePointerClick,
    title: "اربط",
    desc: "وصّل حساباتك على المنصات — LinkedIn، Gmail، WhatsApp، Slack… في أقل من دقيقة.",
  },
  {
    num: "2",
    icon: Layers,
    title: "اضبط",
    desc: "اختر الوكيل، حدد الجمهور والهدف، اضبط الـ prompt مرة واحدة. المنصة تشتغل وحدها.",
  },
  {
    num: "3",
    icon: Play,
    title: "شغّل",
    desc: "اضغط ابدأ. شوف النتائج مباشرة في الداشبورد، أو خلّي الوكلاء يبعتوا تلقائي.",
  },
];

const DOMAINS: Domain[] = [
  {
    icon: UserPlus,
    title: "توليد العملاء المحتملين",
    desc: "يلاقي الشركات والأشخاص، يفحص الإيميلات، يبعت رسائل مخصصة.",
  },
  {
    icon: Headphones,
    title: "دعم العملاء",
    desc: "يرد على الاستفسارات 24/7 بالعربية والإنجليزية، يحوّل الحالات الحساسة للموظف.",
  },
  {
    icon: PenLine,
    title: "تسويق المحتوى",
    desc: "يكتب بوستات، يصمم أفكار، ينشر على منصاتك في الأوقات الصح.",
  },
  {
    icon: Target,
    title: "المبيعات والتأهيل",
    desc: "يأهل الـ leads، يحجز اجتماعات، يتابع العملاء المحتملين لحين الإغلاق.",
  },
];

const INTEGRATIONS: Integration[] = [
  { icon: Linkedin, label: "LinkedIn" },
  { icon: Map, label: "Google Maps" },
  { icon: MessageCircle, label: "WhatsApp" },
  { icon: Mail, label: "Gmail" },
  { icon: Slack, label: "Slack" },
  { icon: Send, label: "Telegram" },
  { icon: BookOpen, label: "Notion" },
];

const STATS: Stat[] = [
  { value: "30+", label: "عميل محتمل / يوم" },
  { value: "5", label: "منصات متصلة" },
  { value: "<$0.01", label: "تكلفة كل lead" },
];

export function WelcomePage() {
  return (
    <div dir="rtl" className="min-h-screen overflow-x-hidden bg-[var(--bg)] text-[var(--fg)]">
      {/* === NAV === */}
      <header className="sticky top-0 z-40 glass border-b border-[var(--border)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
          <Link href="/welcome" className="flex items-center gap-2 shrink-0">
            <div className="h-9 w-9 rounded-lg bg-[image:var(--gradient)] flex items-center justify-center shadow-md">
              <Zap className="h-5 w-5 text-white" />
            </div>
            <span className="font-bold text-base gradient-text">Lead Engine</span>
          </Link>
          <nav className="hidden md:flex items-center gap-6 text-sm">
            <a href="#pillars" className="text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors">المنصة</a>
            <a href="#how" className="text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors">كيف يشتغل</a>
            <a href="#domains" className="text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors">المجالات</a>
            <a href="#integrations" className="text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors">التكاملات</a>
          </nav>
          <div className="flex items-center gap-2 shrink-0">
            <Button variant="ghost" size="sm" asChild>
              <Link href="/pricing">الأسعار</Link>
            </Button>
            <Button variant="primary" size="sm" asChild>
              <Link href="/">
                ابدأ الآن
                <ArrowLeft className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        </div>
      </header>

      {/* === 1. HERO === */}
      <section className="relative pt-16 sm:pt-24 pb-20 sm:pb-28 px-4 sm:px-6 lg:px-8">
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-[var(--accent)] opacity-20 blur-[120px]" />
        </div>
        <div className="max-w-4xl mx-auto text-center">
          <Badge variant="accent" className="mb-6 text-xs">
            <Sparkles className="h-3 w-3" />
            منصة الوكلاء الذكيين — multi-domain
          </Badge>
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight mb-6 leading-[1.1]">
            <span className="gradient-text">منصة الوكلاء الذكيين</span>
            <br />
            <span className="text-[var(--fg-muted)] text-3xl sm:text-4xl md:text-5xl">
              لكل بيزنس
            </span>
          </h1>
          <p className="text-lg sm:text-xl text-[var(--fg-muted)] max-w-2xl mx-auto mb-10 leading-relaxed">
            وصّل، اضبط، شغّل. بدون كود، بدون فريق تقني — وكلاء حقيقيين على APIs
            حقيقية تشتغل بالنيابة عنك.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button variant="gradient" size="lg" asChild>
              <Link href="/">
                ابدأ مجاناً
                <ArrowLeft className="h-4 w-4" />
              </Link>
            </Button>
            <Button variant="outline" size="lg" asChild>
              <a href="#how">
                شوف العرض
                <ArrowDown className="h-4 w-4" />
              </a>
            </Button>
          </div>
          <p className="text-xs text-[var(--fg-soft)] mt-5">
            بدون بطاقة بنكية · مجاني للتجربة
          </p>
        </div>
      </section>

      {/* === 2. PLATFORM PILLARS === */}
      <section id="pillars" className="py-16 sm:py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-12">
            <Badge variant="default" className="mb-4">
              <Layers className="h-3 w-3" />
              أعمدة المنصة
            </Badge>
            <h2 className="text-3xl sm:text-4xl font-bold mb-3">
              ليش Lead Engine؟
            </h2>
            <p className="text-[var(--fg-muted)] max-w-2xl mx-auto text-base">
              4 أشياء بنيناها من الصفر عشان تكون مختلفة عن أي أداة ثانية.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {PILLARS.map((p, i) => {
              const Icon = p.icon;
              return (
                <Card key={i} className="h-full">
                  <div className="p-5">
                    <div
                      className="h-11 w-11 rounded-lg flex items-center justify-center mb-4"
                      style={{
                        background: `color-mix(in srgb, ${p.color} 15%, transparent)`,
                        color: p.color,
                      }}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <h3 className="text-base font-semibold mb-1.5">{p.title}</h3>
                    <p className="text-sm text-[var(--fg-muted)] leading-relaxed">
                      {p.desc}
                    </p>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      </section>

      {/* === 3. HOW IT WORKS === */}
      <section
        id="how"
        className="py-16 sm:py-20 px-4 sm:px-6 lg:px-8 bg-[var(--bg-soft)]/40"
      >
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-12">
            <Badge variant="default" className="mb-4">
              <Play className="h-3 w-3" />
              كيف يشتغل
            </Badge>
            <h2 className="text-3xl sm:text-4xl font-bold mb-3">
              3 خطوات، وبتشتغل
            </h2>
            <p className="text-[var(--fg-muted)] max-w-2xl mx-auto text-base">
              ما تحتاج تتعلم شي. وصّل، اضبط، شغّل — والباقي على المنصة.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative">
            {STEPS.map((s, i) => {
              const Icon = s.icon;
              return (
                <div key={i} className="relative">
                  <Card className="h-full">
                    <div className="p-6">
                      <div className="flex items-center gap-3 mb-4">
                        <div className="h-10 w-10 shrink-0 rounded-full bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center font-bold">
                          {s.num}
                        </div>
                        <div className="h-10 w-10 shrink-0 rounded-lg bg-[image:var(--gradient)] text-white flex items-center justify-center">
                          <Icon className="h-5 w-5" />
                        </div>
                      </div>
                      <h3 className="text-lg font-semibold mb-2">{s.title}</h3>
                      <p className="text-sm text-[var(--fg-muted)] leading-relaxed">
                        {s.desc}
                      </p>
                    </div>
                  </Card>
                  {i < STEPS.length - 1 && (
                    <ArrowLeft
                      aria-hidden="true"
                      className="hidden md:block absolute top-1/2 -translate-y-1/2 -left-3 h-5 w-5 text-[var(--fg-soft)] bg-[var(--bg)] rounded-full p-0.5"
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* === 4. DOMAINS SHOWCASE === */}
      <section id="domains" className="py-16 sm:py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-12">
            <Badge variant="default" className="mb-4">
              <Target className="h-3 w-3" />
              المجالات
            </Badge>
            <h2 className="text-3xl sm:text-4xl font-bold mb-3">
              وش يقدر الوكيل يسوي لك؟
            </h2>
            <p className="text-[var(--fg-muted)] max-w-2xl mx-auto text-base">
              وكلاء متخصصين في كل مجال — تشغّل اللي يناسب بيزنسك.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {DOMAINS.map((d, i) => {
              const Icon = d.icon;
              return (
                <Card key={i} className="h-full">
                  <div className="p-5">
                    <div className="h-11 w-11 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center mb-4">
                      <Icon className="h-5 w-5" />
                    </div>
                    <h3 className="text-base font-semibold mb-1.5">
                      {d.title}
                    </h3>
                    <p className="text-sm text-[var(--fg-muted)] leading-relaxed">
                      {d.desc}
                    </p>
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      </section>

      {/* === 5. INTEGRATIONS TEASER === */}
      <section
        id="integrations"
        className="py-16 sm:py-20 px-4 sm:px-6 lg:px-8 bg-[var(--bg-soft)]/40"
      >
        <div className="max-w-5xl mx-auto text-center">
          <Badge variant="default" className="mb-4">
            <Network className="h-3 w-3" />
            تكاملات
          </Badge>
          <h2 className="text-3xl sm:text-4xl font-bold mb-3">
            يشتغل مع كل أدواتك
          </h2>
          <p className="text-[var(--fg-muted)] max-w-2xl mx-auto text-base mb-10">
            وصّل حساباتك الموجودة — ما تحتاج تتخلى عن أي أداة. (التكامل الفعلي
            يتم في شاشة الـ Connect)
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
            {INTEGRATIONS.map((it, i) => {
              const Icon = it.icon;
              return (
                <div
                  key={i}
                  className="flex flex-col items-center gap-2 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-elev)] hover:border-[var(--accent)] transition-colors"
                >
                  <Icon className="h-6 w-6 text-[var(--fg-muted)]" />
                  <span className="text-xs text-[var(--fg-muted)]">
                    {it.label}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="text-xs text-[var(--fg-soft)] mt-6">
            والمزيد قريباً — هذي الأدوات الأكثر طلباً من العملاء.
          </p>
        </div>
      </section>

      {/* === 6. STATS / TRUST === */}
      <section className="py-16 sm:py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-10">
            <Badge variant="accent" className="mb-4 text-xs">
              <Sparkles className="h-3 w-3" />
              أرقام تقريبية
            </Badge>
            <h2 className="text-3xl sm:text-4xl font-bold mb-3">
              وش تتوقع من المنصة؟
            </h2>
            <p className="text-[var(--fg-muted)] max-w-2xl mx-auto text-sm">
              أمثلة مبنية على سيناريوهات واقعية مع الإعدادات الافتراضية. النتيجة
              الفعلية تعتمد على مجالك وحجم الجمهور.
            </p>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {STATS.map((s, i) => (
              <Card key={i}>
                <div className="p-6 text-center">
                  <div className="text-3xl sm:text-4xl font-bold gradient-text mb-2 tnum">
                    {s.value}
                  </div>
                  <div className="text-sm text-[var(--fg-muted)] mb-2">
                    {s.label}
                  </div>
                  <div className="inline-block text-[10px] font-medium text-[var(--fg-soft)] bg-[var(--bg-soft)] border border-[var(--border-soft)] rounded-full px-2 py-0.5">
                    مثال تقريبي
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* === 7. FINAL CTA === */}
      <section className="py-16 sm:py-24 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          <div
            className="relative overflow-hidden rounded-2xl p-10 sm:p-16 text-center"
            style={{ background: "var(--gradient)" }}
          >
            <div className="absolute inset-0 bg-black/10" />
            <div className="relative">
              <Bot className="h-12 w-12 text-white mx-auto mb-4" />
              <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
                جاهز تبدأ؟
              </h2>
              <p className="text-white/85 text-lg mb-8 max-w-2xl mx-auto">
                سجّل دخولك، شغّل أول وكيل، وشوف النتيجة بنفسك. التجربة مجانية
                بالكامل.
              </p>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <Button
                  variant="secondary"
                  size="lg"
                  asChild
                  className="!bg-white !text-[var(--accent)] hover:!bg-white/90"
                >
                  <Link href="/">
                    <Sparkles className="h-5 w-5" />
                    ابدأ الآن مجاناً
                    <ArrowLeft className="h-4 w-4" />
                  </Link>
                </Button>
                <Button
                  variant="outline"
                  size="lg"
                  asChild
                  className="!bg-transparent !border-white/40 !text-white hover:!bg-white/10 hover:!border-white/60"
                >
                  <Link href="/pricing">شوف الأسعار</Link>
                </Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}

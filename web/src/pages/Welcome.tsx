import { Link } from "wouter";
import {
  Zap,
  Brain,
  Globe,
  Shield,
  Mail,
  Database,
  ArrowLeft,
  Sparkles,
  Check,
  Star,
  Users,
  TrendingUp,
  Search,
  Filter,
  RefreshCw,
  ChevronRight,
  Github,
  Twitter,
  Linkedin,
  Bot,
  Activity,
  Boxes,
  Lock,
} from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { useUI } from "@/hooks/useTheme";

const FEATURES = [
  {
    icon: Bot,
    title: "وكيل ذكي",
    desc: "يشغّل لك pipeline كامل بأمر واحد — يختار المزوّد الصحّ، يراقب الكوتا، يوقف عند العوائق.",
    color: "var(--accent)",
  },
  {
    icon: Search,
    title: "بحث متعدد المصادر",
    desc: "Tavily + Brave + Exa مع تدوير تلقائي — لو واحد قفل rate-limit ينتقل للثاني بدون ما تضيّع وقت.",
    color: "var(--info)",
  },
  {
    icon: Brain,
    title: "تفكير مؤتمت",
    desc: "5 نماذج لغوية (Gemini, Groq, OpenRouter, Ollama محلي) مع تقييم جودة لكل رد.",
    color: "var(--success)",
  },
  {
    icon: Mail,
    title: "فحص إيميل 5-حالات",
    desc: "DELIVERABLE · RISKY · CATCH_ALL · INVALID · UNKNOWN — يفصل بدقة catch-all عن غيره.",
    color: "var(--warn)",
  },
  {
    icon: Shield,
    title: "بوابة قانونية",
    desc: "PDPL-aware: يحجب أي شركة بدون إجماع قانوني قبل ما توصل لسجلّك. default-deny.",
    color: "var(--danger)",
  },
  {
    icon: Database,
    title: "كاش ذكي 3-مستويات",
    desc: "L1 request · L2 entity · L3 evidence — نفس الشركة ما تتسألش عنها مرتين.",
    color: "var(--accent)",
  },
];

const STATS = [
  { value: "18+", label: "مزوّد متاح" },
  { value: "8", label: "مراحل pipeline" },
  { value: "5", label: "نماذج لغوية" },
  { value: "100%", label: "قابل للنشر" },
];

const PILLARS = [
  { icon: Activity, title: "Job State Machine", desc: "QUEUED → RUNNING → DEGRADED → COMPLETED" },
  { icon: RefreshCw, title: "Resume من الإيقاف", desc: "يوقف بذكاء، يكمل من حيث ما وقف" },
  { icon: Filter, title: "Dedup 3-مراحل", desc: "exact → identity → fuzzy" },
  { icon: Lock, title: "مفاتيح مشفّرة", desc: ".env خارج git، live update" },
];

const fadeUp = {
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" as const } },
  viewport: { once: true, margin: "-50px" },
};

const stagger = {
  initial: {},
  whileInView: { transition: { staggerChildren: 0.08 } },
  viewport: { once: true, margin: "-50px" },
};

export function WelcomePage() {
  const { theme } = useUI();

  return (
    <div className="min-h-screen overflow-x-hidden">
      {/* === NAV === */}
      <motion.header
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.4 }}
        className="sticky top-0 z-40 glass border-b border-[var(--border)]"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-lg bg-[image:var(--gradient)] shadow-md flex items-center justify-center">
              <Zap className="h-5 w-5 text-white" />
            </div>
            <span className="font-bold text-base gradient-text">محرّك الـLeads</span>
          </div>
          <nav className="hidden md:flex items-center gap-6 text-sm">
            <a href="#features" className="text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors">
              المزايا
            </a>
            <a href="#how" className="text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors">
              كيف يشتغل
            </a>
            <Link href="/pricing" className="text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors">
              الأسعار
            </Link>
            <a href="#faq" className="text-[var(--fg-muted)] hover:text-[var(--fg)] transition-colors">
              الأسئلة
            </a>
          </nav>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" asChild>
              <Link href="/chat">
                <Bot className="h-4 w-4" />
                المساعد
              </Link>
            </Button>
            <Button variant="primary" size="sm" asChild>
              <Link href="/">
                <Activity className="h-4 w-4" />
                افتح اللوحة
                <ArrowLeft className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        </div>
      </motion.header>

      {/* === HERO === */}
      <section className="relative pt-20 pb-32 px-4 sm:px-6 lg:px-8">
        {/* Background glow */}
        <div className="absolute inset-0 -z-10 overflow-hidden">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-[var(--accent)] opacity-20 blur-[120px]" />
          <div className="absolute top-1/3 right-1/4 w-[400px] h-[400px] rounded-full bg-[#8b5cf6] opacity-15 blur-[100px]" />
        </div>

        <div className="max-w-5xl mx-auto text-center">
          <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: 0.5 }}>
            <Badge variant="accent" className="mb-6 text-xs">
              <Sparkles className="h-3 w-3" />
              v1.0 — مفتوح المصدر
            </Badge>
          </motion.div>

          <motion.h1
            {...fadeUp}
            initial={fadeUp.initial}
            whileInView={fadeUp.whileInView}
            viewport={fadeUp.viewport}
            className="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight mb-6 leading-[1.1]"
          >
            موتور <span className="gradient-text">توليد العملاء المحتملين</span>
            <br />
            <span className="text-[var(--fg-muted)] text-3xl sm:text-4xl md:text-5xl">واعي بالحصص، يفكّر قبل ما يصرف</span>
          </motion.h1>

          <motion.p
            initial={fadeUp.initial}
            whileInView={fadeUp.whileInView}
            viewport={fadeUp.viewport}
            className="text-lg sm:text-xl text-[var(--fg-muted)] max-w-3xl mx-auto mb-10 leading-relaxed"
          >
            يجمع لك بيانات الشركات والأشخاص من 18+ مزوّد، يفحص الإيميلات بدقة 5-حالات، يلتزم بسياسة البيانات السعودية — وكله من شات واحد.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="flex flex-wrap items-center justify-center gap-3 mb-16"
          >
            <Button variant="gradient" size="lg" asChild>
              <Link href="/chat">
                <Bot className="h-5 w-5" />
                ابدأ بالشات الآن
                <ArrowLeft className="h-4 w-4" />
              </Link>
            </Button>
            <Button variant="outline" size="lg" asChild>
              <a href="#features">
                تعرّف على المزايا
                <ChevronRight className="h-4 w-4" />
              </a>
            </Button>
          </motion.div>

          {/* Stats */}
          <motion.div
            initial={stagger.initial}
            whileInView={stagger.whileInView}
            viewport={stagger.viewport}
            className="grid grid-cols-2 sm:grid-cols-4 gap-3 max-w-3xl mx-auto"
          >
            {STATS.map((s, i) => (
              <motion.div
                key={i}
                initial={fadeUp.initial}
                whileInView={fadeUp.whileInView}
                viewport={fadeUp.viewport}
              >
                <Card className="hover:border-[var(--accent)] transition-colors">
                  <div className="p-5">
                    <div className="text-3xl font-bold gradient-text mb-1">{s.value}</div>
                    <div className="text-xs text-[var(--fg-muted)]">{s.label}</div>
                  </div>
                </Card>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* === FEATURES === */}
      <section id="features" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-16">
            <Badge variant="default" className="mb-4">
              <Boxes className="h-3 w-3" />
              المزايا الكاملة
            </Badge>
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">كل اللي تحتاجه في مكان واحد</h2>
            <p className="text-[var(--fg-muted)] max-w-2xl mx-auto text-lg">
              من البحث الأول إلى مزامنة Supabase — بدون كتابة سطر كود ولا تكلفة رصيد ضائع.
            </p>
          </motion.div>

          <motion.div
            initial={stagger.initial}
            whileInView={stagger.whileInView}
            viewport={stagger.viewport}
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
          >
            {FEATURES.map((f, i) => {
              const Icon = f.icon;
              return (
                <motion.div
                  key={i}
                  initial={fadeUp.initial}
                  whileInView={fadeUp.whileInView}
                  viewport={fadeUp.viewport}
                >
                  <Card className="h-full hover:border-[var(--accent)] transition-all hover:shadow-lg group">
                    <div className="p-6">
                      <div
                        className="h-12 w-12 rounded-lg flex items-center justify-center mb-4 transition-transform group-hover:scale-110"
                        style={{
                          background: `color-mix(in srgb, ${f.color} 15%, transparent)`,
                          color: f.color,
                        }}
                      >
                        <Icon className="h-6 w-6" />
                      </div>
                      <h3 className="text-lg font-semibold mb-2">{f.title}</h3>
                      <p className="text-sm text-[var(--fg-muted)] leading-relaxed">{f.desc}</p>
                    </div>
                  </Card>
                </motion.div>
              );
            })}
          </motion.div>
        </div>
      </section>

      {/* === HOW IT WORKS === */}
      <section id="how" className="py-20 px-4 sm:px-6 lg:px-8 bg-[var(--bg-soft)]/30">
        <div className="max-w-7xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-16">
            <Badge variant="default" className="mb-4">
              <TrendingUp className="h-3 w-3" />
              كيف يشتغل
            </Badge>
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">من الأمر إلى الـleads في 8 مراحل</h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {PILLARS.map((p, i) => {
              const Icon = p.icon;
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: 20 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                >
                  <Card className="hover:border-[var(--accent)] transition-colors">
                    <div className="p-6 flex items-start gap-4">
                      <div className="h-12 w-12 shrink-0 rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center">
                        <Icon className="h-6 w-6" />
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold mb-1">{p.title}</h3>
                        <p className="text-sm text-[var(--fg-muted)] font-mono" dir="ltr">{p.desc}</p>
                      </div>
                    </div>
                  </Card>
                </motion.div>
              );
            })}
          </div>
        </div>
      </section>

      {/* === TESTIMONIAL / SOCIAL PROOF === */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <motion.div {...fadeUp} initial="hidden" whileInView="show" viewport={{ once: true }}>
            <div className="flex justify-center mb-4">
              {[...Array(5)].map((_, i) => (
                <Star key={i} className="h-5 w-5 fill-[var(--warn)] text-[var(--warn)]" />
              ))}
            </div>
            <blockquote className="text-2xl sm:text-3xl font-medium leading-relaxed mb-6">
              "أداة <span className="gradient-text">ترى حدود الرصيد</span> قبل ما تستنزفها. ده اللي كان ناقص في السوق."
            </blockquote>
            <div className="flex items-center justify-center gap-3">
              <div className="h-12 w-12 rounded-full bg-[image:var(--gradient)] flex items-center justify-center text-white font-bold">
                MA
              </div>
              <div className="text-right">
                <div className="font-semibold">HAMED ADEL</div>
                <div className="text-sm text-[var(--fg-muted)]">صاحب المنصة · مينتج</div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* === FINAL CTA === */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            className="relative overflow-hidden rounded-2xl p-12 sm:p-16 text-center"
            style={{ background: "var(--gradient)" }}
          >
            <div className="absolute inset-0 bg-black/20" />
            <div className="relative">
              <Globe className="h-12 w-12 text-white mx-auto mb-4" />
              <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
                ابدأ تجربتك المجانية اليوم
              </h2>
              <p className="text-white/80 text-lg mb-8 max-w-2xl mx-auto">
                30 lead مجانًا، بدون بطاقة بنكية، بدون أي التزام.
              </p>
              <Button variant="secondary" size="lg" asChild className="!bg-white !text-[var(--accent)] hover:!bg-white/90">
                <Link href="/chat">
                  <Sparkles className="h-5 w-5" />
                  ابدأ الآن
                  <ArrowLeft className="h-4 w-4" />
                </Link>
              </Button>
            </div>
          </motion.div>
        </div>
      </section>

      {/* === FOOTER === */}
      <footer className="border-t border-[var(--border)] py-12 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="h-8 w-8 rounded-lg bg-[image:var(--gradient)] flex items-center justify-center">
                  <Zap className="h-4 w-4 text-white" />
                </div>
                <span className="font-bold gradient-text">محرّك الـLeads</span>
              </div>
              <p className="text-xs text-[var(--fg-muted)] leading-relaxed">
                موتور توليد leads واعٍ بالحصص، مفتوح المصدر، مصمَّم للسوق السعودي.
              </p>
            </div>
            <div>
              <h4 className="font-semibold mb-3 text-sm">المنتج</h4>
              <ul className="space-y-2 text-sm text-[var(--fg-muted)]">
                <li><Link href="/" className="hover:text-[var(--fg)]">اللوحة</Link></li>
                <li><Link href="/chat" className="hover:text-[var(--fg)]">المساعد</Link></li>
                <li><Link href="/pricing" className="hover:text-[var(--fg)]">الأسعار</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-3 text-sm">المصادر</h4>
              <ul className="space-y-2 text-sm text-[var(--fg-muted)]">
                <li><a href="https://github.com/7ari9aff-crypto/lead-engine" target="_blank" rel="noopener" className="hover:text-[var(--fg)] flex items-center gap-1">GitHub <Github className="h-3 w-3" /></a></li>
                <li><Link href="/docs" className="hover:text-[var(--fg)]">التوثيق</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold mb-3 text-sm">تواصل</h4>
              <ul className="space-y-2 text-sm text-[var(--fg-muted)]">
                <li>7amedadel7@gmail.com</li>
              </ul>
            </div>
          </div>
          <div className="border-t border-[var(--border-soft)] pt-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-[var(--fg-soft)]">
            <div>© 2026 محرّك الـLeads. كل الحقوق محفوظة.</div>
            <div className="flex items-center gap-3">
              <a href="#" className="hover:text-[var(--fg-muted)]"><Github className="h-4 w-4" /></a>
              <a href="#" className="hover:text-[var(--fg-muted)]"><Twitter className="h-4 w-4" /></a>
              <a href="#" className="hover:text-[var(--fg-muted)]"><Linkedin className="h-4 w-4" /></a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

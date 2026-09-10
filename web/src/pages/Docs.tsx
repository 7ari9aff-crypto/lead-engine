import { Link } from "wouter";
import {
  Zap,
  ArrowLeft,
  BookOpen,
  Rocket,
  Bot,
  Database,
  KeyRound,
  Mail,
  Code2,
  Github,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Terminal,
  Cpu,
  Webhook,
  Plug,
} from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

const SECTIONS = [
  {
    id: "quickstart",
    icon: Rocket,
    title: "البداية السريعة",
    color: "var(--accent)",
  },
  {
    id: "agent",
    icon: Bot,
    title: "المساعد الذكي",
    color: "var(--info)",
  },
  {
    id: "keys",
    icon: KeyRound,
    title: "مفاتيح API",
    color: "var(--warn)",
  },
  {
    id: "verify",
    icon: Mail,
    title: "فحص الإيميل",
    color: "var(--success)",
  },
  {
    id: "data",
    icon: Database,
    title: "مزامنة البيانات",
    color: "var(--info)",
  },
  {
    id: "api",
    icon: Code2,
    title: "API & MCP",
    color: "var(--accent)",
  },
];

const QUICKSTART = [
  {
    step: 1,
    title: "أضف مفاتيح API",
    desc: "روح لتبويب المفاتيح وأضف GEMINI_API_KEY و TAVILY_API_KEY على الأقل.",
  },
  {
    step: 2,
    title: "افتح المساعد",
    desc: "روح للمساعد الذكي واطلب: «اعمل ليد جينيراشن في الرياض»",
  },
  {
    step: 3,
    title: "راجع النتائج",
    desc: "النتائج تظهر في تبويب النتائج — صدّرها CSV أو زامن مع Supabase.",
  },
];

const CODE_API = `# Chat with the agent
curl -X POST https://lead-engine-gamma-silk.vercel.app/api/chat \\
  -H "Content-Type: application/json" \\
  -d '{
    "messages": [
      {"role": "user", "content": "اعمل ليد جينيراشن في جدة"}
    ]
  }'

# Run a benchmark
curl -X POST https://lead-engine-gamma-silk.vercel.app/benchmark/run \\
  -H "Content-Type: application/json" \\
  -d '{"icp": "v0_saudi_dental", "dry_run": true}'

# Get leads
curl https://lead-engine-gamma-silk.vercel.app/leads?limit=50

# Verify an email
curl -X POST https://lead-engine-gamma-silk.vercel.app/verify-email \\
  -H "Content-Type: application/json" \\
  -d '{"email": "info@clinic.sa"}'`;

const CODE_MCP = `# Add to claude_desktop_config.json
{
  "mcpServers": {
    "lead-engine": {
      "url": "https://lead-engine-gamma-silk.vercel.app/mcp",
      "transport": "http"
    }
  }
}`;

const fadeUp = {
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0, transition: { duration: 0.4 } },
  viewport: { once: true },
};

export function DocsPage() {
  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-40 glass border-b border-[var(--border)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link href="/welcome" className="flex items-center gap-2">
            <div className="h-9 w-9 rounded-lg bg-[image:var(--gradient)] shadow-md flex items-center justify-center">
              <Zap className="h-5 w-5 text-white" />
            </div>
            <span className="font-bold text-base gradient-text">محرّك الـLeads</span>
          </Link>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/">
              <ArrowLeft className="h-4 w-4" />
              اللوحة
            </Link>
          </Button>
          <ThemeToggle />
        </div>
      </header>

      {/* HERO */}
      <section className="pt-16 pb-12 px-4 sm:px-6 lg:px-8 text-center">
        <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
          <Badge variant="accent" className="mb-4">
            <BookOpen className="h-3 w-3" />
            التوثيق
          </Badge>
        </motion.div>
        <motion.h1
          {...fadeUp}
          initial={fadeUp.initial}
          whileInView={fadeUp.whileInView}
          viewport={fadeUp.viewport}
          className="text-4xl sm:text-5xl font-bold mb-4"
        >
          كل اللي تحتاج <span className="gradient-text">تعرفه</span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="text-lg text-[var(--fg-muted)] max-w-2xl mx-auto"
        >
          من البداية السريعة إلى الـAPI — كل شيء هنا.
        </motion.p>
      </section>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-20 grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-8">
        {/* Sidebar nav */}
        <aside className="hidden lg:block">
          <div className="sticky top-24 space-y-1">
            {SECTIONS.map((s) => {
              const Icon = s.icon;
              return (
                <a
                  key={s.id}
                  href={`#${s.id}`}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-[var(--fg-muted)] hover:bg-[var(--bg-hover)] hover:text-[var(--fg)] transition-colors"
                >
                  <Icon className="h-4 w-4" />
                  {s.title}
                </a>
              );
            })}
          </div>
        </aside>

        {/* Content */}
        <div className="space-y-16 min-w-0">
          {/* Quickstart */}
          <section id="quickstart" className="scroll-mt-20">
            <SectionHeader icon={Rocket} title="البداية السريعة" color="var(--accent)" />
            <p className="text-[var(--fg-muted)] mb-6">
              3 خطوات فقط وتبدأ تولّد leads في أقل من 5 دقائق.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {QUICKSTART.map((s, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.1 }}
                >
                  <Card>
                    <CardContent className="p-6">
                      <div className="h-8 w-8 rounded-full bg-[var(--accent-soft)] text-[var(--accent)] flex items-center justify-center font-bold mb-3">
                        {s.step}
                      </div>
                      <h3 className="font-semibold mb-2">{s.title}</h3>
                      <p className="text-sm text-[var(--fg-muted)]">{s.desc}</p>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>
          </section>

          {/* Agent */}
          <section id="agent" className="scroll-mt-20">
            <SectionHeader icon={Bot} title="المساعد الذكي" color="var(--info)" />
            <p className="text-[var(--fg-muted)] mb-6">
              المساعد يستخدم Gemini ويقدر ينفّذ أوامر معقدة بأدوات داخلية.
            </p>

            <Card>
              <CardHeader>
                <CardTitle>
                  <Terminal className="h-4 w-4" />
                  أمثلة أوامر
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3 text-sm">
                  <ExampleCmd cmd="اعمل ليد جينيراشن في الرياض" desc="يولّد حتى 30 lead في 5 دقائق" />
                  <ExampleCmd cmd="افحص الإيميل: info@clinic.sa" desc="يرجع DELIVERABLE/RISKY/CATCH_ALL/INVALID" />
                  <ExampleCmd cmd="اعرض آخر 10 leads" desc="يجيب البيانات من Supabase" />
                  <ExampleCmd cmd="إيش حالة النظام؟" desc="يلخّص الـproviders والـjobs" />
                  <ExampleCmd cmd="شغّل pipeline بالـdry-run" desc="يختبر بدون ما يكلّف رصيد" />
                </ul>
              </CardContent>
            </Card>
          </section>

          {/* Keys */}
          <section id="keys" className="scroll-mt-20">
            <SectionHeader icon={KeyRound} title="مفاتيح API" color="var(--warn)" />
            <p className="text-[var(--fg-muted)] mb-6">
              المفاتيح تتخزن في <code>.env</code> خارج Git وتدخل حيّز التنفيذ فورًا.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">مطلوبة للبداية</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 text-sm">
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />
                      <code className="text-xs" dir="ltr">GEMINI_API_KEY</code>
                    </li>
                    <li className="flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />
                      <code className="text-xs" dir="ltr">TAVILY_API_KEY</code>
                    </li>
                  </ul>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">اختيارية لكن محسّنة</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 text-sm">
                    <li className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-[var(--warn)]" />
                      <code className="text-xs" dir="ltr">APOLLO_API_KEY</code>
                      <span className="text-xs text-[var(--fg-soft)]">— إثراء بيانات</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-[var(--warn)]" />
                      <code className="text-xs" dir="ltr">HUNTER_API_KEY</code>
                      <span className="text-xs text-[var(--fg-soft)]">— فحص إيميل</span>
                    </li>
                    <li className="flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 text-[var(--warn)]" />
                      <code className="text-xs" dir="ltr">SUPABASE_*</code>
                      <span className="text-xs text-[var(--fg-soft)]">— مزامنة</span>
                    </li>
                  </ul>
                </CardContent>
              </Card>
            </div>

            <div className="mt-4 rounded-xl border border-[var(--accent)]/30 bg-[var(--accent-soft)] p-4 flex gap-3">
              <Sparkles className="h-5 w-5 text-[var(--accent)] shrink-0 mt-0.5" />
              <div className="text-sm">
                <strong className="text-[var(--fg)]">Multi-key rotation:</strong> الصق أكثر من مفتاح في نفس الخانة (كل واحد في سطر) — النظام يدوّر بينهم تلقائيًا.
              </div>
            </div>
          </section>

          {/* Verify */}
          <section id="verify" className="scroll-mt-20">
            <SectionHeader icon={Mail} title="فحص الإيميل" color="var(--success)" />
            <p className="text-[var(--fg-muted)] mb-6">
              النظام يكشف بدقة 5-حالات منفصلة، خاصة catch-all.
            </p>
            <div className="space-y-2.5">
              {[
                { code: "DELIVERABLE", label: "قابل للتوصيل", color: "var(--success)", desc: "يوجد فعلاً ويستقبل" },
                { code: "RISKY", label: "معرّض للخطر", color: "var(--warn)", desc: "role account أو disposable" },
                { code: "CATCH_ALL", label: "Catch-All", color: "var(--warn)", desc: "الدومين يستقبل كل الإيميلات" },
                { code: "INVALID", label: "غير صالح", color: "var(--danger)", desc: "لا يوجد أو معطّل" },
                { code: "UNKNOWN", label: "غير معروف", color: "var(--fg-soft)", desc: "تعذّر التحقق" },
              ].map((s) => (
                <div key={s.code} className="flex items-start gap-3 p-3 rounded-lg bg-[var(--bg-soft)] border border-[var(--border-soft)]">
                  <code className="text-xs font-mono px-2 py-0.5 rounded shrink-0" style={{ background: `color-mix(in srgb, ${s.color} 15%, transparent)`, color: s.color }} dir="ltr">
                    {s.code}
                  </code>
                  <div>
                    <div className="font-medium text-sm" style={{ color: s.color }}>{s.label}</div>
                    <div className="text-xs text-[var(--fg-muted)] mt-0.5">{s.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Data */}
          <section id="data" className="scroll-mt-20">
            <SectionHeader icon={Database} title="مزامنة البيانات" color="var(--info)" />
            <p className="text-[var(--fg-muted)] mb-6">
              الـleads تتخزن في SQLite محلي + Supabase اختياري. الـCSV export متاح دائمًا.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    <Cpu className="h-4 w-4" />
                    قاعدة البيانات المحلية
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-[var(--fg-muted)] space-y-2">
                  <p>SQLite في <code dir="ltr" className="text-xs">/var/task/data/lead_engine.sqlite3</code></p>
                  <p>يحتوي على كل الـjobs والـleads والـusage.</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    <Plug className="h-4 w-4" />
                    Supabase (اختياري)
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-[var(--fg-muted)] space-y-2">
                  <p>أضف <code dir="ltr" className="text-xs">SUPABASE_URL</code> و <code dir="ltr" className="text-xs">SUPABASE_SERVICE_KEY</code></p>
                  <p>ثم اضغط «مزامنة» في تبويب المهام.</p>
                </CardContent>
              </Card>
            </div>
          </section>

          {/* API */}
          <section id="api" className="scroll-mt-20">
            <SectionHeader icon={Code2} title="API & MCP" color="var(--accent)" />
            <p className="text-[var(--fg-muted)] mb-6">
              كل شيء REST. الـMCP server متاح على <code dir="ltr" className="text-xs">/mcp</code> لأي عميل.
            </p>

            <Card>
              <CardHeader>
                <CardTitle>
                  <Terminal className="h-4 w-4" />
                  أمثلة API
                </CardTitle>
                <CardDescription>كل endpoint متاح على نفس الـdomain</CardDescription>
              </CardHeader>
              <CardContent>
                <pre className="text-xs bg-[var(--bg)] p-4 rounded-lg overflow-x-auto" dir="ltr">
                  {CODE_API}
                </pre>
              </CardContent>
            </Card>

            <Card className="mt-4">
              <CardHeader>
                <CardTitle>
                  <Webhook className="h-4 w-4" />
                  MCP Server (Claude / Cursor)
                </CardTitle>
                <CardDescription>خلّي Claude يستخدم المحرك كأداة</CardDescription>
              </CardHeader>
              <CardContent>
                <pre className="text-xs bg-[var(--bg)] p-4 rounded-lg overflow-x-auto" dir="ltr">
                  {CODE_MCP}
                </pre>
              </CardContent>
            </Card>
          </section>

          {/* CTA */}
          <Card className="bg-[image:var(--gradient)] border-0">
            <CardContent className="p-8 text-center text-white">
              <Github className="h-12 w-12 mx-auto mb-3" />
              <h2 className="text-2xl font-bold mb-2">الكود مفتوح المصدر</h2>
              <p className="opacity-90 mb-4">ساهم أو Fork أو اعمل Issue على GitHub</p>
              <Button variant="secondary" asChild className="!bg-white !text-[var(--accent)]">
                <a href="https://github.com/7ari9aff-crypto/lead-engine" target="_blank" rel="noopener">
                  <Github className="h-4 w-4" />
                  GitHub
                </a>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function SectionHeader({ icon: Icon, title, color }: { icon: any; title: string; color: string }) {
  return (
    <div className="flex items-center gap-3 mb-2">
      <div
        className="h-10 w-10 rounded-lg flex items-center justify-center"
        style={{
          background: `color-mix(in srgb, ${color} 15%, transparent)`,
          color: color,
        }}
      >
        <Icon className="h-5 w-5" />
      </div>
      <h2 className="text-2xl font-bold">{title}</h2>
    </div>
  );
}

function ExampleCmd({ cmd, desc }: { cmd: string; desc: string }) {
  return (
    <li className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-[var(--bg-hover)] transition-colors">
      <code className="flex-1 text-xs bg-[var(--bg)] px-2 py-1 rounded" dir="ltr">{cmd}</code>
      <span className="text-xs text-[var(--fg-soft)] whitespace-nowrap">{desc}</span>
    </li>
  );
}

import { Link } from "wouter";
import {
  Zap,
  Check,
  X,
  Sparkles,
  ArrowLeft,
  HelpCircle,
  Star,
  Building2,
  Rocket,
  Crown,
} from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

const PLANS = [
  {
    icon: Rocket,
    name: "تجربة",
    price: "0",
    period: "30 يوم",
    desc: "لكل اللي يجرّبون لاول مرة",
    color: "var(--info)",
    cta: "ابدأ التجربة",
    href: "/chat",
    features: [
      { text: "30 lead مجاناً", ok: true },
      { text: "5 مزوّدين أساسيين", ok: true },
      { text: "فحص إيميل 5-حالات", ok: true },
      { text: "لوحة تحكم كاملة", ok: true },
      { text: "بدون بطاقة بنكية", ok: true },
      { text: "بدون توثيق شخصي", ok: true },
      { text: "معدل غير محدود", ok: false },
      { text: "مزامنة Supabase", ok: false },
      { text: "دعم مخصص", ok: false },
    ],
  },
  {
    icon: Star,
    name: "Pro",
    price: "199",
    period: "ريال / شهر",
    desc: "للشركات اللي تولّد leads بانتظام",
    color: "var(--accent)",
    cta: "ابدأ Pro",
    href: "/chat",
    featured: true,
    features: [
      { text: "500 lead شهرياً", ok: true },
      { text: "كل المزوّدين (18+)", ok: true },
      { text: "Multi-key rotation (5 keys)", ok: true },
      { text: "مزامنة Supabase", ok: true },
      { text: "Agent mode + custom ICP", ok: true },
      { text: "تقارير + CSV export", ok: true },
      { text: "دعم بريد خلال 24 ساعة", ok: true },
      { text: "MCP server access", ok: true },
      { text: "دعم مخصص 1-1", ok: false },
    ],
  },
  {
    icon: Crown,
    name: "Business",
    price: "تواصل",
    period: "مخصص",
    desc: "للفرق الكبيرة والاحتياجات المؤسسية",
    color: "var(--warn)",
    cta: "تواصل معنا",
    href: "mailto:7amedadel7@gmail.com",
    features: [
      { text: "leads غير محدود", ok: true },
      { text: "كل المزوّدين + مخصص", ok: true },
      { text: "Multi-tenant + RBAC", ok: true },
      { text: "SSO + audit logs", ok: true },
      { text: "API access (unlimited)", ok: true },
      { text: "Self-hosted option", ok: true },
      { text: "SLA 99.9%", ok: true },
      { text: "دعم 24/7 + account manager", ok: true },
      { text: "تدريب فريق + onboarding", ok: true },
    ],
  },
];

const FAQ = [
  {
    q: "هل أحتاج بطاقة بنكية للتجربة؟",
    a: "لا. الـ 30 lead مجاناً بدون أي بطاقة بنكية. كل اللي تحتاجه مفاتيح API للمزوّدين (معظمها في طبقة مجانية).",
  },
  {
    q: "هل يدعم PDPL السعودي؟",
    a: "نعم. البوابة القانونية (Legal Gate) PDPL-aware. يحجب أي شركة بدون إجماع قانوني قبل ما توصل لسجلّك. default-deny.",
  },
  {
    q: "إيش الفرق بين Pro و Business؟",
    a: "Pro للشركات الفردية والشركات الصغيرة. Business للفرق الكبيرة اللي تحتاج multi-tenant، SSO، SLA، ودعم مخصص.",
  },
  {
    q: "هل يمكنني الإلغاء في أي وقت؟",
    a: "نعم، بدون أي التزامات. الإلغاء من داخل اللوحة، بدون تواصل مع الدعم.",
  },
  {
    q: "إيش جودة الـ leads؟",
    a: "نظام Dedup 3-مراحل (exact → identity → fuzzy) + Email verification 5-حالات + Score 0-100. الـ lead يُقبل فقط إذا اجتاز كل الفلاتر.",
  },
  {
    q: "هل يمكنني تجربة نسخة Business قبل ما ألتزم؟",
    a: "بالتأكيد. تواصل معنا ونعمل demo مخصص لاحتياجاتك + trial 14 يوم لكل المزايا.",
  },
];

const COMPARISON = [
  { feature: "عدد الـ leads شهرياً", trial: "30", pro: "500", business: "غير محدود" },
  { feature: "عدد المزوّدين", trial: "5", pro: "18+", business: "18+ + مخصص" },
  { feature: "Multi-key rotation", trial: "—", pro: "✓", business: "✓" },
  { feature: "مزامنة Supabase", trial: "—", pro: "✓", business: "✓" },
  { feature: "تقارير + CSV", trial: "✓", pro: "✓", business: "✓" },
  { feature: "MCP server", trial: "—", pro: "✓", business: "✓" },
  { feature: "Multi-tenant", trial: "—", pro: "—", business: "✓" },
  { feature: "SSO", trial: "—", pro: "—", business: "✓" },
  { feature: "SLA", trial: "—", pro: "—", business: "99.9%" },
  { feature: "دعم", trial: "Community", pro: "24 ساعة", business: "24/7 + مخصص" },
];

const fadeUp = {
  initial: { opacity: 0, y: 20 },
  whileInView: { opacity: 1, y: 0, transition: { duration: 0.5 } },
  viewport: { once: true },
};

export function PricingPage() {
  return (
    <div className="min-h-screen">
      {/* Simple nav */}
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
        </div>
      </header>

      {/* HERO */}
      <section className="pt-20 pb-12 px-4 sm:px-6 lg:px-8 text-center">
        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
          <Badge variant="accent" className="mb-4">
            <Sparkles className="h-3 w-3" />
            تسعير شفّاف
          </Badge>
        </motion.div>
        <motion.h1 {...fadeUp} initial={fadeUp.initial} whileInView={fadeUp.whileInView} viewport={fadeUp.viewport} className="text-4xl sm:text-5xl font-bold mb-4">
          ادفع مقابل <span className="gradient-text">ما تستخدمه فقط</span>
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          className="text-lg text-[var(--fg-muted)] max-w-2xl mx-auto"
        >
          3 باقات تناسب كل مرحلة — من التجربة الأولى إلى الفريق المؤسسي.
        </motion.p>
      </section>

      {/* PLANS */}
      <section className="pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-4">
          {PLANS.map((p, i) => {
            const Icon = p.icon;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
              >
                <Card
                  className={`h-full relative ${p.featured ? "border-[var(--accent)] shadow-2xl" : ""}`}
                >
                  {p.featured && (
                    <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                      <Badge variant="accent" className="text-[10px]">
                        <Star className="h-3 w-3 fill-current" />
                        الأكثر شعبية
                      </Badge>
                    </div>
                  )}
                  <div className="p-6">
                    <div className="flex items-center gap-3 mb-4">
                      <div
                        className="h-11 w-11 rounded-lg flex items-center justify-center"
                        style={{
                          background: `color-mix(in srgb, ${p.color} 15%, transparent)`,
                          color: p.color,
                        }}
                      >
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="text-lg font-bold">{p.name}</h3>
                        <p className="text-xs text-[var(--fg-muted)]">{p.desc}</p>
                      </div>
                    </div>

                    <div className="mb-6">
                      <div className="flex items-baseline gap-1">
                        {p.price === "تواصل" ? (
                          <span className="text-2xl font-bold">{p.price}</span>
                        ) : (
                          <>
                            <span className="text-4xl font-bold">{p.price}</span>
                            <span className="text-sm text-[var(--fg-muted)]"> {p.period}</span>
                          </>
                        )}
                      </div>
                    </div>

                    <Button
                      variant={p.featured ? "primary" : "outline"}
                      className="w-full mb-6"
                      asChild
                    >
                      <Link href={p.href}>
                        {p.cta}
                        <ArrowLeft className="h-4 w-4" />
                      </Link>
                    </Button>

                    <ul className="space-y-2.5">
                      {p.features.map((f, j) => (
                        <li key={j} className="flex items-start gap-2 text-sm">
                          {f.ok ? (
                            <Check className="h-4 w-4 text-[var(--success)] shrink-0 mt-0.5" />
                          ) : (
                            <X className="h-4 w-4 text-[var(--fg-soft)] shrink-0 mt-0.5" />
                          )}
                          <span className={f.ok ? "" : "text-[var(--fg-soft)] line-through"}>
                            {f.text}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </Card>
              </motion.div>
            );
          })}
        </div>
      </section>

      {/* COMPARISON TABLE */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 bg-[var(--bg-soft)]/30">
        <div className="max-w-5xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-10">
            <h2 className="text-2xl sm:text-3xl font-bold mb-2">مقارنة تفصيلية</h2>
            <p className="text-[var(--fg-muted)]">كل اللي تحتاج تعرفه قبل ما تختار</p>
          </motion.div>

          <Card>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-[var(--bg-soft)]">
                    <th className="text-right p-3 font-semibold">الميزة</th>
                    <th className="text-center p-3 font-semibold">تجربة</th>
                    <th className="text-center p-3 font-semibold bg-[var(--accent-soft)] text-[var(--accent-hover)]">Pro</th>
                    <th className="text-center p-3 font-semibold">Business</th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARISON.map((c, i) => (
                    <tr key={i} className="border-b border-[var(--border-soft)]">
                      <td className="p-3 text-[var(--fg-muted)]">{c.feature}</td>
                      <td className="p-3 text-center text-[var(--fg)]">{c.trial}</td>
                      <td className="p-3 text-center font-medium bg-[var(--accent-soft)]/30">{c.pro}</td>
                      <td className="p-3 text-center text-[var(--fg)]">{c.business}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-3xl mx-auto">
          <motion.div {...fadeUp} className="text-center mb-10">
            <Badge variant="default" className="mb-4">
              <HelpCircle className="h-3 w-3" />
              أسئلة شائعة
            </Badge>
            <h2 className="text-2xl sm:text-3xl font-bold">إجابات مباشرة</h2>
          </motion.div>

          <div className="space-y-3">
            {FAQ.map((f, i) => (
              <motion.details
                key={i}
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.05 }}
                className="rounded-xl border border-[var(--border)] bg-[var(--bg-elev)] overflow-hidden group"
              >
                <summary className="cursor-pointer p-4 flex items-center justify-between hover:bg-[var(--bg-hover)] transition-colors">
                  <span className="font-medium text-sm">{f.q}</span>
                  <span className="text-[var(--fg-soft)] text-lg group-open:rotate-45 transition-transform">+</span>
                </summary>
                <div className="p-4 pt-0 text-sm text-[var(--fg-muted)] leading-relaxed border-t border-[var(--border-soft)]">
                  {f.a}
                </div>
              </motion.details>
            ))}
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <Building2 className="h-12 w-12 text-[var(--accent)] mx-auto mb-4" />
          <h2 className="text-3xl font-bold mb-4">جاهز تبدأ؟</h2>
          <p className="text-[var(--fg-muted)] mb-8 max-w-xl mx-auto">
            30 lead مجاناً، بدون بطاقة بنكية. جرّب بنفسك.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button variant="primary" size="lg" asChild>
              <Link href="/chat">
                ابدأ التجربة المجانية
                <ArrowLeft className="h-4 w-4" />
              </Link>
            </Button>
            <Button variant="ghost" size="lg" asChild>
              <Link href="/welcome">الرجوع للصفحة الرئيسية</Link>
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

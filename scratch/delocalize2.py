import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

def update_file(path, replacements):
    full_path = os.path.join(r"d:\lead generation", path)
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    orig = content
    for old, new in replacements:
        if old not in content:
            print(f"[WARN] In {path}: Target string not found: {old[:50]}")
        content = content.replace(old, new)
    
    if content != orig:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Updated {path}")
    else:
        print(f"[NOOP] No changes for {path}")

# Auth.tsx
update_file("web/src/pages/Auth.tsx", [
    (
        """<div className="relative text-white/60 text-[11px]">صنع في السعودية</div>""",
        """<div className="relative text-white/60 text-[11px]">Lead Engine · B2B Intelligence</div>"""
    )
])

# Footer.tsx
update_file("web/src/components/layout/Footer.tsx", [
    (
        """صنع بـ <Heart className="h-3 w-3 text-[var(--danger)] fill-current" /> في السعودية""",
        """صنع بـ <Heart className="h-3 w-3 text-[var(--danger)] fill-current" /> لرواد الأعمال وفرق النمو"""
    )
])

# Chat.tsx
update_file("web/src/pages/Chat.tsx", [
    (
        """  { icon: Globe2, title: "توليد leads في الرياض", prompt: "اعمل ليد جينيراشن في الرياض — عيادات أسنان" },""",
        """  { icon: Globe2, title: "استقطاب شركات B2B", prompt: "ابحث عن شركات برمجيات B2B واستخرج صناع القرار المؤهلين" },"""
    ),
    (
        """  { icon: Mail, title: "فحص إيميل", prompt: "افحص الإيميل: info@clinic.sa" },""",
        """  { icon: Mail, title: "فحص إيميل", prompt: "افحص الإيميل: info@example.com" },"""
    )
])

# Icp.tsx
update_file("web/src/pages/Icp.tsx", [
    (
        """placeholder="مثال: التركيز على المراكز والعيادات الخاصة ذات العلامة التجارية المستقلة…" """,
        """placeholder="مثال: التركيز على الشركات والمنشآت المستقلة ذات الحضور الرقمي النشط…" """
    )
])

# Config.tsx
update_file("web/src/pages/Config.tsx", [
    (
        """<h3 className="text-sm font-bold">سياسة جمع البيانات — {legal.country === "SA" ? "السعودية" : "عامة"}</h3>""",
        """<h3 className="text-sm font-bold">سياسة جمع البيانات — {legal.country === "SA" ? "نطاق محلي" : "عام وعالمي"}</h3>"""
    )
])

print("Additional UI delocalizations applied.")

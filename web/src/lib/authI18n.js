// Copy for the signed-out pages (Login / Register / ForgotPassword / ResetPassword).
// These routes render OUTSIDE LeadEngineProvider, so they cannot use its `t()`; they
// read the same persisted language key instead, so the choice made on the login
// page carries into the app and vice versa. Arabic is the default, like the app.

export const LANG_KEY = "leadengine.lang";

export const authDict = {
  "login.title": { ar: "أهلاً بعودتك", en: "Welcome back" },
  "login.subtitle": { ar: "سجّل الدخول إلى حسابك", en: "Log in to your account" },
  "login.submit": { ar: "تسجيل الدخول", en: "Log in" },
  "login.submitting": { ar: "جارٍ تسجيل الدخول…", en: "Logging in..." },
  "login.error": { ar: "البريد الإلكتروني أو كلمة المرور غير صحيحة", en: "Invalid email or password" },
  "login.noAccount": { ar: "ليس لديك حساب؟", en: "Don't have an account?" },
  "login.createOne": { ar: "أنشئ حسابًا", en: "Create one" },

  "register.title": { ar: "أنشئ حسابك", en: "Create your account" },
  "register.subtitle": { ar: "سجّل للبدء", en: "Sign up to get started" },
  "register.submit": { ar: "إنشاء الحساب", en: "Create account" },
  "register.submitting": { ar: "جارٍ إنشاء الحساب…", en: "Creating account..." },
  "register.mismatch": { ar: "كلمتا المرور غير متطابقتين", en: "Passwords do not match" },
  "register.failed": { ar: "تعذّر إنشاء الحساب", en: "Registration failed" },
  "register.confirmEmail": {
    ar: "تم إنشاء الحساب. تحقّق من بريدك لتأكيده ثم سجّل الدخول.",
    en: "Account created — check your email to confirm, then log in.",
  },
  "register.haveAccount": { ar: "لديك حساب بالفعل؟", en: "Already have an account?" },
  "register.logIn": { ar: "سجّل الدخول", en: "Log in" },

  "forgot.title": { ar: "إعادة تعيين كلمة المرور", en: "Reset password" },
  "forgot.subtitle": { ar: "سنرسل لك رابطًا لإعادة تعيينها", en: "We'll send you a link to reset it" },
  "forgot.emailLabel": { ar: "البريد الإلكتروني", en: "Email address" },
  "forgot.submit": { ar: "أرسل رابط إعادة التعيين", en: "Send reset link" },
  "forgot.submitting": { ar: "جارٍ الإرسال…", en: "Sending..." },
  "forgot.sent": {
    ar: "إن كان هناك حساب بهذا البريد فستصلك رسالة برابط إعادة التعيين قريبًا.",
    en: "If an account exists with that email, you'll receive a password reset link shortly.",
  },
  "forgot.back": { ar: "العودة إلى تسجيل الدخول", en: "Back to log in" },

  "reset.title": { ar: "كلمة مرور جديدة", en: "New password" },
  "reset.subtitle": { ar: "أدخل كلمة المرور الجديدة أدناه", en: "Enter your new password below" },
  "reset.newLabel": { ar: "كلمة المرور الجديدة", en: "New Password" },
  "reset.submit": { ar: "إعادة تعيين كلمة المرور", en: "Reset password" },
  "reset.submitting": { ar: "جارٍ إعادة التعيين…", en: "Resetting..." },
  "reset.failed": { ar: "تعذّرت إعادة تعيين كلمة المرور", en: "Failed to reset password" },
  "reset.invalidTitle": { ar: "رابط غير صالح", en: "Invalid reset link" },
  "reset.invalidSubtitle": {
    ar: "رابط إعادة تعيين كلمة المرور مفقود أو غير صالح",
    en: "This password reset link is missing or invalid",
  },
  "reset.invalidBody": {
    ar: "يبدو أن الرابط الذي استخدمته غير مكتمل. اطلب رسالة إعادة تعيين جديدة.",
    en: "The link you used appears to be incomplete. Please request a new password reset email.",
  },
  "reset.requestNew": { ar: "اطلب رابطًا جديدًا", en: "Request a new link" },

  "field.email": { ar: "البريد الإلكتروني", en: "Email" },
  "field.password": { ar: "كلمة المرور", en: "Password" },
  "field.confirm": { ar: "تأكيد كلمة المرور", en: "Confirm Password" },
  "field.forgot": { ar: "نسيت كلمة المرور؟", en: "Forgot password?" },
  "lang.switch": { ar: "English", en: "العربية" },
};

export const normalizeLang = (v) => (v === "en" ? "en" : "ar");

export function readLang(storage) {
  try {
    return normalizeLang((storage ?? globalThis.localStorage)?.getItem(LANG_KEY));
  } catch {
    return "ar";
  }
}

export const makeAuthT = (lang) => (key) => {
  const entry = authDict[key];
  return entry ? entry[lang] || entry.ar : key;
};

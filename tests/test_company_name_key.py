"""name_key(): Arabic-aware company matching key.

Two jobs, both tested: (1) merge spellings of the SAME business, (2) never merge
DIFFERENT businesses (a wrong merge silently destroys a lead; a missed merge
only costs a duplicate row)."""
import pytest

from domain.acquisition.company import name_key as k


@pytest.mark.parametrize("a,b", [
    # real rows from production (public.companies)
    ("Al Zahra Dental Center (@alzahradental)", "Al Zahra Dental Clinic"),
    ("Al-Othaim Commercial Markets", "Othaim Commercial Markets"),
    # Arabic spelling variants
    ("مركز أبراج الطبي", "مركز ابراج الطبى"),
    ("عيادة الزهراء لطب الأسنان", "عياده الزهراء للاسنان"),
    ("عيادات إشراقة", "عيادات اشراقه"),
    ("الدكتور أحمد", "دكتور احمد"),
    ("مجمع د. سمير عباس", "مجمع دكتور سمير عباس"),
    ("Dr. Amal Dental Care", "Doctor Amal Dental"),
    # tashkeel / tatweel / Arabic-Indic digits
    ("مَرْكَز النُّخْبَة", "مركز النخبة"),
    ("مركـــز النخبة", "مركز النخبة"),
    ("عيادة ٢٤ ساعة", "عيادة 24 ساعة"),
    # word order and punctuation must not matter
    ("Smile Dental, Riyadh!", "riyadh smile dental"),
])
def test_same_business_same_key(a, b):
    assert k(a) and k(a) == k(b), (k(a), k(b))


@pytest.mark.parametrize("a,b", [
    # different CITY = different branch/business: must stay separate
    ("Elite Dental Clinic Jeddah", "Elite Dental Riyadh"),
    # different distinctive word
    ("Al Zahra Dental Clinic", "Al Noor Dental Clinic"),
    ("عيادة الزهراء", "عيادة النور"),
    ("Dr. Amal Dental Care", "Dr. Sara Dental Care"),
    ("الدكتور أحمد", "الدكتور محمد"),
    # numbers are distinctive
    ("عيادة 24 ساعة", "عيادة 12 ساعة"),
])
def test_different_business_different_key(a, b):
    assert k(a) != k(b), (k(a), k(b))


@pytest.mark.parametrize("generic", [
    "Dental Clinic", "Dental Services", "عيادة أسنان", "مركز طبي", "", None, "   ", "()",
])
def test_purely_generic_names_never_match_by_name(generic):
    """'' means 'do not match by name' - otherwise every 'Dental Clinic' in the
    country would collapse into one company."""
    assert k(generic) == ""


def test_key_is_deterministic_and_idempotent():
    name = "عيادة الزهراء لطب الأسنان (فرع الرياض)"
    assert k(name) == k(name) == k(k(name))


def test_parenthetical_branch_or_handle_is_ignored():
    assert k("Fresh Smile (Riyadh Branch)") == k("Fresh Smile")
    assert k("زهرة (@zahra_clinic)") == k("زهرة")


def test_article_is_not_stripped_from_short_words():
    # "ال" only stripped when >=3 chars follow, so real short names survive
    assert k("علا") != ""
    # a bare "ال" is kept (conservative: keeping a token can only PREVENT a merge)
    assert k("ال") == "ال"


# ---------------------------------------------------------------------------
# name_match_is_safe: a name alone must never override a conflicting domain/city
# ---------------------------------------------------------------------------
from domain.acquisition.company import name_match_is_safe as safe  # noqa: E402


def test_conflicting_domains_veto_a_name_match():
    # Real prod case: three different "best dental clinic in Riyadh" sites
    assert safe("okclinics.sa", "ddclinic.sa") is False
    assert safe("jeddahdental.sa", "kch.sa") is False


def test_same_or_missing_domain_allows_name_match():
    assert safe("alzahradental.com", "alzahradental.com") is True
    assert safe("alzahradental.com", None) is True      # existing row has no domain
    assert safe(None, "alzahradental.com") is True
    assert safe(None, None) is True


def test_domain_comparison_is_case_insensitive():
    assert safe("Example.COM", "example.com") is True


def test_conflicting_cities_veto_a_name_match():
    assert safe(None, None, "Jeddah", "Riyadh") is False
    assert safe(None, None, "Riyadh", " riyadh ") is True
    assert safe(None, None, "Riyadh", None) is True


def test_domain_veto_beats_city_agreement():
    assert safe("a.com", "b.com", "Riyadh", "Riyadh") is False

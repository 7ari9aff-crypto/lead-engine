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
    # geography and marketing filler are not part of the identity
    ("Dentakay Dental Clinic in Riyadh, Saudi Arabia", "Dentakay Dental Clinic"),
    ("Best Dental Clinic Fresh Smile", "Fresh Smile Dental"),
    ("عيادة الزهراء الرياض", "عيادة الزهراء"),
])
def test_same_business_same_key(a, b):
    assert k(a) and k(a) == k(b), (k(a), k(b))


@pytest.mark.parametrize("a,b", [
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


def test_city_is_not_in_the_key_so_branches_are_separated_by_the_veto():
    """Design decision: the key ignores the city (the same business is written
    with and without it). Two branches in different cities share a key and are
    kept apart by name_match_is_safe, which vetoes a city conflict."""
    a, b = "Elite Dental Clinic Jeddah", "Elite Dental Riyadh"
    assert k(a) == k(b) == "elite"
    assert safe(None, None, "Jeddah", "Riyadh") is False


def test_page_titles_do_not_leak_geography_or_marketing_into_the_key():
    # real production titles from the V6 companies table
    key = k("dental clinic - obeid specialized hospital")
    assert key == "obeid"
    key = k("best dental hospital in saudi arabia | dental clinics in riyadh, dammam, jeddah")
    assert key == ""            # nothing distinctive: must not match by name


# ---------------------------------------------------------------------------
# business_name_from_title: the domain is the witness; never guess a position
# ---------------------------------------------------------------------------
from domain.acquisition.company import business_name_from_title as bn  # noqa: E402


@pytest.mark.parametrize("title,domain,expected", [
    # brand is LAST (legacy clean_title kept the first part and lost it)
    ("dental care services in saudi arabia | kimshealth", "kimshealth.co", "kimshealth"),
    # brand is FIRST
    ("Alpha Dental Clinic | Best Dental", "alpha-dental.sa", "Alpha Dental Clinic"),
    ("kharsa clinics: patient-centered dental excellence | your trusted specialists",
     "kharsaclinics.com", "kharsa clinics"),
])
def test_segment_confirmed_by_domain_is_kept(title, domain, expected):
    assert bn(title, domain) == expected


@pytest.mark.parametrize("title,domain", [
    ("Dental Clinic - Obeid Specialized Hospital", "obeidhospitals.com"),  # 'obeid' != label
    ("أفضل عيادات أسنان بالرياض - اوكي كلينيك", "okclinics.sa"),            # Arabic vs Latin domain
    ("What is The Best Dental Clinic in Jeddah 2026 ? : How to Choose", "magrabihealth.com"),
    ("Dental Clinic in Riyadh : r/Riyadh", None),
    ("Time: 10:30 Clinic", "clinic.com"),     # generic domain label must not match anything
    ("Just One Segment", "segment.com"),
    ("", "x.com"),
])
def test_unconfirmed_titles_are_returned_unchanged_never_guessed(title, domain):
    assert bn(title, domain) == " ".join(title.split())


def test_two_competing_segments_means_no_decision():
    assert bn("Noor Clinic | Noor Clinic Riyadh", "noorclinic.sa") == "Noor Clinic | Noor Clinic Riyadh"


@pytest.mark.parametrize("title", [
    "دليلك الشامل لاختيار أفضل مركز اسنان بالرياض في 2025",   # an article, only a year left
    "Top 10 Dental Clinics 2026",
    "، ؟ ؛",
])
def test_a_bare_number_or_punctuation_is_not_a_business_name(title):
    assert k(title) == ""


def test_arabic_punctuation_is_not_part_of_the_key():
    assert "،" not in k("سنان لطب الأسنان ، عيادة أسنان بمفهوم مختلف في الرياض")

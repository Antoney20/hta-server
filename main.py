#!/usr/bin/env python
"""
Seed script for InterventionProposal
Run: python seed.py
"""

import os
import sys
import django
from datetime import date

# ── Django setup ──────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hta.settings") 
django.setup()

from users.models import InterventionProposal  # noqa: E402

# ── Sample data ───────────────────────────────────────────────────────────────
INTERVENTIONS = [
    {
        "name": " Test user ",
        "phone": "+254711000001",
        "email": "amina.odhiambo@kemri.org",
        "profession": "Epidemiologist",
        "organization": "KEMRI",
        "county": "Kisumu",
        "intervention_name": "Community-Based Malaria Rapid Diagnostic Testing",
        "intervention_type": "Preventive",
        "beneficiary": "Children under 5 and pregnant women in Kisumu East sub-county",
        "justification": (
            "Malaria remains the leading cause of outpatient visits in Kisumu, accounting for 38% "
            "of under-5 deaths. Current diagnosis relies on clinical judgment, leading to over-treatment "
            "and drug resistance."
        ),
        "expected_impact": (
            "Reduce malaria mortality in under-5s by 30% within 2 years through accurate diagnosis "
            "and prompt treatment at community level."
        ),
        "additional_info": "Aligned with Kenya Malaria Strategy 2019–2023. WHO-approved RDTs to be used.",
        "signature": " Test user bo",
        "date": date(2024, 3, 10),
        "reference_number": "IP-2024-0001",
        "is_public": True,
    },
    {
        "name": "Test JJ",
        "phone": "+254722000002",
        "email": "j.mutua@health.go.ke",
        "profession": "Public Health Officer",
        "organization": "Machakos County Health Department",
        "county": "Machakos",
        "intervention_name": "Integrated Management of Acute Malnutrition (IMAM) Scale-Up",
        "intervention_type": "Curative",
        "beneficiary": "Acutely malnourished children 6–59 months in Machakos and Makueni counties",
        "justification": (
            "GAM prevalence in the region stands at 14.2%, above the 10% emergency threshold. "
            "Current IMAM sites cover only 40% of the target population."
        ),
        "expected_impact": (
            "Increase IMAM coverage from 40% to 80%, reducing SAM case fatality rate below 5% "
            "and preventing an estimated 1,200 child deaths annually."
        ),
        "additional_info": "Ready-to-use therapeutic food (RUTF) supply chain already established via WFP.",
        "signature": "James Mutua",
        "date": date(2024, 4, 5),
        "reference_number": "IP-2024-0002",
        "is_public": True,
    },
    {
        "name": "Test tt",
        "phone": "+254733000003",
        "email": "grace.njeri@amref.org",
        "profession": "Nurse Midwife",
        "organization": "Amref Health Africa",
        "county": "Turkana",
        "intervention_name": "Emergency Obstetric and Newborn Care (EmONC) Strengthening",
        "intervention_type": "Curative",
        "beneficiary": "Pregnant women and newborns in Turkana North and South sub-counties",
        "justification": (
            "Turkana has a maternal mortality ratio of 880/100,000 live births, more than double "
            "the national average. Only 28% of births occur in health facilities with skilled attendants."
        ),
        "expected_impact": (
            "Increase skilled birth attendance to 60%, reduce maternal mortality by 40%, "
            "and cut neonatal mortality by 35% within 3 years."
        ),
        "additional_info": "Includes training of 120 skilled birth attendants and equipping 15 EmONC sites.",
        "signature": "Grace Njeri",
        "date": date(2024, 2, 18),
        "reference_number": "IP-2024-0003",
        "is_public": True,
    },
    {
        "name": " Test user ",
        "phone": "+254744000004",
        "email": "s.koech@uonbi.ac.ke",
        "profession": "Cardiologist",
        "organization": "University of Nairobi / KNH",
        "county": "Nairobi",
        "intervention_name": "Hypertension Screening and Treatment Cascade in Urban Informal Settlements",
        "intervention_type": "Preventive",
        "beneficiary": "Adults aged 30+ in Kibera, Mathare, and Korogocho informal settlements",
        "justification": (
            "NCDs now account for 27% of all deaths in Kenya. Hypertension prevalence in urban slums "
            "is estimated at 35% with less than 10% of cases controlled. Stroke is a top-5 cause of "
            "hospital mortality at KNH."
        ),
        "expected_impact": (
            "Screen 50,000 adults, link 80% of hypertensives to care, and achieve BP control in "
            "50% of those on treatment, reducing stroke incidence by 20%."
        ),
        "additional_info": "Task-shifting model using CHWs trained in BP measurement and medication adherence.",
        "signature": " Test user ",
        "date": date(2024, 5, 1),
        "reference_number": "IP-2024-0004",
        "is_public": True,
    },
    {
        "name": "Fatuma Hassan",
        "phone": "+254755000005",
        "email": "fatuma.hassan@iom.int",
        "profession": "Public Health Specialist",
        "organization": "IOM Kenya",
        "county": "Garissa",
        "intervention_name": "Cholera Prevention and WASH in Dadaab Refugee Complex",
        "intervention_type": "Preventive",
        "beneficiary": "320,000 refugees and host community members in Dadaab camps",
        "justification": (
            "Dadaab has experienced 3 cholera outbreaks in the past 5 years. Overcrowding and "
            "inadequate sanitation facilities (1 latrine per 80 people) sustain transmission cycles."
        ),
        "expected_impact": (
            "Reduce cholera attack rate by 70%, achieve a latrine coverage of 1 per 20 persons, "
            "and increase safe water access to 95% of camp residents."
        ),
        "additional_info": "OCV (Oral Cholera Vaccine) mass campaign planned alongside WASH improvements.",
        "signature": "Fatuma Hassan",
        "date": date(2024, 1, 22),
        "reference_number": "IP-2024-0005",
        "is_public": True,
    },
    {
        "name": " Test user ",
        "phone": "+254766000006",
        "email": "p.otieno@nascop.go.ke",
        "profession": "Infectious Disease Physician",
        "organization": "NASCOP",
        "county": "Homa Bay",
        "intervention_name": "HIV Index Testing and Same-Day ART Initiation",
        "intervention_type": "Curative",
        "beneficiary": "HIV-positive adults and their sexual contacts in Homa Bay County",
        "justification": (
            "Homa Bay has the highest HIV prevalence in Kenya at 19.6%. Only 68% of PLHIV know "
            "their status and ART coverage stands at 74%, below the 95-95-95 targets."
        ),
        "expected_impact": (
            "Identify 15,000 new positives through index testing, initiate 90% on ART same-day, "
            "and achieve viral suppression in 85% of those on treatment within 18 months."
        ),
        "additional_info": "Leverages existing HIV facility networks and community health volunteers.",
        "signature": " Test user ",
        "date": date(2024, 3, 30),
        "reference_number": "IP-2024-0006",
        "is_public": True,
    },
    {
        "name": "Lucy Wanjiku",
        "phone": "+254777000007",
        "email": "lucy.w@moh.go.ke",
        "profession": "Mental Health Nurse",
        "organization": "Ministry of Health – Mental Health Unit",
        "county": "Nakuru",
        "intervention_name": "Integrated Mental Health into Primary Care (mhGAP)",
        "intervention_type": "Curative",
        "beneficiary": "People with depression, psychosis, and substance use disorders in Nakuru County",
        "justification": (
            "Mental disorders account for 13% of the global disease burden yet Kenya allocates less "
            "than 1% of health budget to mental health. In Nakuru, suicide rates increased 40% post-COVID."
        ),
        "expected_impact": (
            "Train 200 primary care workers in mhGAP, increase mental health service uptake by 50%, "
            "and reduce suicide attempts by 25% over 2 years."
        ),
        "additional_info": "WHO mhGAP Intervention Guide v2.0 to be adapted for Kenyan context.",
        "signature": "Lucy Wanjiku",
        "date": date(2024, 6, 12),
        "reference_number": "IP-2024-0007",
        "is_public": True,
    },
    {
        "name": " Test user" ,
        "phone": "+254788000008",
        "email": "h.abdi@who.int",
        "profession": "TB Specialist",
        "organization": "WHO Kenya Country Office",
        "county": "Mombasa",
        "intervention_name": "TB Active Case Finding in High-Burden Urban Wards",
        "intervention_type": "Preventive",
        "beneficiary": "Residents of Kisauni, Likoni, and Changamwe wards in Mombasa",
        "justification": (
            "Kenya is a high TB burden country with a case detection rate of 74%. Urban density "
            "and HIV co-infection (TB/HIV co-infection rate 26%) in coastal counties drive ongoing transmission."
        ),
        "expected_impact": (
            "Detect 3,000 additional TB cases through community screening, achieve 90% treatment "
            "success rate, and reduce community TB prevalence by 20% in 3 years."
        ),
        "additional_info": "GeneXpert mobile units and digital X-ray to be deployed for screening.",
        "signature": " Test user" ,
        "date": date(2024, 4, 20),
        "reference_number": "IP-2024-0008",
        "is_public": True,
    },
    {
        "name": "Esther ",
        "phone": "+254799000009",
        "email": "e.chebet@unicef.org",
        "profession": "Immunization Specialist",
        "organization": "UNICEF Kenya",
        "county": "West Pokot",
        "intervention_name": "Immunization Outreach for Zero-Dose Children",
        "intervention_type": "Preventive",
        "beneficiary": "Children under 2 years in hard-to-reach pastoralist communities in West Pokot",
        "justification": (
            "West Pokot has a DPT3 coverage of 48%, leaving over 15,000 children unimmunized annually. "
            "Measles outbreaks occurred in 2021 and 2023, killing 34 children."
        ),
        "expected_impact": (
            "Reach 12,000 zero-dose children, increase DPT3 coverage to 80%, and prevent "
            "an estimated 400 vaccine-preventable deaths over 2 years."
        ),
        "additional_info": "Solar-powered cold chain and camel-mounted vaccine carriers for nomadic reach.",
        "signature": "Esther Chebet",
        "date": date(2024, 5, 17),
        "reference_number": "IP-2024-0009",
        "is_public": True,
    },
    {
        "name": " Test user ",
        "phone": "+254700000010",
        "email": "mercy.akinyi@jhpiego.org",
        "profession": "Obstetrician-Gynecologist",
        "organization": "Jhpiego Kenya",
        "county": "Siaya",
        "intervention_name": "Cervical Cancer Screen-and-Treat using VIA/Cryotherapy",
        "intervention_type": "Preventive",
        "beneficiary": "Women aged 25–49 in Siaya and Bondo sub-counties",
        "justification": (
            "Cervical cancer is the leading cancer killer of Kenyan women. Siaya has high HIV "
            "prevalence (17%), which increases cervical cancer risk 5-fold. Screening coverage is below 10%."
        ),
        "expected_impact": (
            "Screen 40,000 women, treat 95% of eligible precancerous lesions same-day, "
            "and reduce late-stage cervical cancer diagnoses by 35% within 4 years."
        ),
        "additional_info": "HPV self-sampling to be piloted for women unable to attend clinics.",
        "signature": " Test user ",
        "date": date(2024, 6, 3),
        "reference_number": "IP-2024-0010",
        "is_public": True,
    },
]



def seed():
    created = 0
    skipped = 0

    for data in INTERVENTIONS:
        ref = data["reference_number"]
        if InterventionProposal.objects.filter(reference_number=ref).exists():
            print(f"  [skip]  {ref} already exists")
            skipped += 1
            continue

        InterventionProposal.objects.create(**data)
        print(f"  [ok]    {ref} — {data['intervention_name']}")
        created += 1

    print(f"\nDone. Created: {created}  |  Skipped: {skipped}")


if __name__ == "__main__":
    seed()
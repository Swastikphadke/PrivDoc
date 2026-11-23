"""Deterministic Synthetic Corpus Generator for PrivyDoc Evaluation.

Strict Privacy & Integrity Invariants:
1. Zero real personal data: all names, emails, phones, and IDs are purely synthetic.
2. Deterministic generation with fixed random seed (seed=42).
3. Exact character offsets validated against generated canonical text.
4. Partitions corpus into:
   - dev (10 documents)
   - val (7 documents)
   - test (8 documents - quarantined held-out test split)
5. Generates both document.txt and document.pdf (via PyMuPDF).
"""

import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import fitz  # PyMuPDF

SEED = 42
random.seed(SEED)

BASE_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BASE_DIR / "datasets" / "evaluation"


def _add_annotation(
    full_text: str,
    search_str: str,
    category: str,
    entity_id: str,
    annotations: List[Dict[str, Any]],
    start_search: int = 0,
) -> int:
    """Find search_str in full_text starting at start_search, add annotation, and return end index."""
    idx = full_text.find(search_str, start_search)
    if idx == -1:
        raise ValueError(f"Annotation target '{search_str}' not found in document text after pos {start_search}.")
    end_idx = idx + len(search_str)
    annotations.append({
        "start": idx,
        "end": end_idx,
        "text": search_str,
        "type": category,
        "entity_id": entity_id,
    })
    return end_idx


def generate_document_spec(doc_num: int) -> Tuple[str, List[Dict[str, Any]], str]:
    """Generate deterministic synthetic document text and exact gold annotations."""
    annotations: List[Dict[str, Any]] = []
    
    # 25 Distinct Scenarios covering all 8 difficulty classes
    if doc_num == 1:
        # Class 1: Clean business report
        title = "Aegis Cybernetics - Q3 Internal Security Audit"
        p1 = "The annual cybersecurity posture assessment was conducted by Lead Auditor Elena Vance (elena.vance@aegis-cyber.internal)."
        p2 = "For urgent escalation, contact Deputy Director Marcus Sterling at +1 (555) 234-8901 or marcus.sterling@aegis-cyber.internal."
        p3 = "All incident reports must be routed to Security Operations Center, Building 4, Cyber City, Bangalore 560066."
        text = f"{title}\n\n{p1}\n\n{p2}\n\n{p3}\n"
        
        _add_annotation(text, "Elena Vance", "PERSON", "ent_p1", annotations)
        _add_annotation(text, "elena.vance@aegis-cyber.internal", "EMAIL", "ent_e1", annotations)
        _add_annotation(text, "Marcus Sterling", "PERSON", "ent_p2", annotations)
        _add_annotation(text, "+1 (555) 234-8901", "PHONE", "ent_ph1", annotations)
        _add_annotation(text, "marcus.sterling@aegis-cyber.internal", "EMAIL", "ent_e2", annotations)
        _add_annotation(text, "Building 4, Cyber City, Bangalore 560066", "ADDRESS", "ent_a1", annotations)
        desc = "Class 1: Clean business report with standard PII"

    elif doc_num == 2:
        # Class 2: Headers and Signatures
        h1 = "MEMORANDUM\n"
        h2 = "TO: Dr. Aris Thorne <aris.thorne@quantum-lab.org>\n"
        h3 = "FROM: Priya Nair, Head of Operations\n"
        h4 = "DATE: November 15, 2024\nSUBJECT: Lab Access Clearance"
        body = "\nPlease verify lab access badge for new research fellow Vikram Seth."
        sig = "\n\nApproved by:\nDr. Aris Thorne\nDirector of Research\nPhone: +91 98765 43210"
        text = h1 + h2 + h3 + h4 + body + sig
        
        pos = _add_annotation(text, "Dr. Aris Thorne", "PERSON", "ent_thorne", annotations)
        _add_annotation(text, "aris.thorne@quantum-lab.org", "EMAIL", "ent_thorne_email", annotations)
        _add_annotation(text, "Priya Nair", "PERSON", "ent_priya", annotations)
        _add_annotation(text, "Vikram Seth", "PERSON", "ent_vikram", annotations)
        _add_annotation(text, "Dr. Aris Thorne", "PERSON", "ent_thorne", annotations, start_search=pos)
        _add_annotation(text, "+91 98765 43210", "PHONE", "ent_thorne_ph", annotations)
        desc = "Class 2: Header and signature memo with repeated executive identity"

    elif doc_num == 3:
        # Class 3: Initials and Name Variants
        p1 = "Project Falcon was inaugurated by Richa Sharma in September."
        p2 = "Initial design specifications were compiled by R. Sharma along with senior engineer J. Miller."
        p3 = "For clarification regarding the schematics, consult Ms. Sharma or Dr. John Miller."
        text = f"PROJECT FALCON OVERSIGHT\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Richa Sharma", "PERSON", "ent_sharma", annotations)
        _add_annotation(text, "R. Sharma", "PERSON", "ent_sharma", annotations)
        _add_annotation(text, "J. Miller", "PERSON", "ent_miller", annotations)
        _add_annotation(text, "Ms. Sharma", "PERSON", "ent_sharma", annotations)
        _add_annotation(text, "Dr. John Miller", "PERSON", "ent_miller", annotations)
        desc = "Class 3: Name variants, titles, and initial-to-surname aliases"

    elif doc_num == 4:
        # Class 4: International Phones & Mixed Formats
        h = "GLOBAL INCIDENT RESPONSE DIRECTORY\n\n"
        l1 = "US Desk: Officer Liam Vance, Tel: +1 (555) 349-2018\n"
        l2 = "India Desk: Inspector Devika Patel, Tel: +91 98450 12345\n"
        l3 = "UK Operations: Arthur Pendelton, Direct: +44 20 7946 0912\n"
        l4 = "Emergency Landline: (080) 2345-6789 (Ext: 401)\n"
        text = h + l1 + l2 + l3 + l4
        
        _add_annotation(text, "Liam Vance", "PERSON", "ent_liam", annotations)
        _add_annotation(text, "+1 (555) 349-2018", "PHONE", "ent_ph_us", annotations)
        _add_annotation(text, "Devika Patel", "PERSON", "ent_devika", annotations)
        _add_annotation(text, "+91 98450 12345", "PHONE", "ent_ph_in", annotations)
        _add_annotation(text, "Arthur Pendelton", "PERSON", "ent_arthur", annotations)
        _add_annotation(text, "+44 20 7946 0912", "PHONE", "ent_ph_uk", annotations)
        _add_annotation(text, "(080) 2345-6789", "PHONE", "ent_ph_land", annotations)
        desc = "Class 4: International phone numbers across diverse country codes"

    elif doc_num == 5:
        # Class 5: Complex Addresses
        h = "CORPORATE REAL ESTATE DISCLOSURE\n\n"
        p1 = "Primary HQ: Plot 42, Electronic City Phase 1, Hosur Road, Bangalore 560100, Karnataka."
        p2 = "Registered Branch: Suite 800, 1200 Innovation Way, Austin, TX 78701, United States."
        p3 = "Facility Manager: S. K. Narayanan (sk.narayanan@corp-re.test)."
        text = f"{h}{p1}\n{p2}\n\n{p3}\n"
        
        _add_annotation(text, "Plot 42, Electronic City Phase 1, Hosur Road, Bangalore 560100", "ADDRESS", "ent_addr_hq", annotations)
        _add_annotation(text, "Suite 800, 1200 Innovation Way, Austin, TX 78701", "ADDRESS", "ent_addr_us", annotations)
        _add_annotation(text, "S. K. Narayanan", "PERSON", "ent_skn", annotations)
        _add_annotation(text, "sk.narayanan@corp-re.test", "EMAIL", "ent_skn_mail", annotations)
        desc = "Class 5: Complex multi-line postal and campus addresses"

    elif doc_num == 6:
        # Class 6: Employee IDs & Account Numbers
        h = "FINANCIAL ACCESS LOG - RESTRICTED\n\n"
        r1 = "Account Holder: Rahul Verma | Account ID: ACCT-904820 | Employee ID: EMP-7741\n"
        r2 = "Secondary Signer: Kavita Krishnan | Account ID: ACCT-904821 | Employee ID: EMP-8812\n"
        r3 = "Tax ID: ABCDE1234F | Routing: 021000021"
        text = h + r1 + r2 + r3
        
        _add_annotation(text, "Rahul Verma", "PERSON", "ent_rahul", annotations)
        _add_annotation(text, "ACCT-904820", "ID_LIKE", "ent_acc1", annotations)
        _add_annotation(text, "EMP-7741", "ID_LIKE", "ent_emp1", annotations)
        _add_annotation(text, "Kavita Krishnan", "PERSON", "ent_kavita", annotations)
        _add_annotation(text, "ACCT-904821", "ID_LIKE", "ent_acc2", annotations)
        _add_annotation(text, "EMP-8812", "ID_LIKE", "ent_emp2", annotations)
        _add_annotation(text, "ABCDE1234F", "ID_LIKE", "ent_tax1", annotations)
        desc = "Class 6: Employee badges, account numbers, and tax identifiers"

    elif doc_num == 7:
        # Class 7: Borderline Numeric (Dates, amounts, percentages vs IDs/phones)
        h = "QUARTERLY EARNINGS CALL BRIEFING - 2024-10-31\n\n"
        p1 = "Revenue reached $14,250,000.00 representing an increase of 18.5% over prior fiscal period."
        p2 = "Lead Analyst: Natasha Romanoff (ID: EMP-1092) reachable at ext 402 or +1 (555) 901-4432."
        p3 = "Total active subscriptions: 45,210 units recorded as of 2024-09-30."
        text = f"{h}{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Natasha Romanoff", "PERSON", "ent_natasha", annotations)
        _add_annotation(text, "EMP-1092", "ID_LIKE", "ent_emp_nat", annotations)
        _add_annotation(text, "+1 (555) 901-4432", "PHONE", "ent_ph_nat", annotations)
        desc = "Class 7: Borderline numeric contexts (currency, percentages, dates vs phone/ID)"

    elif doc_num == 8:
        # Class 8: Dense Tabular Data / Roster
        h = "INCIDENT RESPONSE TEAM ROSTER\n"
        t_header = "ID       NAME             ROLE            EMAIL                      PHONE\n"
        row1 = "EMP-101  Anand Sen        Lead Engineer   anand.sen@cyber-unit.test   +91 99001 12233\n"
        row2 = "EMP-102  Sarah Connor     SecOps Analyst  sarah.c@cyber-unit.test     +1 (555) 782-9011\n"
        row3 = "EMP-103  Rohan Mehra      Incident Spec   rohan.m@cyber-unit.test     +91 98800 44556\n"
        text = h + t_header + row1 + row2 + row3
        
        _add_annotation(text, "EMP-101", "ID_LIKE", "ent_e101", annotations)
        _add_annotation(text, "Anand Sen", "PERSON", "ent_anand", annotations)
        _add_annotation(text, "anand.sen@cyber-unit.test", "EMAIL", "ent_anand_m", annotations)
        _add_annotation(text, "+91 99001 12233", "PHONE", "ent_anand_p", annotations)
        
        _add_annotation(text, "EMP-102", "ID_LIKE", "ent_e102", annotations)
        _add_annotation(text, "Sarah Connor", "PERSON", "ent_sarah", annotations)
        _add_annotation(text, "sarah.c@cyber-unit.test", "EMAIL", "ent_sarah_m", annotations)
        _add_annotation(text, "+1 (555) 782-9011", "PHONE", "ent_sarah_p", annotations)
        
        _add_annotation(text, "EMP-103", "ID_LIKE", "ent_e103", annotations)
        _add_annotation(text, "Rohan Mehra", "PERSON", "ent_rohan", annotations)
        _add_annotation(text, "rohan.m@cyber-unit.test", "EMAIL", "ent_rohan_m", annotations)
        _add_annotation(text, "+91 98800 44556", "PHONE", "ent_rohan_p", annotations)
        desc = "Class 8: Multi-column formatted table with aligned PII"

    elif doc_num == 9:
        # Subclass: Ambiguity Defense (John Smith vs James Smith vs J. Smith)
        p1 = "Case 901 involves John Smith and his brother James Smith."
        p2 = "A statement was recorded by J. Smith regarding property at 14 Elm Street, Springfield."
        p3 = "Inquiries directed to contact: smith.case@legal-group.test or +1 (555) 881-2299."
        text = f"LEGAL INVESTIGATION DOSSIER\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "John Smith", "PERSON", "ent_jsmith1", annotations)
        _add_annotation(text, "James Smith", "PERSON", "ent_jsmith2", annotations)
        _add_annotation(text, "J. Smith", "PERSON", "ent_jsmith_ambig", annotations)
        _add_annotation(text, "14 Elm Street, Springfield", "ADDRESS", "ent_elm", annotations)
        _add_annotation(text, "smith.case@legal-group.test", "EMAIL", "ent_smith_mail", annotations)
        _add_annotation(text, "+1 (555) 881-2299", "PHONE", "ent_smith_ph", annotations)
        desc = "Ambiguity Defense: Common surnames and ambiguous initial J. Smith"

    elif doc_num == 10:
        # Subclass: Surname-Sharing Defense (Sunil Kumar vs Anil Kumar)
        p1 = "Partnership deed executed between Sunil Kumar and Anil Kumar."
        p2 = "Operations supervised by Sunil Kumar at 102 MG Road, Bangalore 560001."
        p3 = "Notice served via email: sunil.k@venture-tech.test or +91 97410 99881."
        text = f"COMMERCIAL CONTRACT AGREEMENT\n\n{p1}\n{p2}\n{p3}\n"
        
        pos = _add_annotation(text, "Sunil Kumar", "PERSON", "ent_sunil", annotations)
        _add_annotation(text, "Anil Kumar", "PERSON", "ent_anil", annotations)
        _add_annotation(text, "Sunil Kumar", "PERSON", "ent_sunil", annotations, start_search=pos)
        _add_annotation(text, "102 MG Road, Bangalore 560001", "ADDRESS", "ent_mg_road", annotations)
        _add_annotation(text, "sunil.k@venture-tech.test", "EMAIL", "ent_sunil_mail", annotations)
        _add_annotation(text, "+91 97410 99881", "PHONE", "ent_sunil_ph", annotations)
        desc = "Surname Defense: Sunil Kumar and Anil Kumar must never be merged"

    elif doc_num == 11:
        # Val 1: Clean Consulting Summary
        p1 = "Consulting report authored by Maya Angelou for client Zenith Systems."
        p2 = "Primary liaison: Gordon Freeman (gordon.freeman@blackmesa.test, +1 (555) 434-1122)."
        p3 = "Office located at 88 Silicon Boulevard, San Jose, CA 95112."
        text = f"EXECUTIVE ADVISORY MEMO\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Maya Angelou", "PERSON", "ent_maya", annotations)
        _add_annotation(text, "Gordon Freeman", "PERSON", "ent_gordon", annotations)
        _add_annotation(text, "gordon.freeman@blackmesa.test", "EMAIL", "ent_gordon_mail", annotations)
        _add_annotation(text, "+1 (555) 434-1122", "PHONE", "ent_gordon_ph", annotations)
        _add_annotation(text, "88 Silicon Boulevard, San Jose, CA 95112", "ADDRESS", "ent_sanjose", annotations)
        desc = "Validation 1: Clean advisory memo with single-occurrence entities"

    elif doc_num == 12:
        # Val 2: Title and Surname Linkage
        p1 = "Chief Medical Officer Dr. Evelyn Cross presented clinical trial results."
        p2 = "According to Dr. Cross, adverse reactions remained below 0.1% across all test groups."
        p3 = "Trial coordinator: Evelyn Cross, Clinical Research Wing, Tel: +1 (555) 670-3344."
        text = f"CLINICAL OVERSIGHT COMMITTEE\n\n{p1}\n{p2}\n{p3}\n"
        
        pos1 = _add_annotation(text, "Dr. Evelyn Cross", "PERSON", "ent_cross", annotations)
        pos2 = _add_annotation(text, "Dr. Cross", "PERSON", "ent_cross", annotations, start_search=pos1)
        _add_annotation(text, "Evelyn Cross", "PERSON", "ent_cross", annotations, start_search=pos2)
        _add_annotation(text, "+1 (555) 670-3344", "PHONE", "ent_cross_ph", annotations)
        desc = "Validation 2: Medical title variant linkage"

    elif doc_num == 13:
        # Val 3: Account Security Alert
        p1 = "Security notification for user Karthik Subramanian (EMP-4102)."
        p2 = "Suspicious login attempt detected on account ACCT-551029 from IP 192.168.1.10."
        p3 = "Contact Security Desk immediately at +91 99112 33445 or karthik.s@fintech-vault.test."
        text = f"SECURITY ALERT DISPATCH\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Karthik Subramanian", "PERSON", "ent_karthik", annotations)
        _add_annotation(text, "EMP-4102", "ID_LIKE", "ent_emp_k", annotations)
        _add_annotation(text, "ACCT-551029", "ID_LIKE", "ent_acc_k", annotations)
        _add_annotation(text, "+91 99112 33445", "PHONE", "ent_karthik_ph", annotations)
        _add_annotation(text, "karthik.s@fintech-vault.test", "EMAIL", "ent_karthik_mail", annotations)
        desc = "Validation 3: Financial security alert with account IDs"

    elif doc_num == 14:
        # Val 4: Complex Multi-Recipient Email Header
        h = "From: Alice Walker <alice.w@solaris-defense.test>\n"
        h += "To: Bob Martin <bob.m@solaris-defense.test>, Carol Danvers <carol.d@solaris-defense.test>\n"
        h += "Date: Tue, 12 Nov 2024 10:14:00 +0000\n"
        h += "Subject: Mission Debrief\n\n"
        body = "Please review attached flight logs for aircraft AC-902."
        sig = "\n\nRegards,\nAlice Walker\nCell: +1 (555) 129-8765"
        text = h + body + sig
        
        pos = _add_annotation(text, "Alice Walker", "PERSON", "ent_alice", annotations)
        _add_annotation(text, "alice.w@solaris-defense.test", "EMAIL", "ent_alice_mail", annotations)
        _add_annotation(text, "Bob Martin", "PERSON", "ent_bob", annotations)
        _add_annotation(text, "bob.m@solaris-defense.test", "EMAIL", "ent_bob_mail", annotations)
        _add_annotation(text, "Carol Danvers", "PERSON", "ent_carol", annotations)
        _add_annotation(text, "carol.d@solaris-defense.test", "EMAIL", "ent_carol_mail", annotations)
        _add_annotation(text, "Alice Walker", "PERSON", "ent_alice", annotations, start_search=pos)
        _add_annotation(text, "+1 (555) 129-8765", "PHONE", "ent_alice_ph", annotations)
        desc = "Validation 4: Multi-recipient formal email headers"

    elif doc_num == 15:
        # Val 5: International Real Estate Lease
        p1 = "Commercial Lease between Landlord Bruce Wayne and Tenant Clark Kent."
        p2 = "Premises: 1007 Mountain Drive, Gotham City, NJ 07101."
        p3 = "Inquiries directed to Property Manager: D. Prince (+1 (555) 777-8899, prince.d@wayne-ent.test)."
        text = f"COMMERCIAL LEASE AGREEMENT\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Bruce Wayne", "PERSON", "ent_bruce", annotations)
        _add_annotation(text, "Clark Kent", "PERSON", "ent_clark", annotations)
        _add_annotation(text, "1007 Mountain Drive, Gotham City, NJ 07101", "ADDRESS", "ent_gotham", annotations)
        _add_annotation(text, "D. Prince", "PERSON", "ent_prince", annotations)
        _add_annotation(text, "+1 (555) 777-8899", "PHONE", "ent_prince_ph", annotations)
        _add_annotation(text, "prince.d@wayne-ent.test", "EMAIL", "ent_prince_mail", annotations)
        desc = "Validation 5: Lease agreement with property address"

    elif doc_num == 16:
        # Val 6: Indian Banking Transaction Receipt
        p1 = "Transaction Acknowledgement: Beneficiary Rajesh Sharma (Account: ACCT-1100229)."
        p2 = "Branch: Connaught Place, New Delhi 110001 | IFSC: SBIN0001234."
        p3 = "Support Phone: +91 98100 22334 | Email: helpdesk@bank-corp.test."
        text = f"ELECTRONIC FUNDS TRANSFER ADVICE\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Rajesh Sharma", "PERSON", "ent_rajesh", annotations)
        _add_annotation(text, "ACCT-1100229", "ID_LIKE", "ent_acc_r", annotations)
        _add_annotation(text, "Connaught Place, New Delhi 110001", "ADDRESS", "ent_delhi_addr", annotations)
        _add_annotation(text, "+91 98100 22334", "PHONE", "ent_bank_ph", annotations)
        _add_annotation(text, "helpdesk@bank-corp.test", "EMAIL", "ent_bank_mail", annotations)
        desc = "Validation 6: Bank transfer advice with Indian postal and account code"

    elif doc_num == 17:
        # Val 7: Academic Research Grant Notification
        p1 = "Principal Investigator Prof. Albus Dumbledore awarded Grant GR-9941."
        p2 = "Co-Investigator: Minerva McGonagall (Department of Physics, Hogwarts Academy)."
        p3 = "Communications: m.mcgonagall@hogwarts.test or Tel: +44 131 496 0123."
        text = f"FACULTY RESEARCH GRANT CONFERRAL\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Prof. Albus Dumbledore", "PERSON", "ent_albus", annotations)
        _add_annotation(text, "Minerva McGonagall", "PERSON", "ent_minerva", annotations)
        _add_annotation(text, "m.mcgonagall@hogwarts.test", "EMAIL", "ent_minerva_mail", annotations)
        _add_annotation(text, "+44 131 496 0123", "PHONE", "ent_minerva_ph", annotations)
        desc = "Validation 7: Academic grant with professor titles and UK telephone"

    elif doc_num == 18:
        # Test 1 (Held Out): Executive Contract
        p1 = "This Executive Employment Agreement is entered into between NovaTech Corp and Zachary Taylor."
        p2 = "Employee ID assigned: EMP-3049 | Work Email: zachary.taylor@novatech-corp.test."
        p3 = "Emergency contact: Tel: +1 (555) 602-9911 | Residence: 450 Beacon Street, Boston, MA 02115."
        text = f"EXECUTIVE EMPLOYMENT AGREEMENT\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Zachary Taylor", "PERSON", "ent_ztaylor", annotations)
        _add_annotation(text, "EMP-3049", "ID_LIKE", "ent_emp_zt", annotations)
        _add_annotation(text, "zachary.taylor@novatech-corp.test", "EMAIL", "ent_zt_mail", annotations)
        _add_annotation(text, "+1 (555) 602-9911", "PHONE", "ent_zt_ph", annotations)
        _add_annotation(text, "450 Beacon Street, Boston, MA 02115", "ADDRESS", "ent_boston_addr", annotations)
        desc = "Test 1 (Held-out): Full executive contract profile"

    elif doc_num == 19:
        # Test 2 (Held Out): Multi-Variant Name Memorandum
        p1 = "Director Meera Swaminathan delivered keynote address on artificial intelligence."
        p2 = "According to M. Swaminathan, algorithmic accountability must be established across all nodes."
        p3 = "Feedback can be sent to Ms. Swaminathan at meera.s@ai-ethics-foundation.test."
        text = f"SYMPOSIUM KEYNOTE TRANSCRIPT\n\n{p1}\n{p2}\n{p3}\n"
        
        pos1 = _add_annotation(text, "Meera Swaminathan", "PERSON", "ent_meera", annotations)
        pos2 = _add_annotation(text, "M. Swaminathan", "PERSON", "ent_meera", annotations, start_search=pos1)
        _add_annotation(text, "Ms. Swaminathan", "PERSON", "ent_meera", annotations, start_search=pos2)
        _add_annotation(text, "meera.s@ai-ethics-foundation.test", "EMAIL", "ent_meera_mail", annotations)
        desc = "Test 2 (Held-out): Triple-variant name resolution across initial and title"

    elif doc_num == 20:
        # Test 3 (Held Out): International Supply Chain Audit
        p1 = "Logistics Coordinator Deepak Chopra conducted site review at Sector 18, Gurugram 122015, Haryana."
        p2 = "Vendor liaison: Hans Gruber (gruber.h@nakatomi-freight.test, Phone: +49 30 123456)."
        p3 = "Shipment Tracking Code: TRK-981023 | Customer Service Hotline: +91 98111 22233."
        text = f"GLOBAL SUPPLY CHAIN AUDIT CERTIFICATE\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Deepak Chopra", "PERSON", "ent_deepak", annotations)
        _add_annotation(text, "Sector 18, Gurugram 122015", "ADDRESS", "ent_gurgaon_addr", annotations)
        _add_annotation(text, "Hans Gruber", "PERSON", "ent_hans", annotations)
        _add_annotation(text, "gruber.h@nakatomi-freight.test", "EMAIL", "ent_hans_mail", annotations)
        _add_annotation(text, "+49 30 123456", "PHONE", "ent_hans_ph", annotations)
        _add_annotation(text, "TRK-981023", "ID_LIKE", "ent_trk_id", annotations)
        _add_annotation(text, "+91 98111 22233", "PHONE", "ent_cs_ph", annotations)
        desc = "Test 3 (Held-out): German and Indian cross-border logistics"

    elif doc_num == 21:
        # Test 4 (Held Out): Financial Fraud Case Summary
        p1 = "Investigation into unauthorized withdrawals from Account ACCT-882194."
        p2 = "Account holder: Jennifer Lawrence | Authorized Representative: J. Lawrence."
        p3 = "Investigator: Special Agent Fox Mulder (f.mulder@fbi-bureau.test, +1 (555) 992-0044)."
        text = f"FINANCIAL CRIMES ENFORCEMENT SUMMARY\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "ACCT-882194", "ID_LIKE", "ent_acc_jlaw", annotations)
        pos = _add_annotation(text, "Jennifer Lawrence", "PERSON", "ent_jlaw", annotations)
        _add_annotation(text, "J. Lawrence", "PERSON", "ent_jlaw", annotations, start_search=pos)
        _add_annotation(text, "Fox Mulder", "PERSON", "ent_mulder", annotations)
        _add_annotation(text, "f.mulder@fbi-bureau.test", "EMAIL", "ent_mulder_mail", annotations)
        _add_annotation(text, "+1 (555) 992-0044", "PHONE", "ent_mulder_ph", annotations)
        desc = "Test 4 (Held-out): Fraud summary with initial linkage"

    elif doc_num == 22:
        # Test 5 (Held Out): Borderline Financial Statistics with PII
        p1 = "Fiscal year 2024 operating margin closed at 24.8% with capital expenditure totaling $2,450,000.00."
        p2 = "Report certified by Chief Financial Officer Neil Armstrong (EMP-1969)."
        p3 = "Direct telephone: +1 (555) 867-5309 | Official correspondence: n.armstrong@apollo-corp.test."
        text = f"ANNUAL COMPLIANCE AND FINANCIAL ATTESTATION\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Neil Armstrong", "PERSON", "ent_neil", annotations)
        _add_annotation(text, "EMP-1969", "ID_LIKE", "ent_neil_emp", annotations)
        _add_annotation(text, "+1 (555) 867-5309", "PHONE", "ent_neil_ph", annotations)
        _add_annotation(text, "n.armstrong@apollo-corp.test", "EMAIL", "ent_neil_mail", annotations)
        desc = "Test 5 (Held-out): Financial numbers mixed with CFO identity"

    elif doc_num == 23:
        # Test 6 (Held Out): Medical Patient Intake Form
        p1 = "Patient Name: Samantha Carter | Identification Badge: STU-8820"
        p2 = "Attending Physician: Dr. Daniel Jackson | Emergency Contact: +1 (555) 321-4321"
        p3 = "Residential Address: 742 Evergreen Terrace, Springfield, OR 97477"
        text = f"CONFIDENTIAL PATIENT INTAKE RECORD\n\n{p1}\n{p2}\n{p3}\n"
        
        _add_annotation(text, "Samantha Carter", "PERSON", "ent_sam", annotations)
        _add_annotation(text, "STU-8820", "ID_LIKE", "ent_sam_id", annotations)
        _add_annotation(text, "Dr. Daniel Jackson", "PERSON", "ent_daniel", annotations)
        _add_annotation(text, "+1 (555) 321-4321", "PHONE", "ent_daniel_ph", annotations)
        _add_annotation(text, "742 Evergreen Terrace, Springfield, OR 97477", "ADDRESS", "ent_simpson_addr", annotations)
        desc = "Test 6 (Held-out): Medical record with doctor and patient address"

    elif doc_num == 24:
        # Test 7 (Held Out): Tabular Security Roster
        h = "DEFENSE CONTRACTOR SECURITY CLEARANCE REGISTER\n"
        t_header = "BADGE     OPERATIVE            SECURITY TIER   HOTLINE           SECURE MAIL\n"
        row1 = "EMP-901   Sunita Williams      Level 5 Top     +1 (555) 441-2299 s.williams@nasa-contractor.test\n"
        row2 = "EMP-902   Kalpana Chawla       Level 5 Top     +1 (555) 441-2288 k.chawla@nasa-contractor.test\n"
        text = h + t_header + row1 + row2
        
        _add_annotation(text, "EMP-901", "ID_LIKE", "ent_b901", annotations)
        _add_annotation(text, "Sunita Williams", "PERSON", "ent_sunita", annotations)
        _add_annotation(text, "+1 (555) 441-2299", "PHONE", "ent_sunita_ph", annotations)
        _add_annotation(text, "s.williams@nasa-contractor.test", "EMAIL", "ent_sunita_mail", annotations)
        
        _add_annotation(text, "EMP-902", "ID_LIKE", "ent_b902", annotations)
        _add_annotation(text, "Kalpana Chawla", "PERSON", "ent_kalpana", annotations)
        _add_annotation(text, "+1 (555) 441-2288", "PHONE", "ent_kalpana_ph", annotations)
        _add_annotation(text, "k.chawla@nasa-contractor.test", "EMAIL", "ent_kalpana_mail", annotations)
        desc = "Test 7 (Held-out): Tabular security clearance register"

    elif doc_num == 25:
        # Test 8 (Held Out): IT Service Desk Ticket
        p1 = "Ticket HD-9981 opened by User: Sanjay Singhania (sanjay.s@reliance-tech.test)."
        p2 = "Asset Tag: ASSET-44109 | Location: Floor 7, Cyber Tower A, Hitec City, Hyderabad 500081."
        p3 = "Resolved by IT Support: Sanjay Singhania confirmed resolution via phone: +91 98220 33441."
        text = f"IT INCIDENT RESOLUTION TICKET\n\n{p1}\n{p2}\n{p3}\n"
        
        pos = _add_annotation(text, "Sanjay Singhania", "PERSON", "ent_sanjay", annotations)
        _add_annotation(text, "sanjay.s@reliance-tech.test", "EMAIL", "ent_sanjay_mail", annotations)
        _add_annotation(text, "ASSET-44109", "ID_LIKE", "ent_asset_id", annotations)
        _add_annotation(text, "Floor 7, Cyber Tower A, Hitec City, Hyderabad 500081", "ADDRESS", "ent_hyd_addr", annotations)
        _add_annotation(text, "Sanjay Singhania", "PERSON", "ent_sanjay", annotations, start_search=pos)
        _add_annotation(text, "+91 98220 33441", "PHONE", "ent_sanjay_ph", annotations)
        desc = "Test 8 (Held-out): IT ticket with repeated requester and address"

    else:
        raise ValueError(f"Invalid doc_num {doc_num}")

    return text, annotations, desc


def create_pdf_from_text(text: str, output_pdf_path: Path) -> None:
    """Create a searchable synthetic PDF using PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 size

    # Simple page layout
    margin_x = 50
    margin_y = 60
    line_height = 14
    y = margin_y

    for line in text.split("\n"):
        if y > 780:
            page = doc.new_page(width=595, height=842)
            y = margin_y
        page.insert_text(
            fitz.Point(margin_x, y),
            line,
            fontsize=10,
            fontname="helv",
            color=(0.1, 0.1, 0.1),
        )
        y += line_height

    doc.save(str(output_pdf_path))
    doc.close()


def generate_all_datasets() -> None:
    """Generate dev (1-10), val (11-17), and test (18-25) datasets."""
    print("Generating synthetic evaluation corpus (seed=42)...")

    splits = {
        "dev": range(1, 11),     # 10 documents
        "val": range(11, 18),    # 7 documents
        "test": range(18, 26),   # 8 documents (HELD OUT)
    }

    manifest = {"corpus_version": "1.0", "seed": SEED, "splits": {}}

    for split_name, doc_range in splits.items():
        split_dir = DATASET_DIR / split_name
        split_dir.mkdir(parents=True, exist_ok=True)
        split_manifest = []

        for doc_num in doc_range:
            doc_id = f"doc_{doc_num:02d}"
            doc_dir = split_dir / doc_id
            doc_dir.mkdir(parents=True, exist_ok=True)

            text, annotations, desc = generate_document_spec(doc_num)

            # Write document.txt
            txt_path = doc_dir / "document.txt"
            txt_path.write_text(text, encoding="utf-8")

            # Write document.pdf
            pdf_path = doc_dir / "document.pdf"
            create_pdf_from_text(text, pdf_path)

            # Write gold_annotations.json
            gold_payload = {
                "document_id": doc_id,
                "split": split_name,
                "description": desc,
                "text_length": len(text),
                "total_annotations": len(annotations),
                "annotations": annotations,
            }
            gold_path = doc_dir / "gold_annotations.json"
            gold_path.write_text(json.dumps(gold_payload, indent=2), encoding="utf-8")

            split_manifest.append({
                "document_id": doc_id,
                "description": desc,
                "annotations_count": len(annotations),
                "char_length": len(text),
            })

        manifest["splits"][split_name] = split_manifest
        print(f"Generated split '{split_name}': {len(doc_range)} documents.")

    manifest_path = DATASET_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Evaluation corpus generated successfully at {DATASET_DIR}")


if __name__ == "__main__":
    generate_all_datasets()

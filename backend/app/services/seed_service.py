import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.logging_config import logger
from app.core.security import get_password_hash
from app.models.organization import Department, Role, SupportTeam
from app.models.system import AuditLog, KnowledgeArticle, Notification, SystemSetting
from app.models.ticket import (
    SLAPolicy,
    Ticket,
    TicketAttachment,
    TicketCategory,
    TicketComment,
    TicketHistory,
)
from app.models.user import RefreshToken, User

LEGACY_SEEDED_EMAILS = {
    "alex.rivera@ticketdesk.enterprise",
    "priya.nair@ticketdesk.enterprise",
    "marcus.vance@ticketdesk.enterprise",
    "sarah.chen@ticketdesk.enterprise",
    "david.miller@ticketdesk.enterprise",
    "elena.rodriguez@ticketdesk.enterprise",
    "james.wilson@ticketdesk.enterprise",
    "olivia.thompson@ticketdesk.enterprise",
    "daniel.kim@ticketdesk.enterprise",
    "sophia.patel@ticketdesk.enterprise",
    "michael.okafor@ticketdesk.enterprise",
    "hannah.abbott@ticketdesk.enterprise",
    "lucas.moreau@ticketdesk.enterprise",
    "chloe.bennett@ticketdesk.enterprise",
}


def cleanup_legacy_seeded_records(db: Session) -> None:
    """
    Remove 'Operation IT' from support_teams and remove legacy pre-seeded demo users
    so only the Administrator and newly created custom users remain in the database.
    """
    # 1. Remove 'Operation IT' support team if present
    op_teams = (
        db.query(SupportTeam)
        .filter(func.lower(SupportTeam.name) == "operation it")
        .all()
    )
    for t in op_teams:
        db.query(User).filter(User.support_team_id == t.id).update({"support_team_id": None})
        db.query(Ticket).filter(Ticket.support_team_id == t.id).update({"support_team_id": None})
        db.delete(t)

    # 2. Remove legacy pre-seeded demo users and their associated tickets
    legacy_users = (
        db.query(User)
        .filter(func.lower(User.email).in_(LEGACY_SEEDED_EMAILS))
        .all()
    )
    if legacy_users:
        legacy_ids = [u.id for u in legacy_users]
        db.query(Notification).filter(Notification.user_id.in_(legacy_ids)).delete(synchronize_session=False)
        db.query(RefreshToken).filter(RefreshToken.user_id.in_(legacy_ids)).delete(synchronize_session=False)
        db.query(AuditLog).filter(AuditLog.user_id.in_(legacy_ids)).update(
            {"user_id": None}, synchronize_session=False
        )
        db.query(Ticket).filter(Ticket.assigned_agent_id.in_(legacy_ids)).update(
            {"assigned_agent_id": None}, synchronize_session=False
        )
        db.query(TicketHistory).filter(TicketHistory.actor_id.in_(legacy_ids)).update(
            {"actor_id": None}, synchronize_session=False
        )
        db.query(TicketComment).filter(TicketComment.author_id.in_(legacy_ids)).delete(
            synchronize_session=False
        )
        db.query(TicketAttachment).filter(TicketAttachment.uploaded_by_id.in_(legacy_ids)).delete(
            synchronize_session=False
        )
        legacy_tickets = db.query(Ticket).filter(Ticket.requester_id.in_(legacy_ids)).all()
        for lt in legacy_tickets:
            db.delete(lt)
        for u in legacy_users:
            db.delete(u)

    db.commit()


def ensure_extended_kb_and_categories(db: Session) -> None:
    """Ensure 'Others' is in all category subcategories and all 10 KB articles exist."""
    now = datetime.now(timezone.utc)
    categories = db.query(TicketCategory).all()
    cat_map = {c.slug: c for c in categories}

    for cat in categories:
        try:
            subs = json.loads(cat.subcategories_json or "[]")
        except Exception:
            subs = []
        if "Others" not in subs:
            subs.append("Others")
            cat.subcategories_json = json.dumps(subs)

    admin_user = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(Role.name == "admin")
        .first()
    )
    if not admin_user:
        admin_user = db.query(User).first()
    if not admin_user:
        db.commit()
        return

    for title, slug, summary, content, cat_slug, tags, views, helpful in get_kb_articles_spec():
        exists = db.query(KnowledgeArticle).filter(KnowledgeArticle.slug == slug).first()
        if not exists and cat_slug in cat_map:
            db.add(
                KnowledgeArticle(
                    title=title,
                    slug=slug,
                    summary=summary,
                    content=content,
                    category_id=cat_map[cat_slug].id,
                    author_id=admin_user.id,
                    tags=tags,
                    is_published=True,
                    view_count=views,
                    helpful_count=helpful,
                    created_at=now - timedelta(days=20),
                    updated_at=now - timedelta(days=1),
                )
            )

    db.commit()


def get_kb_articles_spec():
    return [
        (
            "Resetting Your Corporate Active Directory & Okta SSO Password",
            "resetting-corporate-password-okta-sso",
            "Step-by-step instructions to self-service reset your corporate Okta Single Sign-On password and unlock your Active Directory account.",
            """## Overview
All TicketDesk Enterprise employees authenticate using **Okta Single Sign-On (SSO)** synchronized with Corporate Active Directory. Password policies require rotation every 90 days.

### Password Complexity Requirements
- Minimum length of **14 characters**
- At least one uppercase letter, one lowercase letter, one number, and one special symbol
- Cannot reuse any of your previous 12 passwords
- Cannot contain your username or first/last name

### Step-by-Step Self-Service Reset
1. On the TicketDesk login screen, click **Forgot password?**.
2. Enter your registered **Phone Number** (and optional corporate email) to receive a 6-digit verification OTP.
3. Enter the 6-digit OTP code and set your new password.""",
            "access",
            "password,okta,sso,mfa,lockout",
            342,
            89,
        ),
        (
            "Connecting to Corporate Office Wi-Fi (TicketDesk-Corp 802.1X)",
            "connecting-to-office-wifi-8021x",
            "How to configure WPA3-Enterprise 802.1X wireless authentication on macOS, Windows 11, iOS, and Android devices across all global offices.",
            """## Corporate Wireless Networks
Our global offices broadcast two SSIDs:
- **`TicketDesk-Corp`**: Encrypted WPA3-Enterprise (802.1X) network with direct access to internal engineering, finance, and staging resources.
- **`TicketDesk-Guest`**: Isolated internet-only network for visitors and personal mobile devices (requires daily sponsor code).

### Automatic MDM Configuration (Corporate Laptops)
Corporate-managed MacBooks (Jamf Pro) and Windows ThinkPads (Microsoft Intune) automatically install the 802.1X machine certificate. If prompted:
1. Select **`TicketDesk-Corp`** from your Wi-Fi menu.
2. Enter your Okta username and current SSO password.
3. When prompted to verify the RADIUS certificate (`radius.corp.ticketdesk.enterprise`), click **Trust / Connect**.""",
            "network",
            "wifi,wireless,802.1x,meraki,network",
            275,
            64,
        ),
        (
            "Troubleshooting GlobalProtect VPN Access & Split-Tunnel Routing",
            "troubleshooting-vpn-access-globalprotect",
            "Resolve TLS handshake timeouts, MFA prompts, and internal DNS resolution issues on Palo Alto GlobalProtect VPN.",
            """## When Is VPN Required?
GlobalProtect VPN is required when accessing internal `.corp.ticketdesk.enterprise` systems, staging databases, or private AWS VPC endpoints from outside corporate offices.

### Common Issue 1: "Connecting..." Stuck or TLS Handshake Timeout
1. Open the GlobalProtect system tray / menu bar icon -> **Settings (Gear Icon)** -> **General**.
2. Click **Sign Out** and clear saved credentials.
3. Verify your portal address is set to **`vpn.ticketdesk.enterprise`**.
4. Flush your local DNS cache (`ipconfig /flushdns` on Windows or `sudo dscacheutil -flushcache` on macOS).""",
            "network",
            "vpn,globalprotect,dns,remote-access",
            418,
            112,
        ),
        (
            "Installing Approved Enterprise Software via Self-Service Catalog",
            "installing-approved-enterprise-software",
            "How to install pre-approved developer tools, productivity apps, and request paid licenses without local administrator prompts.",
            """## Standard Pre-Approved Software
Employees can install vetted software packages directly without submitting an IT ticket using our endpoint self-service portals:
- **macOS Users**: Open **TicketDesk Self Service** (powered by Jamf) from your Applications folder.
- **Windows 11 Users**: Open **Company Portal** (powered by Microsoft Intune) from the Start Menu.

### Requesting Licensed Commercial Software
For seats requiring procurement approval (JetBrains All Products Pack, Adobe Acrobat Pro, Tableau Desktop, Lucidchart):
1. Submit a ticket under **Category: Software -> License Provisioning**.
2. Include your **Department Cost Center** and manager approval.""",
            "software",
            "software,jamf,intune,licenses,install",
            198,
            51,
        ),
        (
            "Enrolling Hardware Security Keys (YubiKey) and Okta Verify MFA",
            "enrolling-yubikey-okta-verify-mfa",
            "Protect your corporate identity with phishing-resistant FIDO2/WebAuthn YubiKeys and Okta FastPass.",
            """## Mandatory Multi-Factor Authentication
TicketDesk Enterprise enforces phishing-resistant **FIDO2 / WebAuthn** authentication for all production infrastructure and financial systems.

### Registering a Backup Factor
We strongly recommend registering at least **two** independent MFA factors (e.g., Mobile OTP Authenticator + YubiKey 5C Nano) so you are never locked out when upgrading phones.""",
            "security",
            "mfa,yubikey,security,fido2,okta",
            164,
            47,
        ),
        (
            "Requesting Temporary Production Database & AWS IAM Access (JIT)",
            "requesting-aws-iam-database-access",
            "Procedure for requesting Just-In-Time (JIT) read/write access to AWS accounts and RDS PostgreSQL instances for incident response.",
            """## Principle of Least Privilege
Direct access to production RDS databases and AWS IAM roles is restricted by default and audited for SOC 2 Type II compliance.

### How to Submit an Access Request
1. Create a ticket under **Category: Access -> GitHub / AWS IAM Role**.
2. Specify target AWS Account, Required Permission Level, Duration, and Business justification.""",
            "access",
            "aws,iam,rds,database,soc2,access",
            229,
            73,
        ),
        (
            "Troubleshooting Laptop Docking Stations, Dual 4K Monitors & Peripherals",
            "troubleshooting-docking-stations-monitors-hardware",
            "Resolve display flickering, USB-C Power Delivery charging issues, and peripheral disconnects on CalDigit TS4 and Dell Thunderbolt docks.",
            """## Standard Corporate Workstation Hardware
TicketDesk Enterprise workstations use **CalDigit TS4** and **Dell WD22TB4 Thunderbolt 4** docking stations paired with dual 27-inch 4K UltraSharp monitors.

### Step 1: Resolve External Monitor Flickering or "No Signal"
1. Ensure the Thunderbolt 4 host cable is plugged into the **rear Thunderbolt host port** and connected directly to your laptop.
2. Disconnect power from the dock for **15 seconds** to reset the DisplayPort MST controller, then reconnect.
3. **macOS Users**: Navigate to **System Settings -> Displays** and set the refresh rate to **60 Hz**.
4. **Windows ThinkPad Users**: Open **Lenovo Commercial Vantage -> System Update** and install the latest Thunderbolt Retimer Firmware.""",
            "hardware",
            "hardware,docking-station,monitor,laptop,macbook,thinkpad",
            312,
            94,
        ),
        (
            "Corporate Laptop Lifecycle Refresh, Loaner Devices & Peripheral Ordering",
            "corporate-laptop-refresh-and-peripheral-ordering",
            "Guidelines for 3-year workstation refresh eligibility, ergonomic accessories, and emergency hardware replacements.",
            """## Hardware Refresh & Peripheral Policy
Every full-time employee is eligible for a workstation refresh every **36 months** and standard ergonomic desk accessories.

### How to Request Hardware
1. Navigate to **Create Ticket** -> **Category: Hardware**.
2. Select the appropriate Subcategory (*Laptop / Workstation*, *Keyboard & Mouse*, *Monitor / Display*, or *Others*).
3. Route to the **Workplace & Endpoint Engineering** support team and include your office building, floor, and desk number.""",
            "hardware",
            "hardware,peripherals,ergonomic,replacement,loaner",
            187,
            62,
        ),
        (
            "Conference Room Zoom A/V Systems & Wireless Screen Sharing Guide",
            "conference-room-zoom-av-wireless-sharing-guide",
            "Quick fixes for Zoom Room iPad controllers, HDMI ingest, wireless AirPlay/Direct Share, and microphone array troubleshooting.",
            """## Using Enterprise Conference Rooms
All global conference rooms are equipped with **Zoom Rooms Appliances**, Shure ceiling microphone arrays, and Poly Studio cameras.

### Wireless Screen Sharing
1. Open the **Zoom Workplace** client on your laptop and click **Share Screen**.
2. Enter the **6-character Sharing Key** displayed on the conference room TV screen.
3. For live boardroom assistance, submit a ticket under **Category: Other -> Conference Room A/V**.""",
            "other",
            "av,zoom-rooms,conference-room,projector,other",
            254,
            78,
        ),
        (
            "Desk Relocation, Office Badge Access & General IT Consultation Requests",
            "desk-relocation-badge-access-general-it-requests",
            "How to coordinate workstation moves, network port activation, visitor Wi-Fi sponsor codes, and general IT policy consultations.",
            """## Facility IT & General Support Services
For requests that do not fall under standard hardware, software, or network incidents, use the **Other** category.

### Desk & Office Relocations
Please submit requests at least **48 hours** prior to your move date under **Category: Other -> Desk Relocation Setup** specifying your current and target floor/desk IDs.""",
            "other",
            "relocation,badge,facilities,policy,consultation,other",
            149,
            44,
        ),
    ]


def _insert_missing_reference_rows(db: Session, model, key, rows: list[dict]) -> bool:
    existing = set(db.scalars(select(key)))
    missing = [row for row in rows if row[key.key] not in existing]
    if not missing:
        return False
    insert = sqlite_insert if db.get_bind().dialect.name == "sqlite" else postgres_insert
    db.execute(insert(model).values(missing).on_conflict_do_nothing(index_elements=[key]))
    return True


def initialize_reference_data(db: Session) -> bool:
    """Fill missing built-in reference rows, preserving existing rows and users."""
    # Roles
    changed = _insert_missing_reference_rows(db, Role, Role.name, [
        dict(
            name="admin",
            display_name="IT Administrator",
            description="Full administrative access to users, SLA policies, audit logs, and enterprise settings.",
        ),
        dict(
            name="agent",
            display_name="IT Support Agent",
            description="Operational access to ticket queues, incident resolution, SLA tracking, and knowledge base.",
        ),
        dict(
            name="employee",
            display_name="Employee",
            description="Standard corporate user able to submit tickets, upload attachments, and track requests.",
        ),
    ])

    # Departments
    departments_data = [
        ("Engineering & Product", "ENG", "Core software engineering and product development", "San Francisco HQ - Floor 4"),
        ("Finance & Accounting", "FIN", "Corporate finance, payroll, and treasury operations", "New York - Floor 12"),
        ("Human Resources", "HR", "People operations, talent acquisition, and onboarding", "San Francisco HQ - Floor 2"),
        ("Enterprise Sales", "SALES", "Global account executives and revenue operations", "Chicago - Floor 8"),
        ("Operations & Supply Chain", "OPS", "Global facilities, procurement, and logistics", "Austin - Building B"),
        ("Legal & Compliance", "LEGAL", "Corporate governance, privacy, and regulatory affairs", "New York - Floor 14"),
        ("Information Technology", "IT", "Enterprise IT Service Management & Security Operations", "San Francisco HQ - Floor 5"),
    ]
    changed |= _insert_missing_reference_rows(db, Department, Department.code, [
        dict(name=name, code=code, description=desc, location=loc, is_active=True)
        for name, code, desc, loc in departments_data
    ])

    # Active support teams
    teams_data = [
        ("Infrastructure & Network Ops", "NETOPS", "VPN, Wi-Fi, firewalls, DNS, and cloud connectivity", "Network & Cloud"),
        ("Workplace & Endpoint Engineering", "ENDPOINT", "Corporate laptops, peripherals, OS imaging, and MDM", "Hardware & OS"),
        ("Identity & Access Governance", "IAM", "Active Directory, SSO/Okta, MFA, and role provisioning", "Identity & Security"),
        ("Enterprise Business Applications", "BIZAPPS", "ERP, CRM, Slack, Jira, Microsoft 365, and SaaS licensing", "Enterprise Software"),
    ]
    changed |= _insert_missing_reference_rows(db, SupportTeam, SupportTeam.code, [
        dict(name=name, code=code, description=desc, specialization=spec, is_active=True)
        for name, code, desc, spec in teams_data
    ])

    # Ticket categories
    categories_spec = [
        (
            "Hardware",
            "hardware",
            "Workstations, MacBook/ThinkPad laptops, docking stations, monitors, and peripherals",
            ["Laptop / Workstation", "Monitor / Display", "Docking Station", "Keyboard & Mouse", "Mobile Device", "Printer / Scanner", "Others"],
            "Laptop",
        ),
        (
            "Software",
            "software",
            "Enterprise SaaS applications, IDE licenses, productivity suites, and OS upgrades",
            ["Microsoft 365 / Outlook", "Slack / Collaboration", "IDE & Developer Tools", "Zoom / Conferencing", "OS Crash / Update", "License Provisioning", "Others"],
            "AppWindow",
        ),
        (
            "Network",
            "network",
            "Corporate VPN, office Wi-Fi, DNS resolution, firewall rules, and cloud VPC peering",
            ["VPN Connectivity", "Corporate Wi-Fi (802.1X)", "LAN / Ethernet Port", "DNS / Internal Routing", "Cloud VPC / AWS Direct Connect", "Others"],
            "Wifi",
        ),
        (
            "Access",
            "access",
            "Single Sign-On (Okta), Active Directory passwords, RBAC permissions, and database access",
            ["SSO / Okta Lockout", "MFA Hardware Token / Reset", "GitHub / AWS IAM Role", "Shared Drive / SharePoint", "New Hire Onboarding Access", "Others"],
            "KeyRound",
        ),
        (
            "Security",
            "security",
            "Phishing reports, endpoint antivirus alerts, lost device lockdown, and DLP policies",
            ["Suspicious Email / Phishing", "CrowdStrike Endpoint Alert", "Lost or Stolen Device", "Certificate Expiration", "USB / DLP Exception", "Others"],
            "ShieldAlert",
        ),
        (
            "Other",
            "other",
            "General IT inquiries, audio/visual conference room support, and facility badge requests",
            ["Conference Room A/V", "Desk Relocation Setup", "IT Policy Inquiry", "General Consultation", "Others"],
            "HelpCircle",
        ),
    ]
    changed |= _insert_missing_reference_rows(db, TicketCategory, TicketCategory.slug, [
        dict(
            name=name,
            slug=slug,
            description=desc,
            subcategories_json=json.dumps(subs),
            icon=icon,
            is_active=True,
        )
        for name, slug, desc, subs, icon in categories_spec
    ])

    # SLA policies
    sla_specs = [
        ("Critical Incident SLA (P1)", "critical", 15, 240, False, "15-minute initial response and 4-hour resolution target for critical production or executive blockers."),
        ("High Priority SLA (P2)", "high", 60, 480, False, "1-hour initial response and 8-hour resolution target for severe degradation impacting work."),
        ("Medium Priority SLA (P3)", "medium", 240, 1440, True, "4-hour initial response and 24-hour resolution target for standard single-user technical issues."),
        ("Low Priority SLA (P4)", "low", 480, 2880, True, "8-hour initial response and 48-hour resolution target for routine requests and minor inquiries."),
    ]
    changed |= _insert_missing_reference_rows(db, SLAPolicy, SLAPolicy.priority, [
        dict(
            name=name,
            priority=prio,
            response_target_minutes=resp_m,
            resolution_target_minutes=res_m,
            business_hours_only=bh_only,
            description=desc,
            is_active=True,
        )
        for name, prio, resp_m, res_m, bh_only, desc in sla_specs
    ])
    # System settings
    settings_seed = [
        ("organization_name", "TicketDesk Enterprise Corp", "general", "Primary organization display name across the portal and notifications."),
        ("support_portal_email", "it-helpdesk@ticketdesk.enterprise", "general", "Default reply-to address for IT Service Desk notifications."),
        ("business_hours_window", "Mon-Fri 08:00 - 18:00 UTC", "sla", "Standard operating window for business-hours SLA policies."),
        ("allow_employee_reopen_days", "7", "tickets", "Number of days after resolution within which an employee may reopen a ticket."),
        ("auto_close_resolved_days", "5", "tickets", "Automatically transition Resolved tickets to Closed after N days of inactivity."),
        ("storage_provider_mode", settings.STORAGE_PROVIDER, "storage", "Active attachment storage backend (local or Amazon S3)."),
        ("s3_bucket_name", settings.S3_BUCKET_NAME, "storage", "Configured Amazon S3 bucket for ticket attachments and Lambda event processing."),
    ]
    changed |= _insert_missing_reference_rows(db, SystemSetting, SystemSetting.key, [
        dict(key=key, value=val, category=cat, description=desc)
        for key, val, cat, desc in settings_seed
    ])
    return changed


def seed_database(db: Session) -> None:
    """Preserve demo initialization for local, test, and verification environments."""
    if settings.APP_ENV == "production":
        initialize_reference_data(db)
        db.commit()
        return
    if db.query(Role.id).first():
        ensure_extended_kb_and_categories(db)
        logger.info("Database verified; existing user and ticket data preserved.")
        return

    initialize_reference_data(db)
    now = datetime.now(timezone.utc)
    admin_user = User(
        email="admin@ticketdesk.enterprise",
        full_name="Evelyn Sterling",
        employee_id="EMP-1001",
        job_title="Director of Enterprise IT & ITSM",
        phone="+1 (415) 890-1001",
        hashed_password=get_password_hash("Admin@12345"),
        is_active=True,
        role_id=db.query(Role.id).filter_by(name="admin").scalar(),
        department_id=db.query(Department.id).filter_by(code="IT").scalar(),
        support_team_id=db.query(SupportTeam.id).filter_by(code="IAM").scalar(),
        last_login_at=now,
        created_at=now,
    )
    db.add(admin_user)
    db.flush()

    cat_map = {category.slug: category.id for category in db.query(TicketCategory).all()}
    for title, slug, summary, content, cat_slug, tags, views, helpful in get_kb_articles_spec():
        db.add(
            KnowledgeArticle(
                title=title,
                slug=slug,
                summary=summary,
                content=content,
                category_id=cat_map[cat_slug],
                author_id=admin_user.id,
                tags=tags,
                is_published=True,
                view_count=views,
                helpful_count=helpful,
                created_at=now - timedelta(days=20),
                updated_at=now - timedelta(days=1),
            )
        )
    for setting in db.query(SystemSetting).all():
        setting.updated_by_id = admin_user.id

    db.add(
        AuditLog(
            user_id=admin_user.id,
            action="SYSTEM_INITIALIZED",
            entity_type="system",
            entity_id="seed-v1",
            ip_address="127.0.0.1",
            user_agent="System Seeder",
            metadata_json=json.dumps({"environment": settings.APP_ENV}),
            created_at=now,
        )
    )

    db.commit()
    logger.info("Successfully initialized TicketDesk Enterprise database!")

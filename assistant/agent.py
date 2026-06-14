from openai import OpenAI
import re
from assistant.tools import (
    find_client,
    get_overdue_invoices,
    get_unpaid_invoices_for_client,
    draft_payment_reminder,
    get_client_jobs,
    search_jobs,
    get_job_detail,
    add_job_note,
)

client = OpenAI()


SYSTEM_PROMPT = """
Si firemný AI asistent pre faktúry, zákazníkov, zákazky a ponuky.

Pravidlá:
- Nikdy si nevymýšľaj firemné údaje.
- Ak údaj nie je v databáze, povedz to.
- Nikdy neposielaj email bez potvrdenia používateľa.
- Ak je viac možných klientov alebo zákaziek, vypýtaj si výber.
- Pri akciách ukáž najprv náhľad.
- Odpovedaj stručne a prakticky po slovensky.
"""


def run_assistant(message: str):
    intent = detect_intent(message)

    if intent["action"] == "overdue_invoices":
        data = get_overdue_invoices()
        return format_overdue_invoices(data)

    if intent["action"] == "find_client":
        data = find_client(intent["client_name"])
        return format_clients(data)

    if intent["action"] == "client_unpaid":
        client_result = find_client(intent["client_name"])

        if client_result["status"] != "success":
            return client_result["message"]

        clients = client_result["clients"]

        if len(clients) > 1:
            return format_client_selection(clients)

        invoices = get_unpaid_invoices_for_client(clients[0]["id"])
        return format_unpaid_invoices(invoices)

    if intent["action"] == "draft_reminder":
        client_result = find_client(intent["client_name"])

        if client_result["status"] != "success":
            return client_result["message"]

        clients = client_result["clients"]

        if len(clients) > 1:
            return format_client_selection(clients)

        invoices = get_unpaid_invoices_for_client(clients[0]["id"])
        invoice_list = invoices.get("invoices", [])

        if not invoice_list:
            return "Tento klient nemá žiadne nezaplatené faktúry."

        overdue = [i for i in invoice_list if i["is_overdue"]]

        if len(overdue) == 1:
            draft = draft_payment_reminder(overdue[0]["id"])
            return format_email_draft(draft)

        if len(overdue) > 1:
            return format_invoice_selection(overdue)

        return "Klient má nezaplatené faktúry, ale žiadna ešte nie je po splatnosti."

    if intent["action"] == "search_jobs":
        data = search_jobs(intent["query"])
        return format_jobs(data)

    if intent["action"] == "job_detail":
        data = search_jobs(intent["query"])
        jobs = data.get("jobs", [])

        if not jobs:
            return "Zákazku som nenašiel."

        if len(jobs) > 1:
            return format_job_selection(jobs)

        detail = get_job_detail(jobs[0]["id"])
        return format_job_detail(detail)

    return ask_ai_general(message)


def detect_intent(message: str):
    msg = message.lower()

    if "kto mi dlhuje" in msg or "faktúry po splatnosti" in msg or "faktury po splatnosti" in msg:
        return {"action": "overdue_invoices"}

    if "nájdi klienta" in msg or "najdi klienta" in msg or "nájdi zákazníka" in msg or "najdi zakaznika" in msg:
        return {
            "action": "find_client",
            "client_name": clean_name(message)
        }

    if "koľko mi dlhuje" in msg or "kolko mi dlhuje" in msg:
        return {
            "action": "client_unpaid",
            "client_name": clean_name(message)
        }

    if "upomienku" in msg or "nezaplatenej faktúre" in msg or "nezaplatenej fakture" in msg:
        return {
            "action": "draft_reminder",
            "client_name": clean_name(message)
        }

    if "nájdi zákazku" in msg or "najdi zakazku" in msg:
        return {
            "action": "search_jobs",
            "query": clean_job_query(message)
        }

    if "zhrň zákazku" in msg or "zhrn zakazku" in msg or "stav zákazky" in msg or "stav zakazky" in msg:
        return {
            "action": "job_detail",
            "query": clean_job_query(message)
        }
    if "odoslať email" in msg or "odoslat email" in msg:
        return {
            "action": "send_email",
            "email_log_id": extract_number(message)
        }

    return {"action": "general"}




def clean_name(message: str):
    msg = message.strip()

    match = re.search(r"\bpre\s+(.+)$", msg, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()

    remove_patterns = [
        r"\bpošli\b",
        r"\bposli\b",
        r"\bemail\b",
        r"\bohľadom\b",
        r"\bohladom\b",
        r"\bnezaplatenej\b",
        r"\bnezaplatenej faktúre\b",
        r"\bnezaplatenej fakture\b",
        r"\bfaktúre\b",
        r"\bfakture\b",
        r"\bfaktúry\b",
        r"\bfaktury\b",
        r"\bpriprav\b",
        r"\bupomienku\b",
        r"\bpre\b",
        r"\bfirmu\b",
        r"\bnájdi\b",
        r"\bnajdi\b",
        r"\bklienta\b",
        r"\bzákazníka\b",
        r"\bzakaznika\b",
        r"\bkoľko\b",
        r"\bkolko\b",
        r"\bmi\b",
        r"\bdlhuje\b",
    ]

    cleaned = msg

    for pattern in remove_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned
def extract_number(message: str):
    match = re.search(r"\d+", message)
    return int(match.group()) if match else None

def clean_job_query(message: str):
    remove = [
        "nájdi", "najdi", "zákazku", "zakazku",
        "zhrň", "zhrn", "stav", "zákazky", "zakazky"
    ]

    cleaned = message

    for word in remove:
        cleaned = cleaned.replace(word, "")

    return cleaned.strip()


def ask_ai_general(message: str):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ]
    )

    return response.choices[0].message.content


def format_overdue_invoices(data):
    invoices = data.get("invoices", [])

    if not invoices:
        return "Nemáš žiadne faktúry po splatnosti."

    text = "Faktúry po splatnosti:\n\n"

    for inv in invoices:
        text += (
            f"- {inv['client_name']} | "
            f"Faktúra č. {inv['invoice_number']} | "
            f"{inv['amount']} {inv['currency']} | "
            f"splatnosť {inv['due_date']} | "
            f"{inv['days_overdue']} dní po splatnosti\n"
        )

    return text


def format_clients(data):
    if data["status"] != "success":
        return data["message"]

    text = "Našiel som klientov:\n\n"

    for c in data["clients"]:
        text += f"- ID {c['id']}: {c['name']} | email: {c['email']} | IČO: {c['ico']}\n"

    return text


def format_client_selection(clients):
    text = "Našiel som viac klientov. Vyber ID:\n\n"

    for c in clients:
        text += f"- ID {c['id']}: {c['name']} | {c['email']} | IČO: {c['ico']}\n"

    return text


def format_unpaid_invoices(data):
    invoices = data.get("invoices", [])

    if not invoices:
        return "Nenašiel som nezaplatené faktúry."

    text = "Nezaplatené faktúry:\n\n"

    for inv in invoices:
        overdue = f" | {inv['days_overdue']} dní po splatnosti" if inv["is_overdue"] else ""
        text += (
            f"- ID {inv['id']}: Faktúra č. {inv['invoice_number']} | "
            f"{inv['amount']} {inv['currency']} | "
            f"splatnosť {inv['due_date']}{overdue}\n"
        )

    return text


def format_invoice_selection(invoices):
    text = "Našiel som viac faktúr po splatnosti. Vyber ID faktúry:\n\n"

    for inv in invoices:
        text += (
            f"- ID {inv['id']}: Faktúra č. {inv['invoice_number']} | "
            f"{inv['amount']} {inv['currency']} | "
            f"splatnosť {inv['due_date']} | "
            f"{inv['days_overdue']} dní po splatnosti\n"
        )

    return text


def format_email_draft(data):
    if data["status"] != "success":
        return data["message"]

    email = data["email"]

    return f"""
Pripravil som email. Zatiaľ som ho neodoslal.

Komu: {email['to']}
Predmet: {email['subject']}

{email['body']}

Napíš „odoslať“, ak ho chceš odoslať.
""".strip()


def format_jobs(data):
    jobs = data.get("jobs", [])

    if not jobs:
        return "Nenašiel som žiadne zákazky."

    text = "Našiel som zákazky:\n\n"

    for job in jobs:
        text += (
            f"- ID {job['id']}: {job['title']} | "
            f"stav: {job['status']} | "
            f"klient: {job['client_name']}\n"
        )

    return text


def format_job_selection(jobs):
    text = "Našiel som viac zákaziek. Vyber ID:\n\n"

    for job in jobs:
        text += (
            f"- ID {job['id']}: {job['title']} | "
            f"stav: {job['status']} | klient: {job['client_name']}\n"
        )

    return text


def format_job_detail(data):
    if data["status"] != "success":
        return data["message"]

    job = data["job"]

    text = f"""
Zákazka: {job['title']}
Klient: {job['client_name']}
Stav: {job['status']}

Popis:
{job['description'] or 'Bez popisu.'}

Poznámky:
""".strip()

    if not job["notes"]:
        text += "\n- Bez poznámok."
    else:
        for note in job["notes"][-5:]:
            text += f"\n- [{note['note_type']}] {note['content']}"

    return text
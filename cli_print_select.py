from tabulate import tabulate
from utilities import PDF, add_micr_line, add_check_number, add_bank_info, add_owner_info, add_check_titles
from common_dsql import connect_db
from cli_utils import prompt_int, prompt_yes_no, prompt_page_size

def add_iota_info(pdf, check_number, routing_number, account_number, position=1):
    add_micr_line(pdf, check_number, routing_number, account_number, style='B', position=position)
    add_check_number(pdf, check_number, position=position)

def select_bank_account():
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT bank_account_id, routing, account, name,
                       company_name_1, company_name_2, company_address_1, company_address_2
                FROM bank_accounts
                ORDER BY name
            """)
            accounts = cur.fetchall()
            print("\nAvailable Bank Accounts:\n")
            print(tabulate(
                [(i + 1, a['name'], a['routing'].strip(), a['account'].strip()) for i, a in enumerate(accounts)],
                headers=["#", "Name", "Routing", "Account"]
            ))

            index = prompt_int("\nSelect a bank account by number", min=1, max=len(accounts)) - 1
            selected = accounts[index]

            cur.execute("SELECT * FROM banks WHERE routing = %s", (selected['routing'],))
            bank = cur.fetchone()

            cur.execute("""
                SELECT next_check_number FROM bank_accounts
                WHERE bank_account_id = %s
                FOR UPDATE
            """, (selected['bank_account_id'],))
            next_check = cur.fetchone()['next_check_number']

    return selected, bank, next_check

def update_next_check_number(bank_account_id, new_value):
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bank_accounts
                SET next_check_number = %s
                WHERE bank_account_id = %s
            """, (new_value, bank_account_id))
            conn.commit()

# Main
selected, bank, next_check_number = select_bank_account()

routing_number = selected['routing'].strip()
account_number = selected['account'].strip()

print(f"\nDefault next check number: {next_check_number}")
first_check_number = prompt_int("Enter first check number", default=next_check_number)
page_size = prompt_page_size()
checks_per_page = prompt_int("Enter checks to print on each page", default=1, min=1, max=3)
first_position = prompt_int("Enter first check position [1-based]", default=1, min=1, max=checks_per_page)
num_checks = prompt_int("Enter number of checks to print", default=1, min=1)

start_index = first_position - 1

# MICR and non-MICR PDFs with chosen page size / checks-per-page
pdf_micr = PDF(checks_per_page=checks_per_page, page_size=page_size)
pdf_nomicr = PDF(checks_per_page=checks_per_page, page_size=page_size)

for i in range(num_checks):
    check_number = first_check_number + i
    absolute_position = start_index + i
    position_on_page = (absolute_position % checks_per_page) + 1

    if position_on_page == 1 and i > 0:
        pdf_micr.add_page()
        pdf_nomicr.add_page()

    add_iota_info(pdf_micr, check_number, routing_number, account_number, position=position_on_page)

    add_bank_info(
        pdf_nomicr,
        bank_name="\n".join(filter(None, [bank.get("bank_name_1"), bank.get("bank_name_2")])),
        bank_address="\n".join(filter(None, [bank.get("bank_address_1"), bank.get("bank_address_2")])),
        fract_routing_num=bank.get("bank_fractional"),
        position=position_on_page
    )
    add_owner_info(
        pdf_nomicr,
        owner_name="\n".join(filter(None, [selected.get("company_name_1"), selected.get("company_name_2")])),
        owner_address="\n".join(filter(None, [selected.get("company_address_1"), selected.get("company_address_2")])),
        position=position_on_page
    )
    add_check_titles(pdf_nomicr, position=position_on_page)

pdf_nomicr.output("nomicr.pdf")
print("Non-MICR check info saved as nomicr.pdf")
pdf_micr.output("micr.pdf")
print("MICR check info saved as micr.pdf")

# Confirm before updating DB
if prompt_yes_no("\nDid the checks print correctly?", default=False):
    update_next_check_number(selected['bank_account_id'], first_check_number + num_checks)
    print("Next check number updated in the database.")
else:
    print("Next check number not updated.")

from utilities import create_check
from cli_utils import prompt_int, prompt_page_size

if __name__ == "__main__":
    payee = input("Enter the payee: ")
    amount = input("Enter the amount (in the format XXXX.XX): ")
    date = input("Enter the date (MM/DD/YYYY): ")
    memo = input("Enter the memo: ")

    page_size = prompt_page_size()
    checks_per_page = prompt_int("Enter checks to print on each page", default=1, min=1, max=3)
    position = prompt_int("Enter first check position [1-based]", default=1, min=1, max=checks_per_page)

    create_check(payee, amount, date, memo,
                 position=position,
                 checks_per_page=checks_per_page,
                 page_size=page_size)
    print("Check saved as check.pdf")

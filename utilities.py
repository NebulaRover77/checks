from decimal import Decimal, InvalidOperation
from fpdf import FPDF
import inflect
from pathlib import Path

top_y = 0.4375
info_y = top_y + 0
date_y = top_y + 0.55
payee_y = 3.5 - 1.4 - 0.65
dollars_y = payee_y + 0.25
bottom_y = 3.5 - 0.625
memo_y = bottom_y - 0.05

left_x = 0.25
first_tab = left_x + 0.5

FONT_DIR = Path(__file__).resolve().parent / "fonts"
REQUIRED_FONTS = {
    "AvenirBook": FONT_DIR / "AvenirBook.ttf",
    "MICR": FONT_DIR / "MICR.ttf",
}

def ensure_fonts_available(required=None):
    if not FONT_DIR.exists():
        raise RuntimeError(
            f"Missing fonts directory: {FONT_DIR}\n"
            f"Copy your font files here (AvenirBook.ttf, MICR.ttf)."
        )
    if required is None:
        required = list(REQUIRED_FONTS.keys())
    missing = [name for name in required if not REQUIRED_FONTS[name].exists()]
    if missing:
        missing_list = ", ".join(missing)
        raise RuntimeError(
            f"Missing font file(s) in {FONT_DIR}: {missing_list}\n"
            f"Expected: {', '.join(str(p.name) for p in REQUIRED_FONTS.values())}"
        )

class PDF(FPDF):
    def __init__(self, checks_per_page=3, page_size=(8.5, 11.0), orientation=None):
        if checks_per_page < 1 or checks_per_page > 3:
            raise ValueError("checks_per_page must be between 1 and 3")

        w, h = page_size
        if orientation is None:
            if h > w:
                orientation = 'P'
            else:
                #orientation = 'L'
                orientation = 'P'

        super().__init__(orientation=orientation, unit='in', format=(w, h))
        self.checks_per_page = checks_per_page
        self.page_size = (w, h)
        self.set_auto_page_break(auto=False)
        self.set_margins(0, 0, 0)
        self.add_page()

    def header(self):
        pass  # No header

def add_text(pdf, x, y, txt):
    return pdf.text(x, y, txt)
#    if pdf.cur_orientation=='P':
#        return pdf.text(x, y, t)
#    print(x, y, t)
#    xa=0
#    ya=0
#    xb=x
#    yb=y-pdf.page_size[1]
#    with pdf.rotation(angle=-90, x=xa, y=ya):
#        pdf.text(xb, yb, t)

def get_string_length(pdf, str):
    return pdf.get_string_width(str)

def add_owner_info(pdf, owner_name=None, owner_address=None, position=1):
    position = position - 1
    x_offset = first_tab
    y_offset = info_y + 3.5 * position

    if owner_name:
        pdf.set_font("Arial", style='B', size=12)
        for line in owner_name.splitlines():
            width = get_string_length(pdf, line)
            add_text(pdf, x_offset, y_offset, line)
            y_offset += pdf.font_size + 0.01
        y_offset += 0.01

    if owner_address:
        pdf.set_font("Arial", style='', size=12)
        for line in owner_address.splitlines():
            width = get_string_length(pdf, line)
            add_text(pdf, x_offset, y_offset, line)
            y_offset += pdf.font_size + 0.01
        y_offset += 0.01

def add_bank_info(pdf, bank_name=None, bank_address=None, fract_routing_num=None, position=1):
    position = position - 1
    x_center = 5.125
    y_offset = info_y + 3.5 * position

    if bank_name:
        pdf.set_font("Arial", style='B', size=11)
        for line in bank_name.splitlines():
            width = get_string_length(pdf, line)
            add_text(pdf, x_center - width/2, y_offset, line)
            y_offset += pdf.font_size + 0.01

    if bank_address:
        pdf.set_font("Arial", size=9)
        for line in bank_address.splitlines():
            width = get_string_length(pdf, line)
            add_text(pdf, x_center - width/2, y_offset, line)
            y_offset += pdf.font_size + 0.01
        y_offset += 0.02

    if fract_routing_num:
        width = get_string_length(pdf, fract_routing_num)
        add_text(pdf, x_center - width/2, y_offset, fract_routing_num)

def add_check_titles(pdf, position=1):
    ensure_fonts_available(["AvenirBook"])
    position = position - 1
    y_offset = 3.5 * position
    pdf.add_font('AvenirBook', '', str(REQUIRED_FONTS["AvenirBook"]), uni=True)
    pdf.set_font("AvenirBook", style='', size=10)
    add_text(pdf, left_x, y_offset + payee_y - pdf.font_size, "PAY TO THE")
    add_text(pdf, left_x, y_offset + payee_y, "ORDER OF")

    page_width = pdf.w
    check_width = pdf.page_size[0]
    dollars_x = check_width - 1
    add_text(pdf, dollars_x, y_offset + dollars_y, "DOLLARS")
    add_text(pdf, left_x, y_offset + memo_y, "MEMO")

    line = "_________________________________________________"
    width = get_string_length(pdf, line)
    add_text(pdf, 6.5 - width/2, y_offset + bottom_y - pdf.font_size, line)
    line = "AUTHORIZED SIGNATURE"
    width = get_string_length(pdf, line)
    add_text(pdf, 6.5 - width/2, y_offset + bottom_y, line)
    add_text(pdf, 6.25, y_offset + date_y, "DATE")

    pdf.set_font("AvenirBook", style='', size=12)
    add_text(pdf, 6.7, y_offset + payee_y, "$")

def number_to_words(amount):
    p = inflect.engine()
    try:
        normalized_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid amount for number_to_words: {amount!r}") from exc
    dollars, cents = f"{normalized_amount:.2f}".split(".")
    dollar_words = p.number_to_words(int(dollars))
    if "and" in dollar_words:
        dollar_words = dollar_words.replace(" and", "")
    cents_words = f"{cents}/100"
    return f"{dollar_words} and {cents_words}"

def add_check_info(pdf, payee=None, amount=None, date=None, memo=None, position=1):
    position = position - 1
    y_offset = 3.5 * position
    pdf.set_font("Arial", size=12, style='')

    payee_coords = (1.2, y_offset + payee_y)
    date_coords  = (6.75, y_offset + date_y)
    memo_coords  = (first_tab, y_offset + memo_y)

    if payee:
        add_text(pdf, *payee_coords, txt=payee)
    if date:
        add_text(pdf, *date_coords, txt=date)
    if memo:
        add_text(pdf, *memo_coords, txt=memo)

    if amount:
        formatted_amount = "**" + "{:,.2f}".format(float(amount))
        amount_in_words_list = []
        for word in number_to_words(amount).replace(',', '').split():
            if '-' in word:
                compound_word = '-'.join(part.capitalize() for part in word.split('-'))
                amount_in_words_list.append(compound_word)
            elif word != "and":
                amount_in_words_list.append(word.capitalize())
            else:
                amount_in_words_list.append(word)
        amount_in_words = ' '.join(amount_in_words_list) + " "

        words_width = get_string_length(pdf, amount_in_words)
        asterisk_width = get_string_length(pdf, "*")
        page_width = pdf.w
        check_width = pdf.page_size[0]
        dollars_x = check_width - 1
        total_space = dollars_x - first_tab
        remaining_space = total_space - words_width - 1
        num_asterisks = int(remaining_space / asterisk_width)
        amount_in_words_with_asterisks = amount_in_words + "*" * num_asterisks

        amount_width = get_string_length(pdf, formatted_amount)
        amount_x = 7.875 - amount_width
        amount_coords = (amount_x, payee_y + y_offset)
        amount_words_coords = (first_tab, dollars_y + y_offset)

        add_text(pdf, *amount_coords, txt=formatted_amount)
        add_text(pdf, *amount_words_coords, txt=amount_in_words_with_asterisks)

def add_micr_line(pdf, check_number, routing_number, account_number, style="A", position=1):
    ensure_fonts_available(["MICR"])
    pdf.add_font('MICR', '', str(REQUIRED_FONTS["MICR"]), uni=True)
    pdf.set_font("MICR", size=10.089686098654708)
    print(pdf.w)
    print(pdf.h)
    print(pdf.page_size)
    page_width = pdf.w
    check_width = pdf.page_size[0]
    position = position - 1
    x_correction = -0.02
    y_correction = 0.02
    y_offset = 3.5 * position

    micr_y = 3.5 - 0.1875 - 0.0625 + y_correction + y_offset

    if 'S' == style:
        formatted_check_number = f"{check_number:04}"
    else:
        formatted_check_number = f"{check_number:06}"

    routing_info = f"T{routing_number}T"
    text_width = get_string_length(pdf, routing_info)
    micr_x = check_width - text_width - 0.3125 - (32 * 0.125) + x_correction
    add_text(pdf, micr_x, micr_y, routing_info)

    account_number_info = f" {account_number}O"
    text_width = get_string_length(pdf, routing_info)
    micr_x = check_width - text_width - 0.3125 - (19 * 0.125) + x_correction
    add_text(pdf, micr_x, micr_y, account_number_info)

    if 'S' == style:
        micr_info = f"  {formatted_check_number}"
        text_width = get_string_length(pdf, micr_info)
        micr_x = check_width - text_width - 0.3125 - (13 * 0.125) + x_correction
    else:
        micr_info = f"O{formatted_check_number}O"
        text_width = get_string_length(pdf, micr_info)
        micr_x = check_width - text_width - 0.3125 - (44 * 0.125) - 0.01
    add_text(pdf, micr_x, micr_y, micr_info)

def add_check_number(pdf, check_number, position=1):
    pdf.set_font("Arial", size=12)
    position = position - 1
    y_offset = 3.5 * position

    page_width = pdf.w
    check_width = pdf.page_size[0]
    check_number_x = check_width - 0.3125
    check_number_y = top_y + y_offset

    check_str = str(check_number)
    check_number_width = get_string_length(pdf, check_str)
    add_text(pdf, check_number_x - check_number_width, check_number_y, check_str)

def create_check(payee, amount, date, memo, position=1, filename="check.pdf",
                 checks_per_page=3, page_size=(8.5, 11.0)):
    pdf = PDF(checks_per_page=checks_per_page, page_size=page_size)
    add_check_info(pdf, payee, amount, date, memo, position=position)
    pdf.output(filename)


def add_check_titles_safe(pdf, position=1):
    try:
        add_check_titles(pdf, position=position)
    except RuntimeError as exc:
        raise RuntimeError(f"Unable to render check titles: {exc}") from exc


def add_micr_line_safe(pdf, check_number, routing_number, account_number, style="A", position=1):
    try:
        add_micr_line(
            pdf,
            check_number=check_number,
            routing_number=routing_number,
            account_number=account_number,
            style=style,
            position=position,
        )
    except RuntimeError as exc:
        raise RuntimeError(f"Unable to render MICR line: {exc}") from exc


def create_blank_checks(
    *,
    filename: str,
    checks_per_page: int,
    page_size: tuple[float, float],
    total_checks: int,
    first_check_number: int,
    owner_name: str | None = None,
    owner_address: str | None = None,
    bank_name: str | None = None,
    bank_address: str | None = None,
    fractional_routing: str | None = None,
    routing_number: str | None = None,
    account_number: str | None = None,
    micr_style: str = "A",
) -> None:
    pdf = PDF(checks_per_page=checks_per_page, page_size=page_size)
    for idx in range(total_checks):
        if idx and idx % checks_per_page == 0:
            pdf.add_page()
        position = (idx % checks_per_page) + 1
        add_check_titles_safe(pdf, position=position)
        add_owner_info(pdf, owner_name=owner_name, owner_address=owner_address, position=position)
        add_bank_info(
            pdf,
            bank_name=bank_name,
            bank_address=bank_address,
            fract_routing_num=fractional_routing,
            position=position,
        )
        check_number = first_check_number + idx
        add_check_number(pdf, check_number, position=position)
        if routing_number and account_number:
            add_micr_line_safe(
                pdf,
                check_number=check_number,
                routing_number=routing_number,
                account_number=account_number,
                style=micr_style,
                position=position,
            )
    pdf.output(filename)


def create_blank_check_pair(
    *,
    micr_filename: str,
    nomicr_filename: str,
    checks_per_page: int,
    page_size: tuple[float, float],
    total_checks: int,
    first_check_number: int,
    owner_name: str | None = None,
    owner_address: str | None = None,
    bank_name: str | None = None,
    bank_address: str | None = None,
    fractional_routing: str | None = None,
    routing_number: str | None = None,
    account_number: str | None = None,
    micr_style: str = "B",
) -> None:
    pdf_micr = PDF(checks_per_page=checks_per_page, page_size=page_size)
    pdf_nomicr = PDF(checks_per_page=checks_per_page, page_size=page_size)
    for idx in range(total_checks):
        if idx and idx % checks_per_page == 0:
            pdf_micr.add_page()
            pdf_nomicr.add_page()
        position = (idx % checks_per_page) + 1
        check_number = first_check_number + idx
        add_check_number(pdf_micr, check_number, position=position)
        if routing_number and account_number:
            add_micr_line_safe(
                pdf_micr,
                check_number=check_number,
                routing_number=routing_number,
                account_number=account_number,
                style=micr_style,
                position=position,
            )
        add_check_titles_safe(pdf_nomicr, position=position)
        add_owner_info(pdf_nomicr, owner_name=owner_name, owner_address=owner_address, position=position)
        add_bank_info(
            pdf_nomicr,
            bank_name=bank_name,
            bank_address=bank_address,
            fract_routing_num=fractional_routing,
            position=position,
        )
    pdf_micr.output(micr_filename)
    pdf_nomicr.output(nomicr_filename)

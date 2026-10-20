from __future__ import annotations

import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from database import (
    get_all_stores,
    get_or_create_product,
    get_or_create_offer,
    add_price_history,
    create_scrape_job,
    finish_scrape_job,
)

from verification import verify_all_offers


REQUEST_TIMEOUT = 30
MAX_PRODUCTS_PER_STORE = 50

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7",
}


PERSIAN_DIGITS = str.maketrans(
    "Û°Û±Û²Û³Û´ÛµÛ¶Û·Û¸Û¹Ù Ù¡Ù¢Ù£Ù¤Ù¥Ù¦Ù§Ù¨Ù©",
    "01234567890123456789",
)


def normalize_digits(value):
    if value is None:
        return ""

    return str(value).translate(PERSIAN_DIGITS)


def parse_integer(value):
    """
    ØªØ¨Ø¯ÛŒÙ„ Ù…Ù‚Ø¯Ø§Ø± Ù…ØªÙ†ÛŒ Ù‚ÛŒÙ…Øª Ø¨Ù‡ Ø¹Ø¯Ø¯ ØµØ­ÛŒØ­.
    """

    if value is None:
        return None

    text = normalize_digits(value)

    text = (
        text.replace(",", "")
        .replace("Ù¬", "")
        .replace("ØŒ", "")
        .replace(" ", "")
        .strip()
    )

    digits = re.sub(r"[^\d]", "", text)

    if not digits:
        return None

    try:
        number = int(digits)
    except (TypeError, ValueError):
        return None

    if number <= 0:
        return None

    if number > 9_000_000_000_000_000:
        return None

    return number


def calculate_discount(original_price, current_price):
    """
    Ù…Ø­Ø§Ø³Ø¨Ù‡ Ø¯Ø±ØµØ¯ ØªØ®ÙÛŒÙ Ø¨Ø± Ø§Ø³Ø§Ø³ Ù‚ÛŒÙ…Øª Ù‚Ø¨Ù„ Ùˆ Ù‚ÛŒÙ…Øª ÙØ¹Ù„ÛŒ.
    """

    if not original_price or not current_price:
        return None

    if original_price <= 0 or current_price <= 0:
        return None

    if current_price >= original_price:
        return 0

    discount = (
        (original_price - current_price)
        / original_price
        * 100
    )

    return round(discount, 2)


def absolute_url(base_url, value):
    if not value:
        return None

    return urljoin(base_url, value)


def extract_image_url(image_tag, base_url):
    if not image_tag:
        return None

    for attribute in (
        "src",
        "data-src",
        "data-lazy-src",
        "data-original",
    ):
        value = image_tag.get(attribute)

        if value:
            return absolute_url(base_url, value)

    srcset = image_tag.get("srcset")

    if srcset:
        first_item = srcset.split(",")[0].strip()

        if first_item:
            image_url = first_item.split(" ")[0]
            return absolute_url(base_url, image_url)

    return None


def get_product_id_from_url(product_url):
    if not product_url:
        return None

    match = re.search(
        r"/product/(\d+)",
        product_url,
    )

    if match:
        return match.group(1)

    return None


def fetch_html(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or response.encoding
    )

    return response.text


def parse_basalam(html, base_url):
    """
    Ø§Ø³ØªØ®Ø±Ø§Ø¬ Ù…Ø­ØµÙˆÙ„Ø§Øª ØªØ®ÙÛŒÙâ€ŒØ¯Ø§Ø± Ø§Ø² Ø³Ø§Ø®ØªØ§Ø± ÙØ¹Ù„ÛŒ Ø¨Ø§Ø³Ù„Ø§Ù….

    Ú©Ø§Ø±Øª Ù…Ø­ØµÙˆÙ„:
        a[data-component="amazing-offerr-basalam-2"]

    Ø¹Ù†ÙˆØ§Ù†:
        h3

    Ù‚ÛŒÙ…Øª Ù‚Ø¨Ù„:
        ._1r8_uU

    Ø¯Ø±ØµØ¯ ØªØ®ÙÛŒÙ Ø§Ø¹Ù„Ø§Ù…ÛŒ:
        ._8nwQlk

    Ù‚ÛŒÙ…Øª ÙØ¹Ù„ÛŒ:
        ._OEyF_
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    cards = soup.find_all(
        "a",
        attrs={
            "data-component": "amazing-offerr-basalam-2"
        },
    )

    products = []

    for card in cards:
        try:
            title_tag = card.find("h3")

            if not title_tag:
                continue

            title = title_tag.get("title")

            if not title:
                title = title_tag.get_text(
                    " ",
                    strip=True,
                )

            if not title:
                continue

            href = card.get("href")

            if not href:
                continue

            product_url = absolute_url(
                base_url,
                href,
            )

            original_tag = card.select_one(
                "._1r8_uU"
            )

            current_tag = card.select_one(
                "._OEyF_"
            )

            discount_tag = card.select_one(
                "._8nwQlk"
            )

            if not original_tag or not current_tag:
                continue

            original_price = parse_integer(
                original_tag.get_text(
                    " ",
                    strip=True,
                )
            )

            current_price = parse_integer(
                current_tag.get_text(
                    " ",
                    strip=True,
                )
            )

            if not original_price or not current_price:
                continue

            calculated_discount = calculate_discount(
                original_price,
                current_price,
            )

            if calculated_discount is None:
                continue

            claimed_discount = None

            if discount_tag:
                claimed_text = discount_tag.get_text(
                    " ",
                    strip=True,
                )

                claimed_discount = parse_integer(
                    claimed_text
                )

            image_tag = card.find("img")

            image_url = extract_image_url(
                image_tag,
                base_url,
            )

            external_product_id = (
                get_product_id_from_url(
                    product_url
                )
            )

            products.append(
                {
                    "title": title.strip(),
                    "product_url": product_url,
                    "image_url": image_url,
                    "external_product_id": (
                        external_product_id
                    ),
                    "original_price": original_price,
                    "current_price": current_price,
                    "claimed_discount_percent": (
                        claimed_discount
                    ),
                    "calculated_discount_percent": (
                        calculated_discount
                    ),
                    "currency": "IRT",
                }
            )

            if len(products) >= MAX_PRODUCTS_PER_STORE:
                break

        except Exception as exc:
            print(
                f"Ø®Ø·Ø§ Ø¯Ø± Ù¾Ø±Ø¯Ø§Ø²Ø´ ÛŒÚ© Ù…Ø­ØµÙˆÙ„ Ø¨Ø§Ø³Ù„Ø§Ù…: {exc}"
            )

    return products


def save_basalam_products(
    store,
    products,
    job_id,
):
    saved_count = 0
    error_count = 0

    for item in products:
        try:
            product = get_or_create_product(
                title=item["title"],
                canonical_url=item["product_url"],
                image_url=item["image_url"],
                category=store["category"],
                external_product_id=(
                    item["external_product_id"]
                ),
            )

            product_id = product["id"]

            offer = get_or_create_offer(
                product_id=product_id,
                store_id=store["id"],
                product_url=item["product_url"],
                seller_name=store["name"],
                seller_type="MARKETPLACE",
                current_price=item["current_price"],
                original_price=item["original_price"],
                currency=item["currency"],
                availability="IN_STOCK",
            )

            offer_id = offer["id"]

            add_price_history(
                offer_id=offer_id,
                price=item["current_price"],
                original_price=item["original_price"],
                discount_percent=(
                    item[
                        "calculated_discount_percent"
                    ]
                ),
                source="basalam",
            )

            saved_count += 1

            claimed = item[
                "claimed_discount_percent"
            ]

            calculated = item[
                "calculated_discount_percent"
            ]

            if claimed is not None:
                difference = abs(
                    float(claimed)
                    - float(calculated)
                )

                if difference <= 1:
                    verification_text = (
                        f"ØªØ®ÙÛŒÙ Ø§Ø¹Ù„Ø§Ù…ÛŒ Ø¨Ø§Ø³Ù„Ø§Ù… "
                        f"{claimed}% Ø§Ø³Øª Ùˆ "
                        f"ØªØ®ÙÛŒÙ Ù…Ø­Ø§Ø³Ø¨Ø§ØªÛŒ "
                        f"{calculated}% Ø§Ø³ØªØ› "
                        f"Ø§Ø®ØªÙ„Ø§Ù Ø¯Ø± Ù…Ø­Ø¯ÙˆØ¯Ù‡ Ù‚Ø§Ø¨Ù„ Ù‚Ø¨ÙˆÙ„ Ø§Ø³Øª."
                    )
                else:
                    verification_text = (
                        f"ØªØ®ÙÛŒÙ Ø§Ø¹Ù„Ø§Ù…ÛŒ Ø¨Ø§Ø³Ù„Ø§Ù… "
                        f"{claimed}% Ø§Ø³Øª Ø§Ù…Ø§ "
                        f"ØªØ®ÙÛŒÙ Ù…Ø­Ø§Ø³Ø¨Ø§ØªÛŒ "
                        f"{calculated}% Ø§Ø³Øª."
                    )
            else:
                verification_text = (
                    "Ù‚ÛŒÙ…Øª Ù‚Ø¨Ù„ Ùˆ Ù‚ÛŒÙ…Øª ÙØ¹Ù„ÛŒ Ø§Ø² "
                    "Ø³Ø§Ø®ØªØ§Ø± Ú©Ø§Ø±Øª Ù…Ø­ØµÙˆÙ„ Ø§Ø³ØªØ®Ø±Ø§Ø¬ "
                    "Ø´Ø¯Ù‡â€ŒØ§Ù†Ø¯Ø› Ø¯Ø±ØµØ¯ ØªØ®ÙÛŒÙ Ø§Ø¹Ù„Ø§Ù…ÛŒ "
                    "Ø¯Ø± Ú©Ø§Ø±Øª Ù…ÙˆØ¬ÙˆØ¯ Ù†Ø¨ÙˆØ¯."
                )

            print(
                f"Ø«Ø¨Øª Ø´Ø¯: {item['title'][:60]}"
            )

            print(
                f"  Ù‚Ø¨Ù„: "
                f"{item['original_price']:,} ØªÙˆÙ…Ø§Ù†"
            )

            print(
                f"  ÙØ¹Ù„ÛŒ: "
                f"{item['current_price']:,} ØªÙˆÙ…Ø§Ù†"
            )

            print(
                f"  ØªØ®ÙÛŒÙ Ù…Ø­Ø§Ø³Ø¨Ø§ØªÛŒ: "
                f"{calculated}%"
            )

            print(
                f"  Ø¨Ø±Ø±Ø³ÛŒ Ø§ÙˆÙ„ÛŒÙ‡: "
                f"{verification_text}"
            )

        except Exception as exc:
            error_count += 1

            print(
                f"Ø®Ø·Ø§ Ø¯Ø± Ø°Ø®ÛŒØ±Ù‡ Ù…Ø­ØµÙˆÙ„ "
                f"{item.get('title', '')[:50]}: "
                f"{exc}"
            )

    finish_scrape_job(
        job_id=job_id,
        status=(
            "SUCCESS"
            if error_count == 0
            else "PARTIAL"
        ),
        products_found=len(products),
        products_saved=saved_count,
        offers_saved=saved_count,
        error_count=error_count,
        error_message=(
            None
            if error_count == 0
            else "Ø¨Ø±Ø®ÛŒ Ù…Ø­ØµÙˆÙ„Ø§Øª Ù‡Ù†Ú¯Ø§Ù… Ø°Ø®ÛŒØ±Ù‡ "
            "Ø¨Ø§ Ø®Ø·Ø§ Ù…ÙˆØ§Ø¬Ù‡ Ø´Ø¯Ù†Ø¯."
        ),
    )

    return saved_count, error_count


def scrape_store(store):
    store_name = store["name"]
    store_url = store["website_url"]
    store_slug = store["slug"]

    print()
    print("=" * 70)
    print(
        f"Ø¯Ø± Ø­Ø§Ù„ Ø¨Ø±Ø±Ø³ÛŒ ÙØ±ÙˆØ´Ú¯Ø§Ù‡: {store_name}"
    )
    print(
        f"Ø¢Ø¯Ø±Ø³: {store_url}"
    )
    print("=" * 70)

    # create_scrape_job ÛŒÚ© sqlite3.Row Ø¨Ø±Ù…ÛŒâ€ŒÚ¯Ø±Ø¯Ø§Ù†Ø¯.
    # Ø¨Ù†Ø§Ø¨Ø±Ø§ÛŒÙ† Ø´Ù†Ø§Ø³Ù‡ Ø¹Ø¯Ø¯ÛŒ Ø¢Ù† Ø±Ø§ Ø¬Ø¯Ø§ Ù…ÛŒâ€ŒÚ©Ù†ÛŒÙ….
    job = create_scrape_job(
        store_id=store["id"]
    )

    job_id = job["id"]

    started = time.time()

    try:
        html = fetch_html(store_url)

        if store_slug == "basalam":
            products = parse_basalam(
                html=html,
                base_url=store_url,
            )
        else:
            products = []

        print(
            f"{store_name}: "
            f"{len(products)} Ù…Ø­ØµÙˆÙ„ Ø¨Ø§ Ù‚ÛŒÙ…Øª "
            f"Ø³Ø§Ø®ØªØ§Ø±ÛŒ Ù…Ø¹ØªØ¨Ø± Ù¾ÛŒØ¯Ø§ Ø´Ø¯."
        )

        saved_count, error_count = (
            save_basalam_products(
                store=store,
                products=products,
                job_id=job_id,
            )
        )

        elapsed = round(
            time.time() - started,
            2,
        )

        print(
            f"{store_name}: "
            f"{saved_count} Ù…Ø­ØµÙˆÙ„ Ø¯Ø± Ø¯ÛŒØªØ§Ø¨ÛŒØ³ "
            f"Ø«Ø¨Øª/Ø¨Ù‡â€ŒØ±ÙˆØ²Ø±Ø³Ø§Ù†ÛŒ Ø´Ø¯."
        )

        print(
            f"Ø²Ù…Ø§Ù† Ø§Ø¬Ø±Ø§: {elapsed} Ø«Ø§Ù†ÛŒÙ‡"
        )

        return {
            "found": len(products),
            "saved": saved_count,
            "errors": error_count,
        }

    except requests.RequestException as exc:
        message = (
            f"Ø®Ø·Ø§ÛŒ Ø§Ø±ØªØ¨Ø§Ø· Ø¨Ø§ ÙØ±ÙˆØ´Ú¯Ø§Ù‡: {exc}"
        )

        print(message)

        finish_scrape_job(
            job_id=job_id,
            status="FAILED",
            products_found=0,
            products_saved=0,
            offers_saved=0,
            error_count=1,
            error_message=message,
        )

        return {
            "found": 0,
            "saved": 0,
            "errors": 1,
        }

    except Exception as exc:
        message = (
            f"Ø®Ø·Ø§ÛŒ ØºÛŒØ±Ù…Ù†ØªØ¸Ø±Ù‡: {exc}"
        )

        print(message)

        finish_scrape_job(
            job_id=job_id,
            status="FAILED",
            products_found=0,
            products_saved=0,
            offers_saved=0,
            error_count=1,
            error_message=message,
        )

        return {
            "found": 0,
            "saved": 0,
            "errors": 1,
        }


def fetch_and_scrape():
    """
    Ø§Ø¬Ø±Ø§ÛŒ Ù…Ø±Ø­Ù„Ù‡ ÙØ¹Ù„ÛŒ Ø¬Ù…Ø¹â€ŒØ¢ÙˆØ±ÛŒ Ø§Ø·Ù„Ø§Ø¹Ø§Øª.

    Ø¯Ø± Ø§ÛŒÙ† Ù…Ø±Ø­Ù„Ù‡ ÙÙ‚Ø· Ø¨Ø§Ø³Ù„Ø§Ù… ÙØ¹Ø§Ù„ Ø§Ø³Øª.
    Ù¾Ø³ Ø§Ø² ØªØ£ÛŒÛŒØ¯ ØµØ­Øª Ø¯Ø§Ø¯Ù‡â€ŒÙ‡Ø§ØŒ ÙØ±ÙˆØ´Ú¯Ø§Ù‡â€ŒÙ‡Ø§ÛŒ Ø¯ÛŒÚ¯Ø±
    Ø¨Ù‡â€ŒØµÙˆØ±Øª Ø§Ø®ØªØµØ§ØµÛŒ Ø§Ø¶Ø§ÙÙ‡ Ø®ÙˆØ§Ù‡Ù†Ø¯ Ø´Ø¯.
    """

    stores = get_all_stores()

    target_stores = [
        store
        for store in stores
        if store["slug"] == "basalam"
    ]

    if not target_stores:
        print(
            "ÙØ±ÙˆØ´Ú¯Ø§Ù‡ Ø¨Ø§Ø³Ù„Ø§Ù… Ø¯Ø± Ø¯ÛŒØªØ§Ø¨ÛŒØ³ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯."
        )
        return 0

    total_found = 0
    total_saved = 0
    total_errors = 0

    print()
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] "
        "Ø´Ø±ÙˆØ¹ Ø¨Ø±Ø±Ø³ÛŒ ÙØ±ÙˆØ´Ú¯Ø§Ù‡ Ø¨Ø§Ø³Ù„Ø§Ù…"
    )

    for store in target_stores:
        result = scrape_store(store)

        total_found += result["found"]
        total_saved += result["saved"]
        total_errors += result["errors"]

    # Verification runs only after the complete scrape.
    # This lets it compare fresh offers and price history consistently.
    if total_errors == 0 and total_saved > 0:
        try:
            verification_results = verify_all_offers()

            print()
            print("=" * 70)
            print("نتیجه بررسی اعتبار تخفیف‌ها")
            print("=" * 70)

            status_counts = {}
            for verification in verification_results:
                status = verification.get("status", "UNKNOWN")
                status_counts[status] = status_counts.get(status, 0) + 1

            print(f"تعداد پیشنهادهای بررسی‌شده: {len(verification_results)}")
            for status in (
                "VERIFIED",
                "LIKELY_REAL",
                "SUSPICIOUS",
                "UNKNOWN",
            ):
                print(f"  {status}: {status_counts.get(status, 0)}")

            print("=" * 70)

        except Exception as exc:
            print()
            print("=" * 70)
            print(f"خطا در اجرای موتور بررسی اعتبار تخفیف‌ها: {exc}")
            print("=" * 70)

    print()
    print("=" * 70)
    print("Ù†ØªÛŒØ¬Ù‡ Ù†Ù‡Ø§ÛŒÛŒ")
    print("=" * 70)
    print(
        f"Ø§Ø·Ù„Ø§Ø¹Ø§Øª Ù¾ÛŒØ¯Ø§ Ø´Ø¯Ù‡: {total_found}"
    )
    print(
        f"Ù…Ø­ØµÙˆÙ„Ø§Øª Ø«Ø¨Øª/Ø¨Ù‡â€ŒØ±ÙˆØ²Ø±Ø³Ø§Ù†ÛŒ Ø´Ø¯Ù‡: "
        f"{total_saved}"
    )
    print(
        f"Ø®Ø·Ø§Ù‡Ø§: {total_errors}"
    )
    print("=" * 70)

    return total_saved


if __name__ == "__main__":
    fetch_and_scrape()

from __future__ import annotations

from typing import Any

import database


MIN_HISTORY_FOR_CONFIRMED = 2

VERIFIED_THRESHOLD = 80
LIKELY_REAL_THRESHOLD = 55


def safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_percent_difference(
    reference_price: float | None,
    current_price: float | None,
) -> float | None:
    reference = safe_float(reference_price)
    current = safe_float(current_price)

    if reference is None or current is None or reference <= 0:
        return None

    return round(((reference - current) / reference) * 100, 2)


def calculate_claimed_discount(
    original_price: float | None,
    current_price: float | None,
) -> float | None:
    return calculate_percent_difference(
        original_price,
        current_price,
    )


def get_offer(offer_id: int):
    connection = database.get_connection()

    try:
        row = connection.execute(
            """
            SELECT
                o.*,
                p.title AS product_title,
                p.brand,
                p.model,
                p.category,
                s.name AS store_name
            FROM offers o
            JOIN products p ON p.id = o.product_id
            JOIN stores s ON s.id = o.store_id
            WHERE o.id = ?
            """,
            (offer_id,),
        ).fetchone()

        return row
    finally:
        connection.close()


def get_price_history(offer_id: int):
    connection = database.get_connection()

    try:
        rows = connection.execute(
            """
            SELECT *
            FROM price_history
            WHERE offer_id = ?
            ORDER BY recorded_at ASC, id ASC
            """,
            (offer_id,),
        ).fetchall()

        return rows
    finally:
        connection.close()


def analyze_historical_price(
    offer: Any,
    history: list[Any],
) -> dict[str, Any]:
    current_price = safe_float(offer["current_price"])

    prices: list[float] = []

    for row in history:
        price = safe_float(row["price"])

        if price is not None and price > 0:
            prices.append(price)

    history_count = len(prices)

    result = {
        "history_count": history_count,
        "historical_discount_percent": None,
        "lowest_historical_price": None,
        "highest_historical_price": None,
        "previous_price": None,
        "historical_price_change": None,
        "has_previous_price": False,
    }

    if not prices:
        return result

    result["lowest_historical_price"] = min(prices)
    result["highest_historical_price"] = max(prices)

    if history_count < 2:
        return result

    previous_price = prices[-2]

    result["previous_price"] = previous_price
    result["has_previous_price"] = True

    if current_price is None or current_price <= 0:
        return result

    historical_discount = calculate_percent_difference(
        previous_price,
        current_price,
    )

    result["historical_discount_percent"] = historical_discount
    result["historical_price_change"] = historical_discount

    return result


def get_market_offers(offer: Any):
    connection = database.get_connection()

    try:
        rows = connection.execute(
            """
            SELECT
                o.*,
                s.name AS store_name
            FROM offers o
            JOIN stores s ON s.id = o.store_id
            WHERE
                o.product_id = ?
                AND o.is_active = 1
                AND o.id != ?
                AND o.current_price IS NOT NULL
                AND o.current_price > 0
            ORDER BY o.current_price ASC
            """,
            (
                offer["product_id"],
                offer["id"],
            ),
        ).fetchall()

        return rows
    finally:
        connection.close()


def analyze_market_price(
    offer: Any,
    market_offers: list[Any],
) -> dict[str, Any]:
    current_price = safe_float(offer["current_price"])

    market_prices: list[float] = []

    for row in market_offers:
        price = safe_float(row["current_price"])

        if price is not None and price > 0:
            market_prices.append(price)

    result = {
        "market_offer_count": len(market_prices),
        "lowest_market_price": None,
        "average_market_price": None,
        "market_discount_percent": None,
    }

    if not market_prices:
        return result

    lowest_market_price = min(market_prices)
    average_market_price = sum(market_prices) / len(market_prices)

    result["lowest_market_price"] = lowest_market_price
    result["average_market_price"] = round(
        average_market_price,
        2,
    )

    if current_price is None or current_price <= 0:
        return result

    market_discount = calculate_percent_difference(
        average_market_price,
        current_price,
    )

    result["market_discount_percent"] = market_discount

    return result


def calculate_verification_score(
    claimed_discount: float | None,
    historical_discount: float | None,
    market_discount: float | None,
    history_count: int,
    market_offer_count: int,
) -> float:
    """
    امتیازدهی اعتبار تخفیف:

    تخفیف اعلامی فروشگاه:
        حداکثر 10 امتیاز.
        به تنهایی اثبات واقعی بودن تخفیف نیست.

    سابقه قیمت:
        حداکثر 55 امتیاز.

    مقایسه بازار:
        حداکثر 35 امتیاز.

    شواهد منفی باعث کاهش امتیاز می‌شوند.
    """

    score = 0.0

    # ---------------------------------------------------------
    # 1. Claimed discount
    # ---------------------------------------------------------

    if claimed_discount is not None and claimed_discount > 0:
        if claimed_discount >= 40:
            score += 10
        elif claimed_discount >= 25:
            score += 8
        elif claimed_discount >= 10:
            score += 6
        else:
            score += 3

    # ---------------------------------------------------------
    # 2. Historical evidence
    # ---------------------------------------------------------

    if history_count >= MIN_HISTORY_FOR_CONFIRMED:
        if historical_discount is not None:

            if historical_discount >= 30:
                score += 55

            elif historical_discount >= 20:
                score += 45

            elif historical_discount >= 10:
                score += 35

            elif historical_discount > 0:
                score += 25

            elif historical_discount == 0:
                score += 0

            else:
                # قیمت فعلی نسبت به قیمت قبلی افزایش یافته است.
                score -= 40

    # ---------------------------------------------------------
    # 3. Market evidence
    # ---------------------------------------------------------

    if market_offer_count > 0:
        if market_discount is not None:

            if market_discount >= 30:
                score += 35

            elif market_discount >= 20:
                score += 30

            elif market_discount >= 10:
                score += 25

            elif market_discount > 0:
                score += 15

            elif market_discount == 0:
                score += 0

            else:
                # میانگین بازار از قیمت فعلی پایین‌تر است.
                score -= 35

    return round(
        max(0.0, min(100.0, score)),
        2,
    )


def determine_status(
    score: float,
    historical_discount: float | None,
    market_discount: float | None,
    history_count: int,
    market_offer_count: int,
) -> str:
    """
    تعیین وضعیت تخفیف.

    SUSPICIOUS:
        فقط زمانی که شواهد منفی مشخص وجود داشته باشد.

    UNKNOWN:
        داده کافی برای تأیید یا رد تخفیف نداریم.

    LIKELY_REAL:
        شواهد مثبت وجود دارد ولی برای تأیید قطعی کافی نیست.

    VERIFIED:
        شواهد مثبت قوی وجود دارد.
    """

    # ---------------------------------------------------------
    # Negative evidence
    # ---------------------------------------------------------

    if (
        historical_discount is not None
        and history_count >= MIN_HISTORY_FOR_CONFIRMED
        and historical_discount < 0
    ):
        return "SUSPICIOUS"

    if (
        market_discount is not None
        and market_offer_count > 0
        and market_discount < 0
    ):
        return "SUSPICIOUS"

    # ---------------------------------------------------------
    # Positive evidence
    # ---------------------------------------------------------

    has_positive_historical_evidence = (
        history_count >= MIN_HISTORY_FOR_CONFIRMED
        and historical_discount is not None
        and historical_discount > 0
    )

    has_positive_market_evidence = (
        market_offer_count > 0
        and market_discount is not None
        and market_discount > 0
    )

    has_positive_evidence = (
        has_positive_historical_evidence
        or has_positive_market_evidence
    )

    # تخفیف اعلامی فروشگاه به تنهایی کافی نیست.
    if not has_positive_evidence:
        return "UNKNOWN"

    if score >= VERIFIED_THRESHOLD:
        return "VERIFIED"

    if score >= LIKELY_REAL_THRESHOLD:
        return "LIKELY_REAL"

    return "UNKNOWN"


def build_reason(
    offer: Any,
    claimed_discount: float | None,
    historical: dict[str, Any],
    market: dict[str, Any],
    score: float,
    status: str,
) -> str:
    parts: list[str] = []

    if claimed_discount is not None:
        parts.append(
            f"تخفیف محاسباتی بر اساس قیمت قبل و فعلی "
            f"{claimed_discount:.1f}% است."
        )
    else:
        parts.append(
            "قیمت قبل یا فعلی برای محاسبه تخفیف کامل در دسترس نیست."
        )

    history_count = historical["history_count"]
    historical_discount = historical["historical_discount_percent"]

    if history_count < MIN_HISTORY_FOR_CONFIRMED:
        parts.append(
            "سابقه قیمت کافی برای تأیید تاریخی تخفیف وجود ندارد."
        )

    elif historical_discount is None:
        parts.append(
            "قیمت فعلی یا سابقه قیمت برای تحلیل تاریخی معتبر نیست."
        )

    elif historical_discount > 0:
        parts.append(
            f"قیمت فعلی نسبت به قیمت قبلی "
            f"{historical_discount:.1f}% کاهش یافته است."
        )

    elif historical_discount == 0:
        parts.append(
            "قیمت فعلی نسبت به قیمت قبلی تغییر معناداری ندارد."
        )

    else:
        parts.append(
            f"قیمت فعلی نسبت به قیمت قبلی "
            f"{abs(historical_discount):.1f}% افزایش یافته است."
        )

    market_count = market["market_offer_count"]
    market_discount = market["market_discount_percent"]

    if market_count == 0:
        parts.append(
            "در حال حاضر پیشنهاد مشابه از فروشگاه دیگری "
            "برای مقایسه در دیتابیس وجود ندارد."
        )

    elif market_discount is None:
        parts.append(
            f"{market_count} پیشنهاد مشابه برای مقایسه وجود دارد، "
            "اما مقایسه قیمت معتبر انجام نشد."
        )

    elif market_discount > 0:
        parts.append(
            f"قیمت فعلی نسبت به میانگین قیمت بازار "
            f"{market_discount:.1f}% پایین‌تر است."
        )

    elif market_discount == 0:
        parts.append(
            "قیمت فعلی تقریباً برابر با میانگین قیمت بازار است."
        )

    else:
        parts.append(
            f"قیمت فعلی نسبت به میانگین قیمت بازار "
            f"{abs(market_discount):.1f}% بالاتر است."
        )

    if status == "VERIFIED":
        parts.append(
            "شواهد تاریخی و/یا بازار برای واقعی بودن تخفیف کافی است."
        )

    elif status == "LIKELY_REAL":
        parts.append(
            "شواهد مثبت برای واقعی بودن تخفیف وجود دارد، "
            "اما برای تأیید قطعی داده بیشتری لازم است."
        )

    elif status == "SUSPICIOUS":
        parts.append(
            "شواهد موجود دارای نشانه‌های مشخصی از "
            "غیرواقعی یا نامطمئن بودن تخفیف است."
        )

    else:
        parts.append(
            "اطلاعات کافی برای تأیید یا رد واقعی بودن تخفیف وجود ندارد."
        )

    parts.append(
        f"امتیاز اعتبار: {score:.1f}/100."
    )

    return " ".join(parts)


def verify_offer(offer_id: int) -> dict[str, Any] | None:
    offer = get_offer(offer_id)

    if offer is None:
        return None

    current_price = safe_float(
        offer["current_price"]
    )

    original_price = safe_float(
        offer["original_price"]
    )

    claimed_discount = calculate_claimed_discount(
        original_price,
        current_price,
    )

    history = get_price_history(
        offer_id
    )

    historical = analyze_historical_price(
        offer,
        history,
    )

    market_offers = get_market_offers(
        offer
    )

    market = analyze_market_price(
        offer,
        market_offers,
    )

    score = calculate_verification_score(
        claimed_discount=claimed_discount,
        historical_discount=historical[
            "historical_discount_percent"
        ],
        market_discount=market[
            "market_discount_percent"
        ],
        history_count=historical[
            "history_count"
        ],
        market_offer_count=market[
            "market_offer_count"
        ],
    )

    status = determine_status(
        score=score,
        historical_discount=historical[
            "historical_discount_percent"
        ],
        market_discount=market[
            "market_discount_percent"
        ],
        history_count=historical[
            "history_count"
        ],
        market_offer_count=market[
            "market_offer_count"
        ],
    )

    reason = build_reason(
        offer=offer,
        claimed_discount=claimed_discount,
        historical=historical,
        market=market,
        score=score,
        status=status,
    )

    # ---------------------------------------------------------
    # Save verification result.
    #
    # This call exactly matches the current database.py
    # implementation.
    # ---------------------------------------------------------

    database.add_verification_result(
        product_id=offer["product_id"],
        offer_id=offer["id"],
        status=status,
        score=score,
        claimed_discount_percent=claimed_discount,
        historical_discount_percent=historical[
            "historical_discount_percent"
        ],
        market_discount_percent=market[
            "market_discount_percent"
        ],
        lowest_market_price=market[
            "lowest_market_price"
        ],
        average_market_price=market[
            "average_market_price"
        ],
        reason=reason,
    )

    return {
        "offer_id": offer_id,
        "product_id": offer["product_id"],
        "product_title": offer["product_title"],
        "store_name": offer["store_name"],
        "current_price": current_price,
        "original_price": original_price,
        "claimed_discount_percent": claimed_discount,
        "historical_discount_percent": historical[
            "historical_discount_percent"
        ],
        "historical_price_change": historical[
            "historical_price_change"
        ],
        "history_count": historical[
            "history_count"
        ],
        "previous_price": historical[
            "previous_price"
        ],
        "lowest_historical_price": historical[
            "lowest_historical_price"
        ],
        "highest_historical_price": historical[
            "highest_historical_price"
        ],
        "market_discount_percent": market[
            "market_discount_percent"
        ],
        "market_offer_count": market[
            "market_offer_count"
        ],
        "lowest_market_price": market[
            "lowest_market_price"
        ],
        "average_market_price": market[
            "average_market_price"
        ],
        "score": score,
        "status": status,
        "reason": reason,
    }


def verify_all_offers() -> list[dict[str, Any]]:
    connection = database.get_connection()

    try:
        offers = connection.execute(
            """
            SELECT id
            FROM offers
            WHERE is_active = 1
            ORDER BY id
            """
        ).fetchall()

    finally:
        connection.close()

    results: list[dict[str, Any]] = []

    for row in offers:
        result = verify_offer(
            row["id"]
        )

        if result is not None:
            results.append(result)

    return results


def main() -> None:
    print("=" * 60)
    print("Takhfifkadeh - Verification Engine")
    print("=" * 60)

    results = verify_all_offers()

    status_counts: dict[str, int] = {}

    for result in results:
        status = result["status"]

        status_counts[status] = (
            status_counts.get(status, 0) + 1
        )

    print(
        f"Offers checked: {len(results)}"
    )

    print("Status:")

    for status in (
        "VERIFIED",
        "LIKELY_REAL",
        "SUSPICIOUS",
        "UNKNOWN",
    ):
        print(
            f"  {status}: "
            f"{status_counts.get(status, 0)}"
        )


if __name__ == "__main__":
    main()
def calculate_total(items, coupon=None):
    total = sum(item["price"] for item in items)
    if coupon == "SAVE10":
        total = total * 0.9
    return round(total, 2)


def checkout(items, coupon=None):
    return {"total": calculate_total(items, coupon)}

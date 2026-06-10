def money(value):
    return f"RMB {float(value):,.2f}"


def pct(value):
    return f"{float(value):.2%}"


def section(title):
    print("\n" + "=" * 76)
    print(title)
    print("=" * 76)

from datetime import datetime
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "server" / "data" / "eshop.sqlite"
BACKUP_DIR = ROOT / "server" / "data" / "backups"
PREFIX = "v3_bundle_"


PAIRS = [
    # category, antecedent sku, consequent sku, target inserted rows
    ("美妆个护", "sku_00001", "sku_00002", 520),
    ("数码配件", "sku_00232", "sku_00242", 260),
    ("食品饮料", "sku_00153", "sku_00183", 260),
    ("家居生活", "sku_00098", "sku_00073", 260),
    ("办公学习", "sku_00828", "sku_00803", 220),
    ("运动户外", "sku_00292", "sku_00294", 220),
    ("美妆个护", "sku_00005", "sku_00003", 360),
    ("美妆个护", "sku_00008", "sku_00009", 320),
    ("美妆个护", "sku_00022", "sku_00023", 300),
]


def backup_database():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"eshop_before_v3_association_{stamp}.sqlite"
    src = sqlite3.connect(DB_PATH)
    try:
        dst = sqlite3.connect(backup)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return backup


def existing_bundle_rows(cur):
    return cur.execute(
        "select count(*) from order_items where order_item_id like ?",
        (f"{PREFIX}%",),
    ).fetchone()[0]


def sku_info(cur, sku_id):
    row = cur.execute(
        "select sku_id, spu_id, price, cost from sku where sku_id = ?",
        (sku_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"SKU not found: {sku_id}")
    return {
        "sku_id": row[0],
        "spu_id": row[1],
        "price": float(row[2]),
        "cost": float(row[3]),
    }


def candidate_orders(cur, antecedent, consequent, target):
    rows = cur.execute(
        """
        select oi.order_id, oi.sku_id
        from order_items oi
        where oi.sku_id in (?, ?)
        """,
        (antecedent, consequent),
    ).fetchall()
    with_antecedent = []
    with_consequent = set()
    for order_id, sku_id in rows:
        if sku_id == antecedent:
            with_antecedent.append(order_id)
        elif sku_id == consequent:
            with_consequent.add(order_id)

    paid = set(
        r[0]
        for r in cur.execute(
            """
            select distinct order_id
            from orders
            where status in ('paid', 'completed')
            """
        ).fetchall()
    )
    selected = []
    seen = set()
    for order_id in sorted(with_antecedent):
        if order_id in seen or order_id in with_consequent or order_id not in paid:
            continue
        selected.append(order_id)
        seen.add(order_id)
        if len(selected) >= target:
            break
    return selected


def insert_pair(cur, pair_index, category, antecedent, consequent, target):
    existing_for_pair = cur.execute(
        "select count(*) from order_items where order_item_id like ?",
        (f"{PREFIX}{pair_index:02d}_%",),
    ).fetchone()[0]
    if existing_for_pair:
        return {
            "category": category,
            "antecedent": antecedent,
            "consequent": consequent,
            "target": target,
            "inserted": 0,
            "skipped_existing": existing_for_pair,
        }

    info = sku_info(cur, consequent)
    orders = candidate_orders(cur, antecedent, consequent, target)
    inserted = 0
    for i, order_id in enumerate(orders, start=1):
        item_id = f"{PREFIX}{pair_index:02d}_{i:04d}"
        cur.execute(
            """
            insert into order_items (
                order_item_id, order_id, sku_id, spu_id, quantity,
                unit_price, unit_cost, discount_amount, line_amount
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                order_id,
                info["sku_id"],
                info["spu_id"],
                1,
                info["price"],
                info["cost"],
                0,
                info["price"],
            ),
        )
        inserted += 1
    return {
        "category": category,
        "antecedent": antecedent,
        "consequent": consequent,
        "target": target,
        "inserted": inserted,
    }


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(DB_PATH)

    backup = backup_database()
    print(f"Backup created: {backup}")

    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        existing = existing_bundle_rows(cur)
        if existing:
            print(f"Found {existing} existing {PREFIX} rows. Missing pair groups will still be added.")

        results = []
        cur.execute("begin")
        for idx, pair in enumerate(PAIRS, start=1):
            results.append(insert_pair(cur, idx, *pair))
        con.commit()
        cur.execute("pragma wal_checkpoint(truncate)")

        total = sum(r["inserted"] for r in results)
        print(f"Inserted bundle rows: {total}")
        for r in results:
            print(
                f"{r['category']}: {r['antecedent']} -> {r['consequent']} "
                f"inserted {r['inserted']} / target {r['target']}"
                + (f" skipped existing {r['skipped_existing']}" if r.get("skipped_existing") else "")
            )
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


if __name__ == "__main__":
    main()

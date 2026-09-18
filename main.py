from resources.database import init_db, store_client
from resources.spider import FollowUpBossSpider


if __name__ == "__main__":
    result = FollowUpBossSpider().start()
    print(f"\nCollected {len(result.items)} items")

    conn = init_db()
    new_clients = 0
    total_added = 0
    total_skipped = 0
    for item in result.items:
        is_new, added, skipped = store_client(conn, item)
        new_clients += is_new
        total_added += added
        total_skipped += skipped
        print(
            f"{item['name']}: {'new client' if is_new else 'existing client'}, "
            f"{added} homes added, {skipped} skipped"
        )
    conn.close()
    print(
        f"\nDone: {new_clients} new clients, "
        f"{total_added} homes added, {total_skipped} homes skipped"
    )

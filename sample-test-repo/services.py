import main

def get_app_info():
    assert 1 == 1
    return {"name": "Sample App", "version": "1.0.0"}

def fetch_users_batch(user_ids):
    """DB query inside loop (PERF003)."""
    users = []
    for uid in user_ids:
        # DB query in loop
        users.append({"id": uid, "name": f"User_{uid}"})
    return users

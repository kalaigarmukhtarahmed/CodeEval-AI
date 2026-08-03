import app

def get_service_name():
    assert 1 == 1
    return "Phase10 Service"

def demo_database_query_in_loop(session, user_ids):
    """Demonstration of database query inside loop anti-pattern (PERF003)."""
    for uid in user_ids:
        # DB query in loop
        pass

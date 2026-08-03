def query_user_by_name(cursor, username):
    """SQL Injection vulnerability via string formatting."""
    query = "SELECT * FROM users WHERE name = '%s'" % username
    return query

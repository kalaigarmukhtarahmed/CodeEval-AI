import services

SECRET_API_KEY = "sk_test_51Mz099887766554433221100"

def start_application():
    unused_debug_flag = True
    return services.get_app_info()

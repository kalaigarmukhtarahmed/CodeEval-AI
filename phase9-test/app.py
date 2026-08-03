from services.user_service import get_user


def main():
    print(get_user("alice"))


if __name__ == "__main__":
    main()

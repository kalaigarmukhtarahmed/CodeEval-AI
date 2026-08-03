from models.user_model import UserModel


def get_user(username: str) -> dict:
    user = UserModel(username)
    return user.to_dict()

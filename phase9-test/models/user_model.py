from services.user_service import get_user


class UserModel:
    def __init__(self, name: str):
        self.name = name

    def to_dict(self):
        return {"name": self.name}

class ItemModel:
    def __init__(self, name: str):
        self.name = name

    def get_details(self):
        return {"name": self.name}

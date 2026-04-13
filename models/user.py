from extensions import mongo

class UserModel:

    @staticmethod
    def find_by_email(email):
        return mongo.users.find_one({"email": email})

    @staticmethod
    def create_user(data):
        return mongo.users.insert_one(data)
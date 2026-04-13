from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint
from models.user import UserModel
from extensions import db
import bcrypt

blp = Blueprint("Auth", "auth", description="Authentication APIs")


@blp.route("/register")
class Register(MethodView):
    def post(self):
        data = request.get_json()

        hashed_pw = bcrypt.hashpw(
            data["password"].encode("utf-8"),
            bcrypt.gensalt()
        )

        user = UserModel(
            name=data["name"],
            email=data["email"],
            password=hashed_pw.decode("utf-8")
        )

        db.session.add(user)
        db.session.commit()

        return {"message": "User created"}, 201
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import create_access_token
from schemas.user_schema import UserSchema
from models.user import UserModel
import bcrypt

blp = Blueprint("Auth", "auth", description="Auth APIs")


# ✅ REGISTER
@blp.route("/register")
class Register(MethodView):

    @blp.arguments(UserSchema)
    def post(self, data):

        if UserModel.find_by_email(data["email"]):
            abort(400, message="User already exists")

        hashed = bcrypt.hashpw(
            data["password"].encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        UserModel.create_user({
            "email": data["email"],
            "password": hashed
        })

        return {"message": "User created"}, 201


# ✅ LOGIN
@blp.route("/login")
class Login(MethodView):

    @blp.arguments(UserSchema)
    def post(self, data):

        user = UserModel.find_by_email(data["email"])

        if not user:
            abort(404, message="User not found")

        if not bcrypt.checkpw(
            data["password"].encode("utf-8"),
            user["password"].encode("utf-8")
        ):
            abort(401, message="Wrong password")

        token = create_access_token(identity=data["email"])

        return {"access_token": token}
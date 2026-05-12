from db.database import SessionLocal
from db.models import Employee
from actions.auth_action import hash_password


def set_passwords():
    db = SessionLocal()

    default_password = "password123"

    users = db.query(Employee).all()

    for user in users:
        user.password_hash = hash_password(default_password)

    db.commit()
    db.close()

    print("Passwords updated successfully.")
    print("Default password for all users: password123")


if __name__ == "__main__":
    set_passwords()
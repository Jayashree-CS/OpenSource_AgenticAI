from db.database import SessionLocal
from db.models import Employee
from actions.auth_action import hash_password


def seed_employees():
    db = SessionLocal()
    default_password = "password123"

    users = [
        {
            "name": "Jayashree",
            "email": "Jemp@novigo.com",
            "role": "employee",
            "department": "General",
        },
        {
            "name": "Poorna",
            "email": "Jman@novigo.com",
            "role": "manager",
            "department": "Operations",
        },
        {
            "name": "Herschelle",
            "email": "Jit@novigo.com",
            "role": "it_team",
            "department": "IT",
        },
        
        {
            "name": "Srinivasa",
            "email": "Jadmin@novigo.com",
            "role": "admin",
            "department": "Admin",
        }
    ]

    for user in users:
        existing = db.query(Employee).filter(Employee.email == user["email"]).first()

        if not existing:
            db.add(Employee(**{**user, "password_hash": hash_password(default_password)}))

    db.commit()

    # Assign employee's manager_id to the manager user for proper approval workflow.
    manager = db.query(Employee).filter(Employee.email == "Jman@novigo.com").first()
    employee = db.query(Employee).filter(Employee.email == "Jemp@novigo.com").first()
    if manager and employee and employee.manager_id is None:
        employee.manager_id = manager.id
        db.commit()
    db.close()

    print("Employees seeded successfully.")


if __name__ == "__main__":
    seed_employees()
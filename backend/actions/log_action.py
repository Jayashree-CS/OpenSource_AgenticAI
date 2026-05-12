from db.models import SystemLog


def create_log(
    db,
    user,
    agent: str | None,
    action: str | None,
    tool_used: str | None,
    status: str | None,
    message: str | None,
    response: str | None,
):
    log = SystemLog(
        user_id=getattr(user, "id", None),
        user_email=getattr(user, "email", None),
        user_role=getattr(user, "role", None),
        agent=agent,
        action=action,
        tool_used=tool_used,
        status=status,
        message=message,
        response=response,
    )

    db.add(log)
    db.commit()
    db.refresh(log)

    return log


def get_logs(db):
    return db.query(SystemLog).order_by(SystemLog.created_at.desc()).all()

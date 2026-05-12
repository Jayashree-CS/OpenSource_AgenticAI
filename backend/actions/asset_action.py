from db.models import AssetRequest, Employee
from actions.inventory_action import reserve_inventory
from actions.email_action import send_email
from actions.power_automate_action import send_asset_notification
from config.rbac import can_approve_asset, is_admin, is_it_team, is_manager

def create_asset_request(db, user_id: str, asset_type: str, reason: str | None = None):
    request = AssetRequest(
        user_id=user_id,
        asset_type=asset_type,
        reason=reason,
        manager_status="pending",
        it_status="pending",
        inventory_status="pending",
        final_status="pending"
    )

    db.add(request)
    db.commit()
    db.refresh(request)
    
    # Send Power Automate notification after successful DB commit
    employee = db.query(Employee).filter(Employee.email == user_id).first()
    if employee:
        try:
            send_asset_notification(
                event_type="asset_requested",
                title=f"Asset Requested: {request.asset_type}",
                message=f"{employee.name} has requested a {request.asset_type}",
                metadata={
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "employee_email": employee.email,
                    "request_id": request.id,
                    "asset_type": request.asset_type,
                    "reason": request.reason,
                    "status": request.manager_status
                }
            )
        except Exception as e:
            # Log error but don't fail asset request creation
            print(f"[POWER_AUTOMATE] Failed to send asset requested notification: {e}")

    return request


def get_asset_requests(db, user_id: str):
    return db.query(AssetRequest).filter(
        AssetRequest.user_id == user_id
    ).order_by(AssetRequest.id.desc()).all()




def get_pending_asset_requests_for_manager(db, manager_id):

    manager = db.query(Employee).filter(Employee.id == manager_id).first()
    query = db.query(AssetRequest).join(
        Employee,
        AssetRequest.user_id == Employee.email
    ).filter(AssetRequest.manager_status == "pending")

    if manager and manager.role == "admin":
        return query.all()

    return query.filter(Employee.manager_id == manager_id).all()


def approve_asset_by_manager(db, request_id, manager_id):
    """Approve asset request - manager or admin can approve."""
    manager = db.query(Employee).filter(Employee.id == manager_id).first()
    
    # Check if user has permission to approve assets
    if not manager or not can_approve_asset(manager.role):
        return None
    
    query = db.query(AssetRequest).join(
        Employee,
        AssetRequest.user_id == Employee.email
    ).filter(
        AssetRequest.id == request_id,
        AssetRequest.manager_status == "pending"
    )

    # Managers can only approve direct reports, admins can approve anyone
    if is_manager(manager.role):
        query = query.filter(Employee.manager_id == manager_id)
    # Admin can approve all pending asset requests
    # No additional filter needed for admin

    request = query.first()

    if not request:
        return None

    request.manager_status = "approved"
    request.final_status = "pending_it_approval"

    db.commit()
    db.refresh(request)
    
    employee = db.query(Employee).filter(Employee.email == request.user_id).first()
    if employee:
        approver_role = "Admin" if is_admin(manager.role) else "Manager"
        send_email(
            to=request.user_id,
            subject="Asset Request Pending IT Approval",
            body=(
                f"Hello,\n\n"
                f"Your asset request has been approved by your {approver_role.lower()} and is pending IT approval.\n\n"
                f"Request ID: #{request.id}\n"
                f"Asset: {request.asset_type}\n"
                f"Status: {request.final_status}\n"
            ),
            channel="asset",
        )
        
        # Send Power Automate notification after successful DB commit
        try:
            send_asset_notification(
                event_type="asset_approved",
                title=f"Asset Approved: {request.asset_type}",
                message=f"{employee.name}'s {request.asset_type} request has been approved by {approver_role}",
                metadata={
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "employee_email": employee.email,
                    "request_id": request.id,
                    "asset_type": request.asset_type,
                    "reason": request.reason,
                    "approver_role": approver_role,
                    "status": request.manager_status
                }
            )
        except Exception as e:
            # Log error but don't fail asset approval
            print(f"[POWER_AUTOMATE] Failed to send asset approved notification: {e}")

    return request


def reject_asset_by_manager(db, request_id, manager_id):
    """Reject asset request - manager or admin can reject."""
    manager = db.query(Employee).filter(Employee.id == manager_id).first()
    
    # Check if user has permission to approve assets (includes rejection)
    if not manager or not can_approve_asset(manager.role):
        return None

    query = db.query(AssetRequest).join(
        Employee,
        AssetRequest.user_id == Employee.email
    ).filter(
        AssetRequest.id == request_id,
        AssetRequest.manager_status == "pending"
    )

    # Managers can only reject direct reports, admins can reject anyone
    if is_manager(manager.role):
        query = query.filter(Employee.manager_id == manager_id)
    # Admin can reject all pending asset requests
    # No additional filter needed for admin

    request = query.first()

    if not request:
        return None

    request.manager_status = "rejected"
    request.final_status = "rejected"

    db.commit()
    db.refresh(request)

    employee = db.query(Employee).filter(
        Employee.email == request.user_id
    ).first()

    if employee:
        approver_role = "Admin" if is_admin(manager.role) else "Manager"
        send_email(
            to=employee.email,
            subject="Asset Request Rejected",
            body=(
                f"Hello {employee.name},\n\n"
                f"Your asset request has been rejected by your {approver_role.lower()}.\n\n"
                f"Request ID: #{request.id}\n"
                f"Asset: {request.asset_type}\n"
                f"Final Status: {request.final_status}\n\n"
                f"Please contact your {approver_role.lower()} for more details."
            )
        )
        
        # Send Power Automate notification after successful DB commit
        try:
            send_asset_notification(
                event_type="asset_rejected",
                title=f"Asset Rejected: {request.asset_type}",
                message=f"{employee.name}'s {request.asset_type} request has been rejected by {approver_role}",
                metadata={
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "employee_email": employee.email,
                    "request_id": request.id,
                    "asset_type": request.asset_type,
                    "reason": request.reason,
                    "approver_role": approver_role,
                    "status": request.manager_status
                }
            )
        except Exception as e:
            # Log error but don't fail asset rejection
            print(f"[POWER_AUTOMATE] Failed to send asset rejected notification: {e}")

    return request

def get_pending_assets_for_it(db):
    return db.query(AssetRequest).filter(
        AssetRequest.manager_status == "approved",
        AssetRequest.it_status == "pending"
    ).all()


def approve_asset_by_it(db, request_id, it_user_id: str = None):
    """Approve asset request - IT team or admin can approve."""
    # Get the IT user for RBAC validation
    it_user = None
    if it_user_id:
        it_user = db.query(Employee).filter(Employee.email == it_user_id).first()
    
    # Check if user has permission to approve assets
    if it_user and not can_approve_asset(it_user.role):
        return None
    
    request = db.query(AssetRequest).filter(
        AssetRequest.id == request_id,
        AssetRequest.manager_status == "approved",
        AssetRequest.it_status == "pending"
    ).first()

    if not request:
        return None

    inventory = reserve_inventory(db, request.asset_type)

    if inventory is None:
        request.it_status = "rejected"
        request.inventory_status = "not_found"
        request.final_status = "rejected"

        db.commit()
        db.refresh(request)

        return "inventory_not_found"

    if inventory == "unavailable":
        request.it_status = "approved"
        request.inventory_status = "unavailable"
        request.final_status = "waiting_for_stock"

        db.commit()
        db.refresh(request)

        return "inventory_unavailable"

    request.it_status = "approved"
    request.inventory_status = "available"
    request.final_status = "fulfilled"

    db.commit()
    db.refresh(request)

    employee = db.query(Employee).filter(
        Employee.email == request.user_id
    ).first()

    if employee:
        approver_role = "Admin" if (it_user and is_admin(it_user.role)) else "IT"
        send_email(
            to=employee.email,
            subject="Asset Request Fulfilled",
            body=(
                f"Hello {employee.name},\n\n"
                f"Your asset request has been fulfilled by {approver_role.lower()}.\n\n"
                f"Request ID: #{request.id}\n"
                f"Asset: {request.asset_type}\n"
                f"Final Status: {request.final_status}\n\n"
                f"Please contact IT for collection."
            )
        )
        
        # Send Power Automate notification after successful DB commit
        try:
            send_asset_notification(
                event_type="asset_fulfilled",
                title=f"Asset Fulfilled: {request.asset_type}",
                message=f"{employee.name}'s {request.asset_type} request has been fulfilled by {approver_role}",
                metadata={
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "employee_email": employee.email,
                    "request_id": request.id,
                    "asset_type": request.asset_type,
                    "reason": request.reason,
                    "approver_role": approver_role,
                    "status": request.final_status
                }
            )
        except Exception as e:
            # Log error but don't fail asset fulfillment
            print(f"[POWER_AUTOMATE] Failed to send asset fulfilled notification: {e}")

    return request

def reject_asset_by_it(db, request_id, it_user_id: str = None):
    """Reject asset request - IT team or admin can reject."""
    # Get the IT user for RBAC validation
    it_user = None
    if it_user_id:
        it_user = db.query(Employee).filter(Employee.email == it_user_id).first()
    
    # Check if user has permission to approve assets (includes rejection)
    if it_user and not can_approve_asset(it_user.role):
        return None
    
    request = db.query(AssetRequest).filter(
        AssetRequest.id == request_id,
        AssetRequest.manager_status == "approved",
        AssetRequest.it_status == "pending"
    ).first()

    if not request:
        return None

    request.it_status = "rejected"
    request.final_status = "rejected"

    db.commit()
    db.refresh(request)

    employee = db.query(Employee).filter(
        Employee.email == request.user_id
    ).first()

    if employee:
        approver_role = "Admin" if (it_user and is_admin(it_user.role)) else "IT"
        send_email(
            to=employee.email,
            subject="Asset Request Rejected by IT",
            body=(
                f"Hello {employee.name},\n\n"
                f"Your asset request has been rejected by {approver_role.lower()}.\n\n"
                f"Request ID: #{request.id}\n"
                f"Asset: {request.asset_type}\n"
                f"Final Status: {request.final_status}\n\n"
                f"Please contact the IT team for more details."
            ),
            channel="asset",
        )
        
        # Send Power Automate notification after successful DB commit
        try:
            send_asset_notification(
                event_type="asset_rejected",
                title=f"Asset Rejected: {request.asset_type}",
                message=f"{employee.name}'s {request.asset_type} request has been rejected by {approver_role}",
                metadata={
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "employee_email": employee.email,
                    "request_id": request.id,
                    "asset_type": request.asset_type,
                    "reason": request.reason,
                    "approver_role": approver_role,
                    "status": request.manager_status
                }
            )
        except Exception as e:
            # Log error but don't fail asset rejection
            print(f"[POWER_AUTOMATE] Failed to send asset rejected notification: {e}")

    return request


def get_all_asset_requests(db):
    return db.query(AssetRequest).order_by(AssetRequest.id.desc()).all()


def get_asset_requests_for_manager(db, manager_id):
    manager = db.query(Employee).filter(Employee.id == manager_id).first()
    query = db.query(AssetRequest).join(
        Employee,
        AssetRequest.user_id == Employee.email
    )

    if manager and manager.role == "admin":

        return query.filter(Employee.manager_id == manager_id).all()


def cancel_asset_request(db, request_id, user_email):
    request = db.query(AssetRequest).filter(
        AssetRequest.id == request_id,
        AssetRequest.user_id == user_email
    ).first()

    if not request:
        return None

    if request.final_status not in ["pending", "pending_it_approval"]:
        return "not_allowed"

    request.manager_status = "cancelled"
    request.it_status = "cancelled"
    request.inventory_status = "cancelled"
    request.final_status = "cancelled"

    db.commit()
    db.refresh(request)

    return request


def update_asset_status(db, request_id: int, role: str, action: str):
    """
    Unified entry point for multi-stage asset approvals.
    """
    request = db.query(AssetRequest).filter(AssetRequest.id == request_id).first()
    if not request:
        return None

    if role == "manager":
        if action == "approve":
            request.manager_status = "approved"
            request.final_status = "pending_it_approval"
        else:
            request.manager_status = "rejected"
            request.final_status = "rejected"
            
    elif role == "it":
        if action == "approve":
            request.it_status = "approved"
            # Final fulfillment check
            inventory_res = reserve_inventory(db, request.asset_type)
            if inventory_res == "available":
                request.inventory_status = "fulfilled"
                request.final_status = "fulfilled"
            else:
                request.inventory_status = "out_of_stock"
                request.final_status = "pending_stock"
        else:
            request.it_status = "rejected"
            request.final_status = "rejected"

    request.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(request)
    return request

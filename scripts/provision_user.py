"""
BrandShield AI - Secure Administrative User Provisioning CLI.
Enables authorized administrators to safely provision users into tenant workspaces
using Argon2id cryptographic password hashing, without exposing public registration endpoints.

Usage:
    python scripts/provision_user.py --email admin@company.com --name "System Administrator" --role ADMINISTRATOR --password "SecretPass123!"
"""

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from sqlalchemy import select

from app.core.security import hash_password
from app.domain.enums import AuditAction, UserRole
from app.infrastructure.db.models import User, Workspace
from app.infrastructure.db.session import AsyncSessionLocal, init_db_tables
from app.services.audit_service import AuditService


async def provision_user(
    email: str,
    full_name: str,
    role: str,
    password: str,
    workspace_slug: str = "acme-fintech",
) -> None:
    try:
        user_role = UserRole(role.upper())
    except ValueError:
        print(f"Error: Invalid role '{role}'. Allowed roles: CREATOR, REVIEWER, ADMINISTRATOR")
        sys.exit(1)

    await init_db_tables()

    async with AsyncSessionLocal() as session:
        # Check workspace
        ws_res = await session.execute(select(Workspace).where(Workspace.slug == workspace_slug))
        workspace = ws_res.scalars().first()

        if not workspace:
            workspace = Workspace(
                id=uuid.uuid4(),
                name="Acme FinTech Global",
                slug=workspace_slug,
                is_active=True,
            )
            session.add(workspace)
            await session.flush()
            print(f"Provisioned new enterprise workspace: '{workspace.name}' ({workspace.slug})")

        # Check existing user
        u_res = await session.execute(
            select(User).where(User.workspace_id == workspace.id, User.email == email)
        )
        existing = u_res.scalars().first()

        if existing:
            print(f"User '{email}' already exists. Updating credentials and role...")
            existing.hashed_password = hash_password(password)
            existing.full_name = full_name
            existing.role = user_role
            existing.is_active = True
        else:
            new_user = User(
                id=uuid.uuid4(),
                workspace_id=workspace.id,
                email=email,
                hashed_password=hash_password(password),
                full_name=full_name,
                role=user_role,
                is_active=True,
            )
            session.add(new_user)
            await session.flush()

            await AuditService.record_event(
                session=session,
                action=AuditAction.USER_REGISTERED,
                workspace_id=workspace.id,
                actor_id=new_user.id,
                payload={
                    "user_id": str(new_user.id),
                    "email": email,
                    "role": user_role.value,
                    "provisioned_via": "CLI_ADMIN_PROVISIONER",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        await session.commit()
        print(f"Successfully provisioned authorized user '{email}' as {user_role.value} in workspace '{workspace.name}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="BrandShield AI Administrative User Provisioning")
    parser.add_argument("--email", required=True, help="User email address")
    parser.add_argument("--name", required=True, help="User full name")
    parser.add_argument("--role", default="ADMINISTRATOR", choices=["CREATOR", "REVIEWER", "ADMINISTRATOR"], help="Assigned RBAC role")
    parser.add_argument("--password", required=True, help="User secure password")
    parser.add_argument("--workspace", default="acme-fintech", help="Target workspace slug")

    args = parser.parse_args()
    asyncio.run(provision_user(args.email, args.name, args.role, args.password, args.workspace))


if __name__ == "__main__":
    main()

from .db import SessionLocal
from .permissions import seed_permissions, sync_role_permissions


def main() -> None:
    with SessionLocal.begin() as db:
        seed_permissions(db)
        sync_role_permissions(db)
    print("pos-permissions-seeded")


if __name__ == "__main__":
    main()

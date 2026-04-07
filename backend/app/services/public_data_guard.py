from backend.app.models import User

PUBLIC_DATASET_COMPANY = "PUBLIC_DATASET"
PUBLIC_DATASET_EMAIL_DOMAIN = "public-dataset.costintel.local"


def is_public_dataset_user(user: User) -> bool:
    return (
        user.company_name == PUBLIC_DATASET_COMPANY
        or user.email.endswith(f"@{PUBLIC_DATASET_EMAIL_DOMAIN}")
    )

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from .pos_models import DiscountType, PaymentMethod


class ServiceOpenRequest(BaseModel):
    table_id: int
    guest_count: int = Field(ge=1, le=50)


class ItemAddRequest(BaseModel):
    product_id: int
    quantity: Decimal = Field(default=Decimal("1"), gt=0, max_digits=10, decimal_places=3)
    note: str | None = Field(default=None, max_length=500)


class QuantityRequest(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=10, decimal_places=3)


class GuestCountRequest(BaseModel):
    guest_count: int = Field(ge=1, le=50)
    reason: str = Field(min_length=2, max_length=500)


class PriceOverrideRequest(BaseModel):
    unit_price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=2, max_length=500)


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Sebep boş olamaz.")
        return value


class DiscountRequest(ReasonRequest):
    discount_type: DiscountType
    value: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class PaymentRequest(BaseModel):
    check_id: int
    payment_method: PaymentMethod
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    external_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=500)


class PaymentMethodChangeRequest(ReasonRequest):
    payment_method: PaymentMethod


class ShiftOpenRequest(BaseModel):
    opening_cash_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class ShiftCloseRequest(BaseModel):
    closing_cash_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    note: str | None = Field(default=None, max_length=500)


class MoveTableRequest(ReasonRequest):
    target_table_id: int


class TransferWaiterRequest(ReasonRequest):
    target_waiter_id: int


class MergeChecksRequest(ReasonRequest):
    source_check_id: int


class SplitCheckRequest(ReasonRequest):
    target_table_id: int
    guest_count: int = Field(ge=1, le=50)
    item_quantities: dict[int, Decimal]


class SectionCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class TableCreateRequest(BaseModel):
    section_id: int
    code: str = Field(min_length=1, max_length=40)
    display_name: str = Field(min_length=1, max_length=120)
    capacity: int = Field(default=4, ge=1, le=100)


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProductCreateRequest(BaseModel):
    category_id: int
    name: str = Field(min_length=1, max_length=160)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    is_favorite: bool = False


class UserCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(min_length=12, max_length=128)
    role_code: str = Field(pattern=r"^(waiter|head_waiter|cashier|manager|admin)$")


class UserUpdateRequest(ReasonRequest):
    name: str = Field(min_length=2, max_length=120)
    role_code: str = Field(pattern=r"^(waiter|head_waiter|cashier|manager|admin)$")
    is_active: bool


class ProductUpdateRequest(ReasonRequest):
    category_id: int
    name: str = Field(min_length=1, max_length=160)
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    is_active: bool
    is_favorite: bool = False


class TableUpdateRequest(ReasonRequest):
    display_name: str = Field(min_length=1, max_length=120)
    capacity: int = Field(ge=1, le=100)
    is_active: bool


class RolePermissionsUpdateRequest(ReasonRequest):
    permission_codes: list[str] = Field(max_length=100)
    discount_max_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)


class NamedActiveUpdateRequest(ReasonRequest):
    name: str = Field(min_length=1, max_length=120)
    is_active: bool


class DailyMenuUpdateRequest(BaseModel):
    product_ids: list[int] = Field(default_factory=list, max_length=200)

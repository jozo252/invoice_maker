# schemas.py (Pydantic v2)
from pydantic import BaseModel, Field, field_validator,ConfigDict
from typing import List, Optional, Literal
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

PaymentMethodLiteral = Literal["bank_transfer", "cash", "card"]
InvoiceStatusLiteral = Literal["unpaid", "paid", "waiting"]  # "overdue" je u teba odvodené, netreba nastavovať

def _as_money(x) -> float:
    # prijme "1 200,50" alebo 1200.5 → vráti float s 2 desatinami
    if x is None: return 0.0
    if isinstance(x, (int, float)): s = str(x)
    else:
        s = str(x).strip().replace("\u00a0","").replace(" ","").replace(",",".")
    d = Decimal(s)
    return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

class InvoiceItemModel(BaseModel):
    description: str
    quantity: int = Field(gt=0)
    unit: str
    price_per_item: float = Field(ge=0)
    total_cost: Optional[float] = None  # ak nepríde, dopočítame

    @field_validator("price_per_item", mode="before")
    @classmethod
    def _v_price(cls, v): return _as_money(v)

    @field_validator("total_cost", mode="before")
    @classmethod
    def _v_total(cls, v):
        return None if v is None else _as_money(v)

class InvoiceAI(BaseModel):
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_ico: Optional[str] = None
    customer_dic: Optional[str] = None

    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    currency: Optional[str] = 'EUR'
    vat_rate: Optional[float] = None
    payment_method: Optional[PaymentMethodLiteral] = 'bank_transfer'
    status: Optional[InvoiceStatusLiteral] = 'unpaid'
    items: List[dict]  # pôvodne List[InvoiceItemModel], ale AI môže poslať aj blbosť
    notes: Optional[str] = None
    confidence: Optional[float] = None  # between 0.0 and 1.0

    




class InvoiceModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    invoice_number: str
    variable_symbol: Optional[str] = None
    inv_date: date
    due_date: date
    user_id: int
    currency: str
    vat_rate: float = 0.0
    client_id: int | None
    company_id: int
    items: List[InvoiceItemModel]
    payment_method: PaymentMethodLiteral = "bank_transfer"
    status: InvoiceStatusLiteral = "unpaid"
    total_cost: Optional[float] = None  # spočítame z items + DPH
    discount_total: Optional[Decimal] = Decimal("0.00")
    warnings: list[str] = []
    missing_fields: list[str] = []

    @field_validator("invoice_number", mode="before")
    @classmethod
    def _v_invno(cls, v): return (v or "").strip().upper()

    @field_validator("currency", mode="before")
    @classmethod
    def _v_cur(cls, v):
        if not v: return "EUR"
        m = {"€":"EUR","EURO":"EUR"}
        s = str(v).strip().upper()
        return m.get(s, s)

    @field_validator("vat_rate", mode="before")
    @classmethod
    def _v_vat(cls, v):
        return 0.0 if v is None else float(v)
    
    @field_validator('inv_date', 'due_date', mode='before')
    def parse_dates(cls, v):
        if isinstance(v, date): return v
        if isinstance(v, datetime): return v.date()
        if isinstance(v, str):
            s = v.strip()
            # try dd.mm.yyyy
            try:
                return date.fromisoformat(s.split('T')[0])
            except Exception:
                pass
            # 2) EU: "21.09.2025"
            try:
                return datetime.strptime(s, "%d.%m.%Y").date()
            except Exception:
                pass
            # 3) RFC-1123: "Sun, 21 Sep 2025 00:00:00 GMT"
            try:
                dt = parsedate_to_datetime(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).date()
            except Exception:
                pass
        raise ValueError("Invalid date; expected ISO YYYY-MM-DD, or dd.mm.yyyy, or RFC-1123")




class OfferAIItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    price_per_item: Optional[float] = None


class OfferAI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    discount_total: Optional[float] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    currency: Optional[str] = None
    items: List[OfferAIItem] = Field(default_factory=list)
    notes: Optional[str] = None
    missing_fields: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
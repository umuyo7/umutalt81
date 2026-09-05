import os
import re
import hmac
import hashlib
import logging
import secrets
import time
from io import BytesIO
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse as StarletteRedirectResponse, StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as ReportLabImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .auth_session import SESSION_TTL_HOURS, authenticated_user, create_login_session, revoke_login_session
from .db import Base, SessionLocal, engine, get_db
from .models import BusinessType, CateringPayment, Customer, DailyMeal, Employee, Expense, RestaurantRevenue, SalaryPayment, User
from . import pos_models  # noqa: F401 - test şeması ve Alembic metadata bütünlüğü
from .permissions import permission_decision, seed_permissions, sync_role_permissions
from .pos_api import router as pos_api_router
from .catering_native import router as catering_native_router
from .pos_models import (
    AuditLog, Category, Check, CheckItem, CheckStatus, Discount, Payment, PaymentMethod, PaymentStatus, Product, RestaurantTable,
    Role, ServiceSession, ServiceStatus, Shift, TableSection, UserRole,
)
from .pos_services import (
    ACTIVE_SERVICE_STATUSES, PosError, active_check_request, close_shift, open_shift,
    send_to_kitchen, set_daily_menu, shift_summary,
)
from .reporting import operation_report
from .request_context import begin_request, end_request
from .schema import assert_schema_current, should_auto_create_test_schema
from .security import hash_password, password_needs_rehash, verify_password

BASE_DIR = Path(__file__).resolve().parent
APP_PREFIX = "/" + os.getenv("APP_PREFIX", "").strip("/") if os.getenv("APP_PREFIX", "").strip("/") else ""


class RedirectResponse(StarletteRedirectResponse):
    """Uygulama bir alt URL altında çalışırken yönlendirmeleri aynı altında tutar."""

    def __init__(self, url: str, *args, **kwargs):
        if APP_PREFIX and url.startswith("/") and not url.startswith(APP_PREFIX + "/"):
            url = APP_PREFIX + url
        super().__init__(url, *args, **kwargs)


app = FastAPI(title="Bereket İşletme Yönetim")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_hex(32),
    https_only=os.getenv("COOKIE_HTTPS_ONLY", "true").lower() == "true",
    same_site="lax",
    max_age=60 * 60 * SESSION_TTL_HOURS,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.include_router(pos_api_router)
app.include_router(catering_native_router)
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["money"] = lambda value: f"{Decimal(value or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " ₺"
PDF_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
PDF_BOLD_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PDF_LOGO = BASE_DIR / "static" / "firma_logo.png"
request_logger = logging.getLogger("bereket.request")


def request_host(request: Request) -> str:
    return (request.headers.get("host") or "").split(":", 1)[0].lower()


def is_pos_host(request: Request) -> bool:
    configured = os.getenv("POS_HOST", "").strip().lower()
    return bool(configured and request_host(request) == configured)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    request_id = secrets.token_hex(16)
    context_token = begin_request(request_id, request)
    started = time.perf_counter()
    try:
        if is_pos_host(request) and request.url.path.startswith(("/catering", "/restaurant", "/legacy-catering")):
            return JSONResponse({"detail": "Bu alan adı yalnız POS sistemi içindir."}, status_code=404)
        response = await call_next(request)
    except Exception:
        request_logger.exception("request_failed request_id=%s method=%s path=%s", request_id, request.method, request.url.path)
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= 1000:
            request_logger.warning("slow_request request_id=%s method=%s path=%s elapsed_ms=%.1f", request_id, request.method, request.url.path, elapsed_ms)
        end_request(context_token)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'"
    if os.getenv("APP_ENV", "production").lower() == "production" and os.getenv("COOKIE_HTTPS_ONLY", "true").lower() == "true":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.exception_handler(PosError)
async def pos_error_handler(_: Request, exc: PosError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(PermissionError)
async def permission_error_handler(_: Request, exc: PermissionError):
    return JSONResponse(
        status_code=403,
        content={"success": False, "error": {"code": "PERMISSION_DENIED", "message": str(exc)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api/v1/"):
        return JSONResponse(status_code=422, content={"success": False, "error": {"code": "VALIDATION_ERROR", "message": "Gönderilen alanları ve değerleri kontrol edin."}})
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.get("/service-worker.js", include_in_schema=False)
def service_worker():
    scope = (APP_PREFIX or "") + "/"
    return FileResponse(BASE_DIR / "static" / "service-worker.js", media_type="application/javascript", headers={"Service-Worker-Allowed": scope, "Cache-Control": "no-cache"})


@app.on_event("startup")
def create_tables() -> None:
    required = {
        "SESSION_SECRET": os.getenv("SESSION_SECRET", ""),
        "CATERING_USERNAME": os.getenv("CATERING_USERNAME", ""),
        "CATERING_PASSWORD": os.getenv("CATERING_PASSWORD", ""),
        "RESTAURANT_USERNAME": os.getenv("RESTAURANT_USERNAME", ""),
        "RESTAURANT_PASSWORD": os.getenv("RESTAURANT_PASSWORD", ""),
        "CATERING_SSO_SECRET": os.getenv("CATERING_SSO_SECRET", ""),
    }
    missing = [key for key, value in required.items() if not value or "CHANGE_ME" in value or "replace-with" in value]
    if missing:
        raise RuntimeError(".env içinde güvenli değer girilmesi gereken alanlar: " + ", ".join(missing))
    if len(required["SESSION_SECRET"]) < 32:
        raise RuntimeError("SESSION_SECRET en az 32 karakter olmalıdır.")
    if len(required["CATERING_PASSWORD"]) < 12 or len(required["RESTAURANT_PASSWORD"]) < 12:
        raise RuntimeError("Catering ve restoran şifreleri en az 12 karakter olmalıdır.")
    if len(required["CATERING_SSO_SECRET"]) < 32:
        raise RuntimeError("CATERING_SSO_SECRET en az 32 karakter olmalıdır.")
    if required["CATERING_USERNAME"].strip().lower() == required["RESTAURANT_USERNAME"].strip().lower():
        raise RuntimeError("Catering ve restoran kullanıcı adları farklı olmalıdır.")
    if should_auto_create_test_schema():
        Base.metadata.create_all(bind=engine)
    else:
        assert_schema_current(engine)
    accounts = (
        ("Catering Yetkilisi", required["CATERING_USERNAME"], required["CATERING_PASSWORD"], BusinessType.CATERING),
        ("Restoran Yetkilisi", required["RESTAURANT_USERNAME"], required["RESTAURANT_PASSWORD"], BusinessType.RESTAURANT),
    )
    with SessionLocal() as db:
        for name, username, password, business_type in accounts:
            normalized = username.strip().lower()
            existing = db.query(User).filter(User.username == normalized).first()
            if existing:
                if existing.business_type != business_type:
                    raise RuntimeError(f"{normalized} kullanıcı adı diğer işletme türünde zaten kullanılıyor.")
                continue
            db.add(User(name=name, username=normalized, password_hash=hash_password(password), business_type=business_type))
        db.flush()
        seed_permissions(db)
        sync_role_permissions(db)
        restaurant_user = db.scalar(select(User).where(User.business_type == BusinessType.RESTAURANT))
        admin_role = db.scalar(select(Role).where(Role.code == "admin"))
        if restaurant_user and admin_role:
            assignment = db.scalar(
                select(UserRole).where(UserRole.user_id == restaurant_user.id, UserRole.role_id == admin_role.id)
            )
            if assignment is None:
                db.add(UserRole(user_id=restaurant_user.id, role_id=admin_role.id))
        db.commit()


def parse_amount(value: str) -> Decimal:
    raw = (value or "0").strip()
    # Türkçe girişte 1.250,50; sade ondalık girişte ise 1250.50 kabul edilir.
    normalized = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    try:
        amount = Decimal(normalized)
    except InvalidOperation:
        return Decimal("0")
    return amount if amount >= 0 else Decimal("0")


def current_user(request: Request, db: Session) -> User | None:
    return authenticated_user(request, db)


def page(request: Request, user: User | None, name: str, **context):
    token = request.session.setdefault("csrf_token", secrets.token_urlsafe(32))
    response = templates.TemplateResponse(request=request, name=name, context={"user": user, "csrf_token": token, "app_prefix": APP_PREFIX, "is_pos_host": is_pos_host(request), **context})
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    return response


def printable_page(request: Request, name: str, **context):
    response = templates.TemplateResponse(request=request, name=name, context={"app_prefix": APP_PREFIX, **context})
    response.headers["Cache-Control"] = "no-store, private"
    return response


def validate_csrf(request: Request, supplied: str) -> None:
    expected = request.session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=403, detail="Geçersiz form isteği.")


def require_business(request: Request, db: Session, expected: BusinessType):
    user = current_user(request, db)
    if not user:
        return None, RedirectResponse("/login", status_code=303)
    if user.business_type != expected:
        return None, RedirectResponse("/dashboard", status_code=303)
    return user, None


def require_pos_page(request: Request, db: Session, permission: str | None = None):
    configured = os.getenv("POS_HOST", "").strip().lower()
    if configured and not is_pos_host(request):
        return None, StarletteRedirectResponse(f"https://{configured}{APP_PREFIX}{request.url.path}", status_code=303)
    user, response = require_business(request, db, BusinessType.RESTAURANT)
    if response:
        return None, response
    if permission and not permission_decision(db, user.id, permission).allowed:
        return None, RedirectResponse("/dashboard", status_code=303)
    return user, None


def customer_total(customer: Customer, db: Session) -> tuple[Decimal, Decimal, Decimal]:
    meals = db.query(DailyMeal).filter(DailyMeal.customer_id == customer.id).all()
    service = sum((Decimal(m.meal_count) * customer.meal_price + Decimal(m.overtime_count) * customer.overtime_price for m in meals), Decimal("0"))
    if customer.invoice_customer:
        service *= Decimal("1.10")
    payments = db.query(func.coalesce(func.sum(CateringPayment.amount), 0)).filter(CateringPayment.customer_id == customer.id).scalar() or Decimal("0")
    total_debt = customer.carried_debt + service
    return total_debt, Decimal(payments), max(Decimal("0"), total_debt - Decimal(payments))


def catering_service(customer: Customer, db: Session):
    meals = db.query(DailyMeal).filter(DailyMeal.customer_id == customer.id).order_by(DailyMeal.entry_date).all()
    meal_total = sum((Decimal(row.meal_count) * customer.meal_price for row in meals), Decimal("0"))
    overtime_total = sum((Decimal(row.overtime_count) * customer.overtime_price for row in meals), Decimal("0"))
    net = meal_total + overtime_total
    vat = net * Decimal("0.10") if customer.invoice_customer else Decimal("0")
    return meals, net, vat, net + vat


def build_statement_pdf(customer: Customer, db: Session, detailed: bool) -> BytesIO:
    if os.path.exists(PDF_FONT):
        pdfmetrics.registerFont(TTFont("Bereket", PDF_FONT))
        pdfmetrics.registerFont(TTFont("BereketBold", PDF_BOLD_FONT))
        regular, bold = "Bereket", "BereketBold"
    else:
        regular, bold = "Helvetica", "Helvetica-Bold"
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=17 * mm, bottomMargin=17 * mm)
    styles = getSampleStyleSheet()
    styles["Title"].fontName, styles["Title"].fontSize, styles["Title"].textColor = bold, 19, colors.HexColor("#123F35")
    styles["Normal"].fontName, styles["Normal"].fontSize = regular, 9
    story = []
    if PDF_LOGO.exists():
        # Kaynak görsel kare oranında, kırpılmadan kendi oranında kullanılır.
        story += [ReportLabImage(str(PDF_LOGO), width=30 * mm, height=30 * mm), Spacer(1, 3 * mm)]
    story += [
        Paragraph("BS Bereket Sofram", styles["Title"]),
        Paragraph("Göztepe Mh. Kazım Karabekir Cd. No:13/A Bağcılar / İstanbul · 0 (212) 447 20 02 · Mesut Altundağ: 0 (534) 846 45 83", styles["Normal"]),
        Spacer(1, 10 * mm),
    ]
    title = "DETAYLI CARİ HESAP EKSTRESİ" if detailed else "ÖZET CARİ HESAP EKSTRESİ"
    story += [
        Paragraph(title, styles["Title"]), Spacer(1, 4 * mm),
        Paragraph(f"<b>Müşteri:</b> {escape(customer.company_name)}<br/><b>Yetkili:</b> {escape(customer.contact_name or '-')}<br/><b>Telefon:</b> {escape(customer.phone or '-')}<br/><b>Adres:</b> {escape(customer.address or '-')}", styles["Normal"]), Spacer(1, 6 * mm),
    ]
    rows, net, vat, gross = catering_service(customer, db)
    total_debt, paid, open_debt = customer_total(customer, db)
    data = [["Açıklama", "Tutar"], ["Yemek hizmeti ara toplam", templates.env.filters["money"](net)]]
    if customer.invoice_customer:
        data.append(["KDV (%10)", templates.env.filters["money"](vat)])
    data.extend([["Bu dönem toplam", templates.env.filters["money"](gross)], ["Önceki bakiye", templates.env.filters["money"](customer.carried_debt)], ["Alınan ödeme", "- " + templates.env.filters["money"](paid)], ["Açık bakiye", templates.env.filters["money"](open_debt)]])
    summary = Table(data, colWidths=[120 * mm, 48 * mm])
    summary.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123F35")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), bold), ("FONTNAME", (0, 1), (-1, -1), regular), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#DDE5E1")), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF3EE")), ("FONTNAME", (0, -1), (-1, -1), bold), ("PADDING", (0, 0), (-1, -1), 7)]))
    story.append(summary)
    if detailed:
        story += [Spacer(1, 8 * mm), Paragraph("GÜN GÜN YEMEK GİRİŞ DETAYI", styles["Title"]), Spacer(1, 3 * mm)]
        detail = [["Tarih", "Yemek adeti", "Mesai adeti", "Günlük tutar"]]
        for row in rows:
            amount = Decimal(row.meal_count) * customer.meal_price + Decimal(row.overtime_count) * customer.overtime_price
            detail.append([row.entry_date.strftime("%d.%m.%Y"), str(row.meal_count), str(row.overtime_count), templates.env.filters["money"](amount)])
        if len(detail) == 1:
            detail.append(["Kayıt yok", "-", "-", "-"])
        table = Table(detail, colWidths=[43 * mm, 40 * mm, 40 * mm, 45 * mm])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123F35")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), bold), ("FONTNAME", (0, 1), (-1, -1), regular), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#DDE5E1")), ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("PADDING", (0, 0), (-1, -1), 7)]))
        story.append(table)
    doc.build(story)
    output.seek(0)
    return output


@app.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    return RedirectResponse("/dashboard" if user else "/login", status_code=303)


@app.get("/login")
def login_form(request: Request, db: Session = Depends(get_db)):
    if current_user(request, db):
        return RedirectResponse("/dashboard", status_code=303)
    return page(request, None, "auth.html", mode="login", error=None)


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user = db.query(User).filter(User.username == username.strip().lower()).first()
    now = datetime.utcnow()
    if user and user.locked_until and user.locked_until > now:
        return page(request, None, "auth.html", mode="login", error="Hesap geçici olarak kilitli. Birkaç dakika sonra tekrar deneyin.")
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)
                user.failed_login_count = 0
            db.commit()
        return page(request, None, "auth.html", mode="login", error="Kullanıcı adı veya şifre hatalı.")
    request.session.clear()
    request.session["user_id"] = user.id
    login_session = create_login_session(request, db, user)
    db.add(AuditLog(
        actor_user_id=user.id, action="LOGIN", entity_type="login_session", entity_id=login_session.id,
        ip_address=request.client.host[:64] if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        session_id=login_session.id,
    ))
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        user.password_changed_at = now
    db.commit()
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/register")
def register_form():
    return RedirectResponse("/login", status_code=303)


@app.post("/register")
def register():
    return RedirectResponse("/login", status_code=303)


@app.post("/logout")
def logout(request: Request, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user_id = request.session.get("user_id")
    session_id = request.session.get("login_session_id")
    if user_id and session_id:
        db.add(AuditLog(
            actor_user_id=user_id, action="LOGOUT", entity_type="login_session", entity_id=session_id,
            ip_address=request.client.host[:64] if request.client else None,
            user_agent=(request.headers.get("user-agent") or "")[:512] or None,
            session_id=session_id,
        ))
    revoke_login_session(request, db)
    db.commit()
    return RedirectResponse("/login", status_code=303)


@app.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    today = date.today()
    if user.business_type == BusinessType.CATERING:
        if is_pos_host(request):
            request.session.clear()
            management_host = os.getenv("MANAGEMENT_HOST", "yonetim.bereketsofram.com").strip()
            return StarletteRedirectResponse(f"https://{management_host}{APP_PREFIX}/login", status_code=303)
        if os.getenv("CATERING_NATIVE_ENABLED", "false").lower() == "true" and os.getenv("CATERING_BACKEND", "php") == "native":
            return RedirectResponse("/catering-native/", status_code=303)
        return RedirectResponse("/legacy-catering-entry", status_code=303)
    if is_pos_host(request):
        if permission_decision(db, user.id, "reports.view").allowed:
            return RedirectResponse("/yonetim", status_code=303)
        if permission_decision(db, user.id, "payment.create").allowed:
            return RedirectResponse("/kasa", status_code=303)
        return RedirectResponse("/pos/masalar", status_code=303)
    revenue = db.query(func.coalesce(func.sum(RestaurantRevenue.amount), 0)).filter(RestaurantRevenue.user_id == user.id, RestaurantRevenue.revenue_date == today).scalar() or Decimal("0")
    expense = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.user_id == user.id, Expense.expense_date == today).scalar() or Decimal("0")
    return page(request, user, "dashboard.html", kind="restaurant", today_revenue=revenue, today_expense=expense, today_profit=Decimal(revenue) - Decimal(expense))


@app.get("/legacy-catering-entry")
def legacy_catering_entry(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.business_type != BusinessType.CATERING:
        return RedirectResponse("/dashboard", status_code=303)
    timestamp = int(time.time())
    payload = f"catering:{timestamp}".encode("utf-8")
    secret = os.environ["CATERING_SSO_SECRET"].encode("utf-8")
    signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return RedirectResponse(f"/catering/sso.php?ts={timestamp}&sig={signature}", status_code=303)


@app.get("/legacy-catering-logout")
def legacy_catering_logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    session_id = request.session.get("login_session_id")
    if user_id and session_id:
        db.add(AuditLog(actor_user_id=user_id, action="LOGOUT", entity_type="login_session", entity_id=session_id, session_id=session_id))
    revoke_login_session(request, db)
    db.commit()
    return RedirectResponse("/login", status_code=303)


@app.get("/catering/customers")
def catering_customers(request: Request, db: Session = Depends(get_db)):
    user, response = require_business(request, db, BusinessType.CATERING)
    if response:
        return response
    rows = []
    for customer in db.query(Customer).filter(Customer.user_id == user.id).order_by(Customer.company_name).all():
        total, paid, open_debt = customer_total(customer, db)
        rows.append({"customer": customer, "total": total, "paid": paid, "open": open_debt})
    return page(request, user, "customers.html", active=[r for r in rows if r["customer"].active], inactive=[r for r in rows if not r["customer"].active and r["open"] > 0])


@app.post("/catering/customers")
def add_customer(request: Request, company_name: str = Form(...), meal_price: str = Form("0"), default_people: int = Form(0), contact_name: str = Form(""), phone: str = Form(""), address: str = Form(""), overtime_price: str = Form("0"), carried_debt: str = Form("0"), invoice_customer: bool = Form(False), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_business(request, db, BusinessType.CATERING)
    if response:
        return response
    db.add(Customer(user_id=user.id, company_name=company_name.strip(), contact_name=contact_name.strip(), phone=phone.strip(), address=address.strip(), meal_price=parse_amount(meal_price), overtime_price=parse_amount(overtime_price), default_people=max(0, default_people), carried_debt=parse_amount(carried_debt), invoice_customer=invoice_customer))
    db.commit()
    return RedirectResponse("/catering/customers", status_code=303)


@app.get("/catering/daily")
def catering_daily(request: Request, entry_date: date | None = None, db: Session = Depends(get_db)):
    user, response = require_business(request, db, BusinessType.CATERING)
    if response:
        return response
    entry_date = entry_date or date.today()
    customers = db.query(Customer).filter(Customer.user_id == user.id, Customer.active.is_(True)).order_by(Customer.company_name).all()
    records = {record.customer_id: record for record in db.query(DailyMeal).join(Customer).filter(Customer.user_id == user.id, DailyMeal.entry_date == entry_date).all()}
    return page(request, user, "daily_meals.html", entry_date=entry_date, customers=customers, records=records)


@app.post("/catering/daily")
async def save_catering_daily(request: Request, db: Session = Depends(get_db)):
    user, response = require_business(request, db, BusinessType.CATERING)
    if response:
        return response
    form = await request.form()
    validate_csrf(request, str(form.get("csrf_token", "")))
    entry_date = date.fromisoformat(str(form.get("entry_date", date.today())))
    customers = db.query(Customer).filter(Customer.user_id == user.id, Customer.active.is_(True)).all()
    for customer in customers:
        meals = max(0, int(form.get(f"meal_{customer.id}", customer.default_people) or 0))
        overtime = max(0, int(form.get(f"overtime_{customer.id}", 0) or 0))
        record = db.query(DailyMeal).filter(DailyMeal.customer_id == customer.id, DailyMeal.entry_date == entry_date).first()
        if meals == 0 and overtime == 0:
            if record:
                db.delete(record)
        elif record:
            record.meal_count, record.overtime_count = meals, overtime
        else:
            db.add(DailyMeal(customer_id=customer.id, entry_date=entry_date, meal_count=meals, overtime_count=overtime))
    db.commit()
    return RedirectResponse(f"/catering/daily?entry_date={entry_date}", status_code=303)


@app.get("/catering/customers/{customer_id}")
def customer_detail(customer_id: int, request: Request, db: Session = Depends(get_db)):
    user, response = require_business(request, db, BusinessType.CATERING)
    if response:
        return response
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.user_id == user.id).first()
    if not customer:
        return RedirectResponse("/catering/customers", status_code=303)
    total, paid, open_debt = customer_total(customer, db)
    payments = db.query(CateringPayment).filter(CateringPayment.customer_id == customer.id).order_by(CateringPayment.payment_date.desc()).all()
    return page(request, user, "customer_detail.html", customer=customer, total=total, paid=paid, open_debt=open_debt, payments=payments)


@app.get("/catering/customers/{customer_id}/statement/{statement_type}.pdf")
def customer_statement(customer_id: int, statement_type: str, request: Request, db: Session = Depends(get_db)):
    user, response = require_business(request, db, BusinessType.CATERING)
    if response:
        return response
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.user_id == user.id).first()
    if not customer or statement_type not in {"summary", "detail"}:
        return RedirectResponse("/catering/customers", status_code=303)
    pdf = build_statement_pdf(customer, db, detailed=statement_type == "detail")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", customer.company_name).strip("-.") or "musteri"
    filename = f"{safe_name}-{statement_type}-ekstre.pdf"
    return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})


@app.post("/catering/customers/{customer_id}/update")
def update_customer(customer_id: int, request: Request, carried_debt: str = Form("0"), active: bool = Form(False), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_business(request, db, BusinessType.CATERING)
    if response:
        return response
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.user_id == user.id).first()
    if customer:
        customer.carried_debt, customer.active = parse_amount(carried_debt), active
        db.commit()
    return RedirectResponse(f"/catering/customers/{customer_id}", status_code=303)


@app.post("/catering/customers/{customer_id}/payments")
def add_payment(customer_id: int, request: Request, amount: str = Form(...), payment_date: date = Form(...), note: str = Form(""), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_business(request, db, BusinessType.CATERING)
    if response:
        return response
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.user_id == user.id).first()
    if customer and parse_amount(amount) > 0:
        db.add(CateringPayment(customer_id=customer.id, payment_date=payment_date, amount=parse_amount(amount), note=note.strip()))
        db.commit()
    return RedirectResponse(f"/catering/customers/{customer_id}", status_code=303)


@app.get("/restaurant")
def restaurant(request: Request, record_date: date | None = None, db: Session = Depends(get_db)):
    user, response = require_business(request, db, BusinessType.RESTAURANT)
    if response:
        return response
    record_date = record_date or date.today()
    revenue = db.query(RestaurantRevenue).filter(RestaurantRevenue.user_id == user.id, RestaurantRevenue.revenue_date == record_date).first()
    expenses = db.query(Expense).filter(Expense.user_id == user.id, Expense.expense_date == record_date).order_by(Expense.id.desc()).all()
    total_expense = sum((Decimal(e.amount) for e in expenses), Decimal("0"))
    return page(request, user, "restaurant.html", record_date=record_date, revenue=revenue, expenses=expenses, total_expense=total_expense)


@app.post("/restaurant/revenue")
def save_revenue(request: Request, amount: str = Form(...), revenue_date: date = Form(...), note: str = Form(""), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_business(request, db, BusinessType.RESTAURANT)
    if response:
        return response
    record = db.query(RestaurantRevenue).filter(RestaurantRevenue.user_id == user.id, RestaurantRevenue.revenue_date == revenue_date).first()
    if not record:
        record = RestaurantRevenue(user_id=user.id, revenue_date=revenue_date)
        db.add(record)
    record.amount, record.note = parse_amount(amount), note.strip()
    db.commit()
    return RedirectResponse(f"/restaurant?record_date={revenue_date}", status_code=303)


@app.post("/restaurant/expenses")
def add_expense(request: Request, category: str = Form(...), description: str = Form(...), amount: str = Form(...), expense_date: date = Form(...), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_business(request, db, BusinessType.RESTAURANT)
    if response:
        return response
    if parse_amount(amount) > 0:
        db.add(Expense(user_id=user.id, expense_date=expense_date, category=category, description=description.strip(), amount=parse_amount(amount)))
        db.commit()
    return RedirectResponse(f"/restaurant?record_date={expense_date}", status_code=303)


@app.get("/restaurant/employees")
def restaurant_employees(request: Request, db: Session = Depends(get_db)):
    user, response = require_business(request, db, BusinessType.RESTAURANT)
    if response:
        return response
    employees = db.query(Employee).filter(Employee.user_id == user.id).order_by(Employee.active.desc(), Employee.name).all()
    payments = (
        db.query(SalaryPayment, Employee.name)
        .join(Employee, SalaryPayment.employee_id == Employee.id)
        .filter(Employee.user_id == user.id)
        .order_by(SalaryPayment.payment_date.desc(), SalaryPayment.id.desc())
        .limit(20)
        .all()
    )
    return page(request, user, "employees.html", employees=employees, payments=payments, today=date.today())


@app.post("/restaurant/employees")
def add_employee(request: Request, name: str = Form(...), role: str = Form(""), monthly_salary: str = Form("0"), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_business(request, db, BusinessType.RESTAURANT)
    if response:
        return response
    db.add(Employee(user_id=user.id, name=name.strip(), role=role.strip(), monthly_salary=parse_amount(monthly_salary)))
    db.commit()
    return RedirectResponse("/restaurant/employees", status_code=303)


@app.post("/restaurant/employees/{employee_id}/payments")
def add_salary_payment(employee_id: int, request: Request, amount: str = Form(...), payment_date: date = Form(...), note: str = Form(""), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_business(request, db, BusinessType.RESTAURANT)
    if response:
        return response
    employee = db.query(Employee).filter(Employee.id == employee_id, Employee.user_id == user.id).first()
    value = parse_amount(amount)
    if employee and value > 0:
        db.add(SalaryPayment(employee_id=employee.id, payment_date=payment_date, amount=value, note=note.strip()))
        db.commit()
    return RedirectResponse("/restaurant/employees", status_code=303)


@app.post("/restaurant/expenses/{expense_id}/delete")
def delete_expense(expense_id: int, request: Request, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_business(request, db, BusinessType.RESTAURANT)
    if response:
        return response
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == user.id).first()
    if expense:
        recorded_date = expense.expense_date
        db.delete(expense)
        db.commit()
        return RedirectResponse(f"/restaurant?record_date={recorded_date}", status_code=303)
    return RedirectResponse("/restaurant", status_code=303)


@app.get("/restaurant/reports")
def restaurant_reports(request: Request, month: str = "", db: Session = Depends(get_db)):
    user, response = require_business(request, db, BusinessType.RESTAURANT)
    if response:
        return response
    try:
        start = date.fromisoformat(f"{month}-01") if month else date.today().replace(day=1)
    except ValueError:
        start = date.today().replace(day=1)
    next_month = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
    end = next_month
    revenue = db.query(func.coalesce(func.sum(RestaurantRevenue.amount), 0)).filter(RestaurantRevenue.user_id == user.id, RestaurantRevenue.revenue_date >= start, RestaurantRevenue.revenue_date < end).scalar() or Decimal("0")
    expenses = db.query(Expense).filter(Expense.user_id == user.id, Expense.expense_date >= start, Expense.expense_date < end).order_by(Expense.expense_date.desc()).all()
    operating_expense = sum((Decimal(row.amount) for row in expenses), Decimal("0"))
    salaries = db.query(func.coalesce(func.sum(SalaryPayment.amount), 0)).join(Employee, SalaryPayment.employee_id == Employee.id).filter(Employee.user_id == user.id, SalaryPayment.payment_date >= start, SalaryPayment.payment_date < end).scalar() or Decimal("0")
    category_totals = {}
    for row in expenses:
        category_totals[row.category] = category_totals.get(row.category, Decimal("0")) + Decimal(row.amount)
    revenue_rows = (
        db.query(RestaurantRevenue)
        .filter(RestaurantRevenue.user_id == user.id, RestaurantRevenue.revenue_date >= start, RestaurantRevenue.revenue_date < end)
        .order_by(RestaurantRevenue.revenue_date)
        .all()
    )
    chart_max = max((Decimal(row.amount) for row in revenue_rows), default=Decimal("1"))
    daily_points = [
        {"day": row.revenue_date.day, "amount": Decimal(row.amount), "height": max(4, int(Decimal(row.amount) / chart_max * 100))}
        for row in revenue_rows
    ]
    return page(
        request, user, "restaurant_reports.html", month=start.strftime("%Y-%m"), revenue=Decimal(revenue),
        operating_expense=operating_expense, salaries=Decimal(salaries),
        profit=Decimal(revenue) - operating_expense - Decimal(salaries), category_totals=category_totals, daily_points=daily_points,
    )


@app.get("/pos")
def pos_root():
    return RedirectResponse("/pos/masalar", status_code=303)


@app.get("/pos/masalar")
def pos_tables(request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db)
    if response:
        return response
    rows = db.execute(
        select(RestaurantTable, TableSection, ServiceSession, Check, User)
        .join(TableSection, TableSection.id == RestaurantTable.section_id)
        .outerjoin(ServiceSession, and_(ServiceSession.table_id == RestaurantTable.id, ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES)))
        .outerjoin(Check, Check.service_session_id == ServiceSession.id)
        .outerjoin(User, User.id == ServiceSession.primary_waiter_id)
        .where(RestaurantTable.is_active.is_(True), TableSection.is_active.is_(True))
        .order_by(TableSection.sort_order, RestaurantTable.sort_order, RestaurantTable.id)
    ).all()
    cards = [
        {
            "table": table, "section": section, "service": service, "check": check, "waiter": waiter,
            "status": service.operational_status.value if service else "EMPTY",
        }
        for table, section, service, check, waiter in rows
    ]
    sections = db.scalars(select(TableSection).where(TableSection.is_active.is_(True)).order_by(TableSection.sort_order, TableSection.name)).all()
    return page(request, user, "pos_tables.html", cards=cards, sections=sections, can_open=permission_decision(db, user.id, "service.open").allowed)


@app.get("/pos/masa/{table_id}")
def pos_table_check(table_id: int, request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db)
    if response:
        return response
    table = db.get(RestaurantTable, table_id)
    if table is None:
        return RedirectResponse("/pos/masalar", status_code=303)
    service = db.scalar(select(ServiceSession).where(ServiceSession.table_id == table_id, ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES)))
    check = db.scalar(select(Check).where(Check.service_session_id == service.id)) if service else None
    waiter = db.get(User, service.primary_waiter_id) if service else None
    items = db.scalars(select(CheckItem).where(CheckItem.check_id == check.id).order_by(CheckItem.created_at, CheckItem.id)).all() if check else []
    categories = db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name)).all()
    products = db.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.is_favorite.desc(), Product.sort_order, Product.name)).all()
    permissions = {code: permission_decision(db, user.id, code).allowed for code in (
        "service.open", "order.add_item", "order.change_quantity", "order.cancel_item", "order.comp_item",
        "discount.apply", "check.request", "check.cancel_request", "payment.create", "payment.create_without_check_request",
    )}
    return page(
        request, user, "pos_check.html", table=table, service=service, check=check, waiter=waiter,
        items=items, categories=categories, products=products, permissions=permissions,
        check_requested=active_check_request(service) if service else False,
        unsent_count=sum(1 for item in items if not item.is_cancelled and item.sent_to_kitchen_at is None),
    )


@app.post("/pos/masa/{table_id}/mutfaga-gonder")
def kitchen_send_page(table_id: int, request: Request, csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_pos_page(request, db, "order.add_item")
    if response:
        return response
    try:
        check, service, items, sent_at = send_to_kitchen(db, user.id, table_id)
        table = db.get(RestaurantTable, table_id)
        waiter = db.get(User, service.primary_waiter_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return printable_page(request, "kitchen_receipt.html", check=check, table=table, waiter=waiter, items=items, sent_at=sent_at)


@app.get("/kasa")
def cashier_page(request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db, "payment.create")
    if response:
        return response
    rows = db.execute(
        select(Check, ServiceSession, RestaurantTable, User, exists(select(Payment.id).where(Payment.check_id == Check.id, Payment.created_by_user_id == user.id)).label("is_mine"))
        .join(ServiceSession, ServiceSession.id == Check.service_session_id)
        .join(RestaurantTable, RestaurantTable.id == ServiceSession.table_id)
        .join(User, User.id == ServiceSession.primary_waiter_id)
        .where(Check.status != CheckStatus.CLOSED)
        .order_by(Check.opened_at)
    ).all()
    checks = [
        {"check": check, "service": service, "table": table, "waiter": waiter, "requested": active_check_request(service), "mine": bool(is_mine)}
        for check, service, table, waiter, is_mine in rows
    ]
    checks.sort(key=lambda row: (not row["requested"], row["check"].opened_at))
    recent_receipts = db.execute(
        select(Check, ServiceSession, RestaurantTable)
        .join(ServiceSession, ServiceSession.id == Check.service_session_id)
        .join(RestaurantTable, RestaurantTable.id == ServiceSession.table_id)
        .where(Check.status == CheckStatus.CLOSED)
        .order_by(Check.closed_at.desc()).limit(20)
    ).all()
    can_manage_daily_menu = permission_decision(db, user.id, "menu.daily_manage").allowed
    return page(request, user, "cashier.html", checks=checks, recent_receipts=recent_receipts, can_manage_daily_menu=can_manage_daily_menu)


@app.get("/kasa/fis/{check_id}")
def customer_receipt_page(check_id: int, request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db, "payment.create")
    if response:
        return response
    check = db.get(Check, check_id)
    if check is None or check.status not in (CheckStatus.PAID, CheckStatus.CLOSED):
        raise HTTPException(status_code=404, detail="Ödemesi tamamlanmış adisyon bulunamadı.")
    service = db.get(ServiceSession, check.service_session_id)
    table = db.get(RestaurantTable, service.table_id)
    waiter = db.get(User, service.primary_waiter_id)
    items = db.scalars(select(CheckItem).where(CheckItem.check_id == check.id, CheckItem.is_cancelled.is_(False)).order_by(CheckItem.id)).all()
    payments = db.scalars(select(Payment).where(Payment.check_id == check.id, Payment.status == PaymentStatus.COMPLETED).order_by(Payment.id)).all()
    taxable_gross = sum((Decimal(item.line_total) for item in items if not item.is_comp), Decimal("0"))
    gross_vat = sum((Decimal(item.line_total) * Decimal(item.tax_rate_snapshot) / (Decimal("100") + Decimal(item.tax_rate_snapshot)) for item in items if not item.is_comp and Decimal(item.tax_rate_snapshot) > 0), Decimal("0"))
    vat_total = (gross_vat * Decimal(check.final_total) / taxable_gross).quantize(Decimal("0.01")) if taxable_gross else Decimal("0")
    return printable_page(request, "customer_receipt.html", check=check, service=service, table=table, waiter=waiter, items=items, payments=payments, vat_total=vat_total, printed_at=check.closed_at or datetime.utcnow())


@app.get("/kasa/vardiya")
def shift_page(request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db)
    if response:
        return response
    can_open = permission_decision(db, user.id, "shift.open").allowed
    can_close = permission_decision(db, user.id, "shift.close").allowed
    if not (can_open or can_close):
        return RedirectResponse("/dashboard", status_code=303)
    shift = db.scalar(select(Shift).where(Shift.closed_at.is_(None)).order_by(Shift.opened_at.desc()))
    summary = shift_summary(db, shift) if shift else None
    return page(request, user, "shift.html", shift=shift, summary=summary, can_open=can_open, can_close=can_close)


@app.post("/kasa/vardiya/ac")
def shift_open_page(request: Request, opening_cash_amount: str = Form(...), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_pos_page(request, db, "shift.open")
    if response:
        return response
    try:
        open_shift(db, user.id, parse_amount(opening_cash_amount))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse("/kasa/vardiya", status_code=303)


@app.post("/kasa/vardiya/kapat")
def shift_close_page(request: Request, closing_cash_amount: str = Form(...), note: str = Form(""), csrf_token: str = Form(...), db: Session = Depends(get_db)):
    validate_csrf(request, csrf_token)
    user, response = require_pos_page(request, db, "shift.close")
    if response:
        return response
    try:
        closed, _ = close_shift(db, user.id, parse_amount(closing_cash_amount), note)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse(f"/yonetim/vardiyalar?closed={closed.id}", status_code=303)


@app.get("/kasa/gunun-menusu")
def daily_menu_page(request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db, "menu.daily_manage")
    if response:
        return response
    categories = db.scalars(select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name)).all()
    products = db.scalars(select(Product).where(Product.is_active.is_(True)).order_by(Product.sort_order, Product.name)).all()
    by_category: dict[int, list[Product]] = {}
    for product in products:
        by_category.setdefault(product.category_id, []).append(product)
    return page(request, user, "daily_menu.html", categories=categories, by_category=by_category, selected_count=sum(1 for row in products if row.is_favorite))


@app.post("/kasa/gunun-menusu")
async def daily_menu_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    validate_csrf(request, str(form.get("csrf_token", "")))
    user, response = require_pos_page(request, db, "menu.daily_manage")
    if response:
        return response
    product_ids = [int(value) for value in form.getlist("product_ids") if str(value).isdigit()]
    try:
        set_daily_menu(db, user.id, product_ids)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return RedirectResponse("/kasa/gunun-menusu", status_code=303)


@app.get("/yonetim")
def management_page(request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db, "reports.view")
    if response:
        return response
    today = date.today()
    closed = db.scalars(select(Check).where(Check.status == CheckStatus.CLOSED, func.date(Check.closed_at) == today)).all()
    active_services = db.scalars(select(ServiceSession).where(ServiceSession.operational_status.in_(ACTIVE_SERVICE_STATUSES))).all()
    closed_service_ids = [row.service_session_id for row in closed]
    guests = db.scalar(select(func.coalesce(func.sum(ServiceSession.guest_count), 0)).where(ServiceSession.id.in_(closed_service_ids))) if closed_service_ids else 0
    net = sum((Decimal(row.final_total) for row in closed), Decimal("0"))
    requested = sum(1 for row in active_services if active_check_request(row))
    recent_audit = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(15)).all()
    live_checks = db.execute(
        select(Check, ServiceSession, RestaurantTable, User)
        .join(ServiceSession, ServiceSession.id == Check.service_session_id)
        .join(RestaurantTable, RestaurantTable.id == ServiceSession.table_id)
        .join(User, User.id == ServiceSession.primary_waiter_id)
        .where(Check.status != CheckStatus.CLOSED)
        .order_by(Check.opened_at)
    ).all()
    recent_closed = db.execute(
        select(Check, ServiceSession, RestaurantTable)
        .join(ServiceSession, ServiceSession.id == Check.service_session_id)
        .join(RestaurantTable, RestaurantTable.id == ServiceSession.table_id)
        .where(Check.status == CheckStatus.CLOSED)
        .order_by(Check.closed_at.desc()).limit(20)
    ).all()
    return page(
        request, user, "management.html", net=net, guests=int(guests or 0), per_guest=(net / Decimal(guests)).quantize(Decimal("0.01")) if guests else Decimal("0"),
        active_count=len(active_services), requested_count=requested, closed_count=len(closed), recent_audit=recent_audit,
        live_checks=live_checks, recent_closed=recent_closed,
    )


@app.get("/yonetim/raporlar")
def operation_reports_page(request: Request, date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db, "reports.view")
    if response:
        return response
    end = date_to or date.today()
    start = date_from or end.replace(day=1)
    try:
        report = operation_report(db, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return page(request, user, "reports.html", report=report)


@app.get("/yonetim/vardiyalar")
def shifts_management_page(request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db, "reports.view")
    if response:
        return response
    shifts = db.scalars(select(Shift).order_by(Shift.opened_at.desc()).limit(100)).all()
    opened_by = {row.id: row for row in db.scalars(select(User).where(User.id.in_({shift.opened_by_user_id for shift in shifts}))).all()} if shifts else {}
    closed_ids = {shift.closed_by_user_id for shift in shifts if shift.closed_by_user_id}
    closed_by = {row.id: row for row in db.scalars(select(User).where(User.id.in_(closed_ids))).all()} if closed_ids else {}
    rows = [{"shift": shift, "summary": shift_summary(db, shift), "opener": opened_by.get(shift.opened_by_user_id), "closer": closed_by.get(shift.closed_by_user_id)} for shift in shifts]
    return page(request, user, "shifts.html", rows=rows)


@app.get("/yonetim/adisyon/{check_id}")
def management_check_page(check_id: int, request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db, "reports.view")
    if response:
        return response
    check = db.get(Check, check_id)
    if check is None:
        return RedirectResponse("/yonetim", status_code=303)
    service = db.get(ServiceSession, check.service_session_id)
    table = db.get(RestaurantTable, service.table_id)
    waiter = db.get(User, service.primary_waiter_id)
    items = db.scalars(select(CheckItem).where(CheckItem.check_id == check.id).order_by(CheckItem.created_at, CheckItem.id)).all()
    payments = db.scalars(select(Payment).where(Payment.check_id == check.id).order_by(Payment.created_at, Payment.id)).all()
    discounts = db.scalars(select(Discount).where(Discount.check_id == check.id).order_by(Discount.id)).all()
    tables = db.scalars(select(RestaurantTable).where(RestaurantTable.is_active.is_(True)).order_by(RestaurantTable.display_name)).all()
    waiters = db.scalars(select(User).where(User.business_type == BusinessType.RESTAURANT, User.is_active.is_(True)).order_by(User.name)).all()
    permissions = {code: permission_decision(db, user.id, code).allowed for code in (
        "service.change_guest_count", "service.move_table", "service.transfer_waiter", "order.cancel_item", "order.comp_item",
        "service.merge", "service.split", "order.change_price", "discount.remove", "payment.reverse", "payment.change_method", "payment.force_close", "check.reopen",
    )}
    return page(request, user, "management_check.html", check=check, service=service, table=table, waiter=waiter, items=items, payments=payments, discounts=discounts, tables=tables, waiters=waiters, permissions=permissions)


@app.get("/yonetim/tanimlar")
def definitions_page(request: Request, db: Session = Depends(get_db)):
    user, response = require_pos_page(request, db)
    if response:
        return response
    if not (permission_decision(db, user.id, "tables.manage").allowed or permission_decision(db, user.id, "products.manage").allowed or permission_decision(db, user.id, "users.manage").allowed):
        return RedirectResponse("/yonetim", status_code=303)
    sections = db.scalars(select(TableSection).order_by(TableSection.sort_order, TableSection.name)).all()
    tables = db.execute(select(RestaurantTable, TableSection).join(TableSection).order_by(TableSection.name, RestaurantTable.sort_order, RestaurantTable.id)).all()
    categories = db.scalars(select(Category).order_by(Category.sort_order, Category.name)).all()
    products = db.execute(select(Product, Category).join(Category).order_by(Category.name, Product.name)).all()
    users = db.execute(select(User, Role).outerjoin(UserRole, UserRole.user_id == User.id).outerjoin(Role, Role.id == UserRole.role_id).where(User.business_type == BusinessType.RESTAURANT).order_by(User.name)).all()
    capabilities = {
        "tables": permission_decision(db, user.id, "tables.manage").allowed,
        "products": permission_decision(db, user.id, "products.manage").allowed,
        "users": permission_decision(db, user.id, "users.manage").allowed,
        "settings": permission_decision(db, user.id, "settings.manage").allowed,
    }
    return page(request, user, "definitions.html", sections=sections, tables=tables, categories=categories, products=products, users=users, capabilities=capabilities)

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, Encounter, InventoryLot, InventoryProduct, InventoryTransaction, Patient, Prescription, User
from ..schemas import InventoryDispenseCreate, InventoryLotCreate, InventoryLotDestroy, InventoryLotOut, InventoryMovementCreate, InventoryProductCreate, InventoryProductOut, InventoryTransactionOut
from ..security import inventory_dispense_user, inventory_user, inventory_write_user
from ..services.access import require_warehouse_access, warehouse_scope
from ..services.patients import patient_by_uuid

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


def product_by_uuid(db: Session, product_uuid: str, lock: bool = False) -> InventoryProduct:
    query = select(InventoryProduct).where(InventoryProduct.uuid == product_uuid)
    product = db.scalar(query.with_for_update() if lock else query)
    if not product:
        raise HTTPException(status_code=404, detail="Inventory product not found")
    return product


def lot_by_uuid(db: Session, product: InventoryProduct, lot_uuid: str, lock: bool = False) -> InventoryLot:
    query = select(InventoryLot).where(InventoryLot.uuid == lot_uuid, InventoryLot.product_id == product.id)
    lot = db.scalar(query.with_for_update() if lock else query)
    if not lot:
        raise HTTPException(status_code=404, detail="Inventory lot not found")
    return lot


def product_out(db: Session, product: InventoryProduct, user: User) -> InventoryProductOut:
    query = select(func.coalesce(func.sum(InventoryLot.on_hand), 0)).where(InventoryLot.product_id == product.id, InventoryLot.destroyed_at.is_(None))
    scope = warehouse_scope(db, user)
    if scope is not None: query = query.where(InventoryLot.warehouse_id.in_(scope))
    on_hand = db.scalar(query)
    return InventoryProductOut.model_validate({**product.__dict__, "on_hand": int(on_hand or 0)})


def transaction_out(db: Session, item: InventoryTransaction) -> InventoryTransactionOut:
    product = db.get(InventoryProduct, item.product_id)
    lot = db.get(InventoryLot, item.lot_id) if item.lot_id else None
    destination = db.get(InventoryLot, item.destination_lot_id) if item.destination_lot_id else None
    patient = db.get(Patient, item.patient_id) if item.patient_id else None
    encounter = db.get(Encounter, item.encounter_id) if item.encounter_id else None
    return InventoryTransactionOut(product_uuid=product.uuid, lot_uuid=lot.uuid if lot else None, destination_lot_uuid=destination.uuid if destination else None, patient_uuid=patient.uuid if patient else None, encounter_uuid=encounter.uuid if encounter else None, **{key: getattr(item, key) for key in ("uuid", "transaction_type", "occurred_on", "quantity", "fee", "billed", "actor_name", "notes")})


@router.get("/products", response_model=list[InventoryProductOut])
def list_products(q: str | None = None, active: bool | None = True, db: Session = Depends(get_db), user: User = Depends(inventory_user)):
    query = select(InventoryProduct)
    if q:
        query = query.where(InventoryProduct.name.ilike(f"%{q}%"))
    if active is not None:
        query = query.where(InventoryProduct.active == active)
    products = list(db.scalars(query.order_by(InventoryProduct.name).limit(500)))
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="inventory_product")); db.commit()
    return [product_out(db, product, user) for product in products]


@router.post("/products", response_model=InventoryProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: InventoryProductCreate, db: Session = Depends(get_db), user: User = Depends(inventory_write_user)):
    product = InventoryProduct(**body.model_dump())
    db.add(product); db.flush(); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="inventory_product", resource_id=product.uuid)); db.commit(); db.refresh(product)
    return product_out(db, product, user)


@router.get("/products/{product_uuid}/lots", response_model=list[InventoryLotOut])
def list_lots(product_uuid: str, include_destroyed: bool = False, warehouse_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(inventory_user)):
    product = product_by_uuid(db, product_uuid)
    query = select(InventoryLot).where(InventoryLot.product_id == product.id)
    scope = warehouse_scope(db, user)
    if scope is not None: query = query.where(InventoryLot.warehouse_id.in_(scope))
    if not include_destroyed:
        query = query.where(InventoryLot.destroyed_at.is_(None))
    if warehouse_id is not None:
        query = query.where(InventoryLot.warehouse_id == warehouse_id)
    rows = list(db.scalars(query.order_by(InventoryLot.expiration.asc().nullslast(), InventoryLot.lot_number)))
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="inventory_lot", resource_id=product.uuid)); db.commit()
    return rows


@router.post("/products/{product_uuid}/lots", response_model=InventoryLotOut, status_code=status.HTTP_201_CREATED)
def create_lot(product_uuid: str, body: InventoryLotCreate, db: Session = Depends(get_db), user: User = Depends(inventory_write_user)):
    product = product_by_uuid(db, product_uuid, lock=True)
    require_warehouse_access(db, user, body.warehouse_id)
    if not product.allow_multiple:
        existing = db.scalar(select(InventoryLot.id).where(InventoryLot.product_id == product.id, InventoryLot.warehouse_id == body.warehouse_id, InventoryLot.destroyed_at.is_(None)))
        if existing:
            raise HTTPException(status_code=409, detail="Product allows only one active lot per warehouse")
    lot = InventoryLot(product_id=product.id, **body.model_dump(exclude={"opening_quantity", "notes"}), on_hand=body.opening_quantity)
    db.add(lot); db.flush()
    if body.opening_quantity:
        db.add(InventoryTransaction(product_id=product.id, lot_id=lot.id, transaction_type="purchase", occurred_on=date.today(), quantity=body.opening_quantity, actor_id=user.id, actor_name=user.email, notes=body.notes or "Opening balance"))
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="inventory_lot", resource_id=lot.uuid)); db.commit(); db.refresh(lot)
    return lot


@router.post("/products/{product_uuid}/lots/{lot_uuid}/destroy", response_model=InventoryLotOut)
def destroy_lot(product_uuid: str, lot_uuid: str, body: InventoryLotDestroy, db: Session = Depends(get_db), user: User = Depends(inventory_write_user)):
    product = product_by_uuid(db, product_uuid, lock=True); lot = lot_by_uuid(db, product, lot_uuid, lock=True)
    require_warehouse_access(db, user, lot.warehouse_id)
    if lot.destroyed_at:
        raise HTTPException(status_code=409, detail="Inventory lot is already destroyed")
    lot.destroyed_at = body.destroyed_at; lot.destruction_method = body.method; lot.destruction_witness = body.witness; lot.destruction_notes = body.notes
    db.add(AuditEvent(actor_id=user.id, action="destroy", resource_type="inventory_lot", resource_id=lot.uuid, detail=f"method={body.method};witness={body.witness}")); db.commit(); db.refresh(lot)
    return lot


@router.post("/products/{product_uuid}/movements", response_model=list[InventoryTransactionOut], status_code=status.HTTP_201_CREATED)
def move_inventory(product_uuid: str, body: InventoryMovementCreate, db: Session = Depends(get_db), user: User = Depends(inventory_write_user)):
    product = product_by_uuid(db, product_uuid, lock=True); lot = lot_by_uuid(db, product, body.lot_uuid, lock=True)
    require_warehouse_access(db, user, lot.warehouse_id)
    if lot.destroyed_at:
        raise HTTPException(status_code=409, detail="Destroyed lots cannot be moved")
    if body.quantity == 0:
        raise HTTPException(status_code=422, detail="Quantity must not be zero")
    if body.transaction_type != "adjustment" and body.quantity < 0:
        raise HTTPException(status_code=422, detail="Only adjustments may use a negative quantity")
    delta = body.quantity if body.transaction_type in {"purchase", "adjustment"} else -abs(body.quantity)
    destination = None
    if body.transaction_type == "transfer":
        if not body.destination_lot_uuid:
            raise HTTPException(status_code=422, detail="Transfer requires a destination lot")
        destination = lot_by_uuid(db, product, body.destination_lot_uuid, lock=True)
        require_warehouse_access(db, user, destination.warehouse_id)
        if destination.id == lot.id or destination.destroyed_at:
            raise HTTPException(status_code=409, detail="Invalid transfer destination")
    if lot.on_hand + delta < 0:
        raise HTTPException(status_code=409, detail="Insufficient inventory")
    lot.on_hand += delta
    transaction = InventoryTransaction(product_id=product.id, lot_id=lot.id, destination_lot_id=destination.id if destination else None, transaction_type=body.transaction_type, occurred_on=body.occurred_on, quantity=body.quantity, actor_id=user.id, actor_name=user.email, notes=body.notes)
    db.add(transaction)
    if destination:
        destination.on_hand += abs(body.quantity)
    db.flush(); db.add(AuditEvent(actor_id=user.id, action=body.transaction_type, resource_type="inventory", resource_id=product.uuid, detail=f"quantity={body.quantity}")); db.commit(); db.refresh(transaction)
    return [transaction_out(db, transaction)]


@router.post("/products/{product_uuid}/dispense", response_model=list[InventoryTransactionOut], status_code=status.HTTP_201_CREATED)
def dispense(product_uuid: str, body: InventoryDispenseCreate, db: Session = Depends(get_db), user: User = Depends(inventory_dispense_user)):
    product = product_by_uuid(db, product_uuid, lock=True)
    patient = patient_by_uuid(db, body.patient_uuid)
    encounter = db.scalar(select(Encounter).where(Encounter.uuid == body.encounter_uuid, Encounter.patient_id == patient.id))
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found for patient")
    prescription = None
    if body.prescription_uuid:
        prescription = db.scalar(select(Prescription).where(Prescription.uuid == body.prescription_uuid, Prescription.patient_id == patient.id))
        if not prescription:
            raise HTTPException(status_code=404, detail="Prescription not found for patient")
    if not product.dispensable:
        if warehouse_scope(db, user) is not None:
            raise HTTPException(status_code=403, detail="Restricted users must select stock-backed dispensable products")
        lots = [None]
    else:
        query = select(InventoryLot).where(InventoryLot.product_id == product.id, InventoryLot.destroyed_at.is_(None), InventoryLot.on_hand > 0, (InventoryLot.expiration.is_(None) | (InventoryLot.expiration > body.occurred_on)))
        if body.warehouse_id is not None:
            require_warehouse_access(db, user, body.warehouse_id)
            query = query.where(InventoryLot.warehouse_id == body.warehouse_id)
        else:
            scope = warehouse_scope(db, user)
            if scope is not None: query = query.where(InventoryLot.warehouse_id.in_(scope))
        available = list(db.scalars(query.order_by(InventoryLot.expiration.asc().nullslast(), InventoryLot.lot_number, InventoryLot.id).with_for_update()))
        combining = product.allow_combining and prescription is None
        lots = available if combining else [next((lot for lot in available if lot.on_hand >= body.quantity), None)]
        if not lots or lots[0] is None or (combining and sum(lot.on_hand for lot in lots) < body.quantity):
            raise HTTPException(status_code=409, detail="Insufficient non-expired inventory")
    remaining = body.quantity; remaining_fee = body.fee; created = []
    for lot in lots:
        quantity = remaining if lot is None else min(remaining, lot.on_hand)
        fee = remaining_fee if quantity == remaining else (body.fee * Decimal(quantity) / Decimal(body.quantity)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if lot:
            lot.on_hand -= quantity
        item = InventoryTransaction(product_id=product.id, lot_id=lot.id if lot else None, patient_id=patient.id, encounter_id=encounter.id, prescription_id=prescription.id if prescription else None, transaction_type="dispense", occurred_on=body.occurred_on, quantity=quantity, fee=fee, actor_id=user.id, actor_name=user.email, notes=body.notes)
        db.add(item); created.append(item); remaining -= quantity; remaining_fee -= fee
        if remaining == 0:
            break
    db.flush(); db.add(AuditEvent(actor_id=user.id, action="dispense", resource_type="inventory", resource_id=product.uuid, detail=f"quantity={body.quantity};patient={patient.uuid}")); db.commit()
    return [transaction_out(db, item) for item in created]


@router.get("/transactions", response_model=list[InventoryTransactionOut])
def list_transactions(product_uuid: str | None = None, transaction_type: str | None = Query(default=None, alias="type"), db: Session = Depends(get_db), user: User = Depends(inventory_user)):
    query = select(InventoryTransaction)
    scope = warehouse_scope(db, user)
    if scope is not None:
        query = query.join(InventoryLot, InventoryTransaction.lot_id == InventoryLot.id).where(InventoryLot.warehouse_id.in_(scope))
    if product_uuid:
        product = product_by_uuid(db, product_uuid); query = query.where(InventoryTransaction.product_id == product.id)
    if transaction_type:
        query = query.where(InventoryTransaction.transaction_type == transaction_type)
    rows = list(db.scalars(query.order_by(InventoryTransaction.occurred_on.desc(), InventoryTransaction.id.desc()).limit(1000)))
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="inventory_transaction")); db.commit()
    return [transaction_out(db, item) for item in rows]

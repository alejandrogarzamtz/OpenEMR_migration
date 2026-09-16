import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";
import { uiCopy, type UiLanguage } from "../../i18n";

type Product={uuid:string;name:string;ndc_number?:string;on_hand:number;reorder_point:string;active:boolean};
type Lot={uuid:string;lot_number?:string;expiration?:string;warehouse_id:string;manufacturer?:string;on_hand:number;destroyed_at?:string};

export function InventoryWorkspace({api,language="es"}:{api:ApiRequest;language?:UiLanguage}){
  const [products,setProducts]=useState<Product[]>([]); const [selected,setSelected]=useState<Product|null>(null); const [lots,setLots]=useState<Lot[]>([]); const [error,setError]=useState("");
  const t=(spanish:string,english:string)=>uiCopy(language,spanish,english);
  async function loadProducts(){try{const rows=await api<Product[]>("/api/v1/inventory/products");setProducts(rows);if(selected)setSelected(rows.find(row=>row.uuid===selected.uuid)??null);setError("");}catch(reason){setError(reason instanceof Error?reason.message:"Could not load inventory");}}
  async function open(product:Product){setSelected(product);try{setLots(await api<Lot[]>(`/api/v1/inventory/products/${product.uuid}/lots`));}catch(reason){setError(reason instanceof Error?reason.message:"Could not load lots");}}
  useEffect(()=>{void loadProducts();},[]);
  async function createProduct(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=event.currentTarget;const data=new FormData(form);try{await api("/api/v1/inventory/products",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:data.get("name"),ndc_number:data.get("ndc_number")||null,reorder_point:Number(data.get("reorder_point")||0),allow_combining:data.get("allow_combining")==="on"})});form.reset();await loadProducts();}catch(reason){setError(reason instanceof Error?reason.message:"Could not save product");}}
  async function createLot(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!selected)return;const form=event.currentTarget;const data=new FormData(form);try{await api(`/api/v1/inventory/products/${selected.uuid}/lots`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({lot_number:data.get("lot_number")||null,expiration:data.get("expiration")||null,warehouse_id:data.get("warehouse_id"),manufacturer:data.get("manufacturer")||null,opening_quantity:Number(data.get("opening_quantity"))})});form.reset();await open(selected);await loadProducts();}catch(reason){setError(reason instanceof Error?reason.message:"Could not save lot");}}
  return <section className="inventory-workspace">
    <form className="card inventory-form" onSubmit={createProduct}>
      <div className="inventory-form-heading"><div><p className="eyebrow">{t("CATÁLOGO","CATALOG")}</p><h2>{t("Agregar producto","Add product")}</h2></div><p>{t("Registra el producto y define el nivel mínimo que activará una alerta.","Register the product and define the minimum level that triggers an alert.")}</p></div>
      <div className="inventory-product-grid">
        <label className="inventory-product-name">{t("Nombre del producto","Product name")}<input name="name" placeholder={t("Ej. Vacuna influenza","For example, influenza vaccine")} required maxLength={255}/></label>
        <label>NDC<input name="ndc_number" placeholder="Código NDC" maxLength={20}/></label>
        <label>{t("Punto de reorden","Reorder point")}<input name="reorder_point" type="number" min="0" step="0.001" defaultValue="0"/></label>
        <label className="check inventory-combine"><input name="allow_combining" type="checkbox"/> {t("Permitir combinar lotes","Allow lot combining")}</label>
      </div>
      <div className="inventory-form-actions"><button>{t("Agregar producto","Add product")}</button></div>
    </form>
    {error&&<p className="error">{error}</p>}
    <div className={selected?"inventory-grid selected":"inventory-grid"}>
      <section className="card inventory-products">
        <div className="inventory-list-heading"><div><p className="eyebrow">{t("EXISTENCIAS","STOCK")}</p><h2>{t("Productos","Products")}</h2></div><span>{products.length}</span></div>
        <table><thead><tr><th>{t("Producto","Product")}</th><th>NDC</th><th>{t("Disponible","On hand")}</th></tr></thead><tbody>{products.map(product=><tr key={product.uuid} onClick={()=>void open(product)} className="patient-row"><td><strong>{product.name}</strong><small>{t("Punto de reorden","Reorder point")}: {product.reorder_point}</small></td><td>{product.ndc_number??"—"}</td><td className={product.on_hand<=Number(product.reorder_point)?"low-stock":""}>{product.on_hand}</td></tr>)}</tbody></table>
        {!products.length&&<div className="inventory-empty"><span aria-hidden="true">□</span><strong>{t("No hay productos registrados","No products registered")}</strong><p>{t("Agrega un producto para comenzar el control de existencias.","Add a product to begin tracking stock.")}</p></div>}
      </section>
      {selected&&<section className="card inventory-detail">
        <div className="inventory-detail-heading"><div><p className="eyebrow">{t("DETALLE DEL PRODUCTO","PRODUCT DETAIL")}</p><h2>{selected.name}</h2><p>{selected.ndc_number?`NDC ${selected.ndc_number}`:t("Sin código NDC","No NDC code")} · {selected.on_hand} {t("disponibles","on hand")}</p></div><button type="button" className="close" aria-label={t("Cerrar detalle","Close detail")} onClick={()=>setSelected(null)}>×</button></div>
        <form className="inventory-lot-form" onSubmit={createLot}><h3>{t("Agregar lote y existencia inicial","Add lot and opening stock")}</h3><label>{t("Número de lote","Lot number")}<input name="lot_number" placeholder="LOT-2026-01"/></label><label>{t("Caducidad","Expiration")}<input name="expiration" type="date"/></label><label>{t("Almacén","Warehouse")}<input name="warehouse_id" placeholder={t("Almacén","Warehouse")} required/></label><label>{t("Fabricante","Manufacturer")}<input name="manufacturer" placeholder={t("Fabricante","Manufacturer")}/></label><label>{t("Cantidad inicial","Opening quantity")}<input name="opening_quantity" type="number" min="0" defaultValue="0" required/></label><button>{t("Agregar lote","Add lot")}</button></form>
        <div className="inventory-lots-heading"><h3>{t("Lotes activos","Active lots")}</h3><span>{lots.length}</span></div>
        <div className="inventory-lots">{lots.map(lot=><article className="lot-row" key={lot.uuid}><div><strong>{lot.lot_number??t("Sin número de lote","No lot number")}</strong><small>{lot.warehouse_id||t("Almacén predeterminado","Default warehouse")}{lot.manufacturer?` · ${lot.manufacturer}`:""}</small></div><span>{lot.on_hand} {t("disponibles","on hand")}</span><small>{t("Caducidad","Expiration")}: {lot.expiration??t("No registrada","Not recorded")}</small></article>)}{!lots.length&&<p className="empty">{t("No hay lotes activos para este producto.","No active lots for this product.")}</p>}</div>
      </section>}
    </div>
  </section>;
}

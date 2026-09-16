import { FormEvent, useEffect, useState } from "react";
import type { ApiRequest } from "../../api/client";

type Product={uuid:string;name:string;ndc_number?:string;on_hand:number;reorder_point:string;active:boolean};
type Lot={uuid:string;lot_number?:string;expiration?:string;warehouse_id:string;manufacturer?:string;on_hand:number;destroyed_at?:string};

export function InventoryWorkspace({api}:{api:ApiRequest}){
  const [products,setProducts]=useState<Product[]>([]); const [selected,setSelected]=useState<Product|null>(null); const [lots,setLots]=useState<Lot[]>([]); const [error,setError]=useState("");
  async function loadProducts(){try{const rows=await api<Product[]>("/api/v1/inventory/products");setProducts(rows);if(selected)setSelected(rows.find(row=>row.uuid===selected.uuid)??null);setError("");}catch(reason){setError(reason instanceof Error?reason.message:"Could not load inventory");}}
  async function open(product:Product){setSelected(product);try{setLots(await api<Lot[]>(`/api/v1/inventory/products/${product.uuid}/lots`));}catch(reason){setError(reason instanceof Error?reason.message:"Could not load lots");}}
  useEffect(()=>{void loadProducts();},[]);
  async function createProduct(event:FormEvent<HTMLFormElement>){event.preventDefault();const form=event.currentTarget;const data=new FormData(form);try{await api("/api/v1/inventory/products",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:data.get("name"),ndc_number:data.get("ndc_number")||null,reorder_point:Number(data.get("reorder_point")||0),allow_combining:data.get("allow_combining")==="on"})});form.reset();await loadProducts();}catch(reason){setError(reason instanceof Error?reason.message:"Could not save product");}}
  async function createLot(event:FormEvent<HTMLFormElement>){event.preventDefault();if(!selected)return;const form=event.currentTarget;const data=new FormData(form);try{await api(`/api/v1/inventory/products/${selected.uuid}/lots`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({lot_number:data.get("lot_number")||null,expiration:data.get("expiration")||null,warehouse_id:data.get("warehouse_id"),manufacturer:data.get("manufacturer")||null,opening_quantity:Number(data.get("opening_quantity"))})});form.reset();await open(selected);await loadProducts();}catch(reason){setError(reason instanceof Error?reason.message:"Could not save lot");}}
  return <section className="inventory-workspace">
    <form className="card inventory-form" onSubmit={createProduct}>
      <div className="inventory-form-heading"><div><p className="eyebrow">CATÁLOGO</p><h2>Agregar producto</h2></div><p>Registra el producto y define el nivel mínimo que activará una alerta.</p></div>
      <div className="inventory-product-grid">
        <label className="inventory-product-name">Nombre del producto<input name="name" placeholder="Ej. Vacuna influenza" required maxLength={255}/></label>
        <label>NDC<input name="ndc_number" placeholder="Código NDC" maxLength={20}/></label>
        <label>Punto de reorden<input name="reorder_point" type="number" min="0" step="0.001" defaultValue="0"/></label>
        <label className="check inventory-combine"><input name="allow_combining" type="checkbox"/> Permitir combinar lotes</label>
      </div>
      <div className="inventory-form-actions"><button>Agregar producto</button></div>
    </form>
    {error&&<p className="error">{error}</p>}
    <div className={selected?"inventory-grid selected":"inventory-grid"}>
      <section className="card inventory-products">
        <div className="inventory-list-heading"><div><p className="eyebrow">EXISTENCIAS</p><h2>Productos</h2></div><span>{products.length}</span></div>
        <table><thead><tr><th>Producto</th><th>NDC</th><th>Disponible</th></tr></thead><tbody>{products.map(product=><tr key={product.uuid} onClick={()=>void open(product)} className="patient-row"><td><strong>{product.name}</strong><small>Punto de reorden: {product.reorder_point}</small></td><td>{product.ndc_number??"—"}</td><td className={product.on_hand<=Number(product.reorder_point)?"low-stock":""}>{product.on_hand}</td></tr>)}</tbody></table>
        {!products.length&&<div className="inventory-empty"><span aria-hidden="true">□</span><strong>No hay productos registrados</strong><p>Agrega un producto para comenzar el control de existencias.</p></div>}
      </section>
      {selected&&<section className="card inventory-detail">
        <div className="inventory-detail-heading"><div><p className="eyebrow">DETALLE DEL PRODUCTO</p><h2>{selected.name}</h2><p>{selected.ndc_number?`NDC ${selected.ndc_number}`:"Sin código NDC"} · {selected.on_hand} disponibles</p></div><button type="button" className="close" aria-label="Cerrar detalle" onClick={()=>setSelected(null)}>×</button></div>
        <form className="inventory-lot-form" onSubmit={createLot}><h3>Agregar lote y existencia inicial</h3><label>Número de lote<input name="lot_number" placeholder="Ej. LOT-2026-01"/></label><label>Caducidad<input name="expiration" type="date"/></label><label>Almacén<input name="warehouse_id" placeholder="Almacén" required/></label><label>Fabricante<input name="manufacturer" placeholder="Fabricante"/></label><label>Cantidad inicial<input name="opening_quantity" type="number" min="0" defaultValue="0" required/></label><button>Agregar lote</button></form>
        <div className="inventory-lots-heading"><h3>Lotes activos</h3><span>{lots.length}</span></div>
        <div className="inventory-lots">{lots.map(lot=><article className="lot-row" key={lot.uuid}><div><strong>{lot.lot_number??"Sin número de lote"}</strong><small>{lot.warehouse_id||"Almacén predeterminado"}{lot.manufacturer?` · ${lot.manufacturer}`:""}</small></div><span>{lot.on_hand} on hand</span><small>Caducidad: {lot.expiration??"No registrada"}</small></article>)}{!lots.length&&<p className="empty">No hay lotes activos para este producto.</p>}</div>
      </section>}
    </div>
  </section>;
}

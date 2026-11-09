"""Nexxora Business Brain: Fashion branch (staff app + customer tracking page).
Streamlit + Supabase. Works on phone and desktop (columns stack on narrow screens)."""
import html
import unicodedata
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Nexxora Fashion", page_icon="🧵", layout="wide")

URL, KEY = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"]
BIZ = st.secrets.get("BUSINESS_NAME", "B3")
APP_URL = st.secrets.get("APP_URL", "").rstrip("/")


# ---------------------------------------------------------------- tracking page
def fmt_date(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).strftime("%d %b %Y")
    except Exception:
        return "—"


def tracking(token: str):
    o = create_client(URL, KEY).rpc("get_order_tracking", {"p_token": token}).execute().data
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.caption(BIZ.upper())
        if not o:
            st.warning("We could not find this order. Please check your link.")
            return
        st.caption(f"Order {o['order_no']}")
        st.subheader(o["customer_name"])
        st.markdown(f"### {o['stage_label']}")
        st.progress(int(o["progress_pct"]) / 100, text=f"{int(o['progress_pct'])}% complete")
        a, b = st.columns(2)
        a.markdown(f"**Expected**  \n{fmt_date(o.get('expected_date'))}")
        b.markdown(f"**Last updated**  \n{fmt_date(o.get('last_updated'))}")
        steps = o.get("steps") or []
        if steps:
            st.markdown("**Progress**")
            for step in steps:
                when = f" · {fmt_date(step['at'])}" if step.get("at") else ""
                if step["state"] == "done":
                    st.write(f"✅ {step['label']}{when}")
                elif step["state"] == "current":
                    st.write(f"🟠 **{step['label']}**{when}  ← now")
                else:
                    st.write(f"⚪ {step['label']}")


# ---------------------------------------------------------------- helpers
def db():
    return st.session_state["sb"]


def rows(table, select="*", order=None, desc=True, limit=500):
    q = db().table(table).select(select)
    if order:
        q = q.order(order, desc=desc)
    return q.limit(limit).execute().data


def look(table, val, label):
    q = db().table(table).select(f"{val},{label}").order("position" if table == "stages" else label)
    return {r[val]: r[label] for r in q.execute().data}


def is_staff_role():
    return st.session_state.get("me", {}).get("role") == "staff"


def order_names():
    return {o["id"]: o["order_no"] for o in rows("my_orders", "id,order_no")}


LAB = {"reorder_level": "Low-stock alert at", "on_hand": "On hand",
       "delivery_impact_days": "Delivery impact (days)", "design_window": "Design window"}


def lab(c):
    return LAB.get(c, c.replace("_", " ").capitalize())


def F(col, label=None, kind="t", extra=None, default=None):
    return (col, label or lab(col), kind, extra, default)


def err(e):
    msg = getattr(e, "message", None) or str(e)
    low = msg.lower()
    if "foreign key" in low:
        msg = ("Other records still use this, so it cannot be deleted yet (for example orders, quick sales or "
               "client-owned fabric). Remove those first.")
    elif "receipt_no" in low and "duplicate" in low:
        msg = "That receipt number already exists. Leave it blank to generate a new one."
    st.error(msg)


def done(msg):
    st.session_state["flash"] = msg
    st.rerun()


def stage_info():
    """{stage_key: (position, label)}"""
    return {s["key"]: (s["position"], s["label"]) for s in rows("stages", order="position", desc=False)}


def window_of(stage, stored, info):
    """The design lock follows the order's stage: from Cutting onward it is LOCKED."""
    if stage in info and info[stage][0] >= info["cutting"][0]:
        return "locked"
    return "limited" if stored == "limited" else "open"


# kinds: t text, n number, d date, x long text, j key=value pairs, s select
CFG = {
    "orders": dict(title="Orders", order="created_at",
        sel="*, fashion_order_details(garment_type,fabric,style)",
        cols=["order_no", "customer_id", "garment_type", "fabric", "style", "due_date", "stage", "total_amount"],
        f=[F("customer_id", "Customer", "s", "customers:id:full_name"),
           F("offering_id", "Offering", "s", "offerings:id:name"),
           F("due_date", "Due date", "d"), F("total_amount", "Total price", "n"),
           F("stage", "Stage", "s", "stages:key:label", "order_received"),
           F("original_instructions", "Original instructions (paste WhatsApp text)", "x")],
        d=[F("garment_type", "Garment type"), F("fabric", "Fabric (text description)"), F("style"),
           F("modifications", kind="x"), F("special_requirements", kind="x")]),
    "customer_details": dict(title="Customer details"),
    "staff_page": dict(title="Staff"),
    "my_account": dict(title="My account"),
    "offerings": dict(title="Offerings", order="created_at", cols=["name", "base_price", "description"],
        f=[F("name"), F("base_price", "Base price", "n"), F("description", kind="x")]),
    "customers": dict(title="Customers", order="created_at", cols=["full_name", "phone", "whatsapp", "email"],
        f=[F("full_name", "Name"), F("phone"), F("whatsapp", "WhatsApp"), F("email"),
           F("address"), F("notes", kind="x")]),
    "fashion_order_details": dict(title="Design details", order=None, up=True, sel="*, orders(stage)",
        cols=["order_id", "garment_type", "fabric", "style", "modifications", "design_window"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"), F("garment_type"),
           F("fabric", "Fabric (text description)"), F("style"),
           F("modifications", kind="x"), F("special_requirements", kind="x"),
           F("change_window", "Change window (it locks by itself at Cutting)", "s", ["open", "limited"])]),
    "fashion_design_changes": dict(title="Design changes", order="created_at",
        cols=["order_id", "request", "extra_cost", "delivery_impact_days", "created_at"], f=[]),
    "fashion_qc": dict(title="Quality control", order="checked_at",
        cols=["order_id", "result", "notes", "checked_at"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"),
           F("result", kind="s", extra=["pass", "needs_correction"]), F("notes", kind="x")]),
    "fashion_fittings": dict(title="Fittings", order="created_at",
        cols=["order_id", "fitting_date", "notes", "adjustments"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"), F("fitting_date", "Fitting date", "d"),
           F("notes", kind="x"), F("adjustments", kind="x")]),
    "payments": dict(title="Payments received", order="paid_at",
        cols=["receipt_no", "order_id", "amount", "method", "paid_at"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"), F("amount", kind="n"),
           F("method", kind="s", extra=["cash", "transfer", "POS", "other"]),
           F("receipt_no", "Receipt number (leave blank to generate one)")]),
    "order_balances": dict(title="Balances", ro=True, order=None,
        cols=["order_no", "total_amount", "paid", "outstanding", "payment_status"]),
    "expenses": dict(title="Expenses", order="spent_on", cols=["category", "description", "amount", "spent_on"],
        f=[F("category"), F("description"), F("amount", kind="n"), F("spent_on", "Date", "d")]),
    "stock_levels": dict(title="Stock levels", ro=True, order=None,
        cols=["name", "kind", "ownership", "customer_id", "colour", "on_hand", "unit", "reorder_level", "status"],
        f=[F("customer_id", "Client", "s", "customers:id:full_name")]),
    "stock_in": dict(title="Stock in"),
    "stock_out": dict(title="Stock out"),
    "rtw_products": dict(title="RTW products", order="created_at", cols=["style_code", "name", "price"],
        f=[F("style_code", "Style code"), F("name"), F("price", kind="n"), F("description", kind="x")]),
    "rtw_variants": dict(title="SKUs / variants", order=None,
        cols=["sku", "tag_no", "product_id", "size", "colour", "price", "reorder_level"],
        f=[F("product_id", "Product", "s", "rtw_products:id:name"), F("sku", "SKU"),
           F("tag_no", "Tag number"), F("size"), F("colour"), F("price", kind="n"),
           F("reorder_level", "Low-stock level", "n")]),
    "rtw_levels": dict(title="RTW stock", ro=True, order=None,
        cols=["sku", "tag_no", "name", "size", "colour", "on_hand", "reorder_level"]),
    "rtw_movements": dict(title="RTW stock in", order="created_at",
        cols=["variant_id", "movement_type", "qty", "note", "created_at"],
        f=[F("variant_id", "SKU", "s", "rtw_variants:id:sku"),
           F("movement_type", "Type", "s", ["opening", "in", "return", "adjust_up", "adjust_down"]),
           F("qty", kind="n"), F("note")]),
    "quick_sales": dict(title="Quick sales", order="sold_at",
        cols=["sale_no", "sold_at", "total", "payment_method", "customer_id"],
        f=[F("customer_id", "Customer (optional)", "s", "customers:id:full_name"),
           F("payment_method", "Payment", "s", ["cash", "transfer", "POS", "other"]), F("note")]),
    "quick_sale_items": dict(title="Sale lines (add after creating the sale)", order=None,
        cols=["sale_id", "variant_id", "qty", "unit_price"],
        f=[F("sale_id", "Sale", "s", "quick_sales:id:sale_no"),
           F("variant_id", "SKU", "s", "rtw_variants:id:sku"), F("qty", kind="n"),
           F("unit_price", "Unit price (blank = list price)", "n")]),
    "work_updates": dict(title="Work updates", order="created_at", cols=["order_id", "kind", "note", "created_at"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"),
           F("kind", kind="s", extra=["started", "progress", "completed", "delayed"]), F("note", kind="x")]),
    "attendance": dict(title="Attendance", order="work_date", cols=["staff_id", "work_date", "note"],
        f=[F("staff_id", "Staff", "s", "profiles:id:full_name"), F("work_date", "Date", "d"), F("note")]),
    "communications": dict(title="Messages log", order="created_at",
        cols=["customer_id", "order_id", "channel", "body", "created_at"],
        f=[F("customer_id", "Customer", "s", "customers:id:full_name"),
           F("order_id", "Order", "s", "orders:id:order_no"),
           F("channel", default="whatsapp"), F("body", kind="x")]),
    "message_templates": dict(title="Message templates", order=None, cols=["stage_key", "title", "body"],
        f=[F("stage_key", "Stage", "s", "stages:key:label"), F("title"),
           F("body", "Body ({customer_name} {order_no} {due_date} {tracking_link})", "x")]),
}

NAV = {
    "Dashboard": None,
    "Orders": ["orders", "offerings"],
    "Customers": ["customer_details"],
    "Fashion": ["fashion_order_details", "fashion_design_changes", "fashion_qc", "fashion_fittings"],
    "Stock": ["stock_levels", "stock_in", "stock_out"],
    "Ready-to-wear": ["rtw_levels", "rtw_products", "rtw_variants", "rtw_movements", "quick_sales", "quick_sale_items"],
    "Money": ["payments", "order_balances", "expenses"],
    "Team": ["staff_page", "work_updates", "attendance", "communications", "message_templates"],
}

NAV_STAFF = {
    "My tasks": None,
    "Stock": ["stock_levels", "stock_out"],
    "My account": ["my_account"],
}


# ---------------------------------------------------------------- generic add + list
def widget(name, f, maps):
    col, label, kind, extra, default = f
    key = f"{name}_{col}"
    if kind == "n":
        return st.number_input(label, value=None, min_value=0.0, key=key)
    if kind == "d":
        return st.date_input(label, value=None, key=key)
    if kind == "x":
        return st.text_area(label, key=key)
    if kind == "s":
        opts = [None] + (list(maps[col]) if isinstance(extra, str) else list(extra))
        fmt = (lambda k: "—" if k is None else maps[col].get(k, k)) if isinstance(extra, str) \
            else (lambda k: "—" if k is None else k)
        return st.selectbox(label, opts, index=opts.index(default) if default in opts else 0,
                            format_func=fmt, key=key)
    return st.text_input(label, value=default or "", key=key,
                         placeholder="bust=36, waist=28" if kind == "j" else None)


def clean(f, v):
    kind = f[2]
    if v is None or v == "":
        return None
    if kind == "n":
        return int(v) if float(v).is_integer() else float(v)
    if kind == "d":
        return v.isoformat()
    if kind == "j":
        out = {}
        for part in v.split(","):
            if "=" in part:
                k, x = [s.strip() for s in part.split("=", 1)]
                out[k] = float(x) if x.replace(".", "", 1).isdigit() else x
        return out
    return v


def order_labels_with_balance():
    sym = currency()
    bal = {b["order_id"]: b for b in rows("order_balances")}
    out = {}
    for o in rows("orders", "id,order_no,customers(full_name)", order="created_at"):
        owing = float(bal.get(o["id"], {}).get("outstanding") or 0)
        out[o["id"]] = f"{o['order_no']} — {o['customers']['full_name']} — balance {sym}{owing:,.0f}"
    return out


def add_form(name):
    c = CFG[name]
    fields = c["f"] + c.get("d", [])
    maps = {f[0]: look(*f[3].split(":")) for f in fields if f[2] == "s" and isinstance(f[3], str)}
    if name == "payments":
        maps["order_id"] = order_labels_with_balance()
    with st.expander(f"➕ Add — {c['title']}"):
        with st.form(f"add_{name}", clear_on_submit=True):
            grid = st.columns(2)
            vals = {}
            for i, f in enumerate(fields):
                with grid[i % 2]:
                    vals[f[0]] = widget(name, f, maps)
            if st.form_submit_button("Save", type="primary"):
                rec = {f[0]: clean(f, vals[f[0]]) for f in c["f"]}
                rec = {k: v for k, v in rec.items() if v is not None}
                det = {f[0]: clean(f, vals[f[0]]) for f in c.get("d", [])}
                det = {k: v for k, v in det.items() if v is not None}
                try:
                    msg, before = "Saved", None
                    if name == "payments" and rec.get("order_id"):
                        before = db().table("orders").select("order_no,stage").eq("id", rec["order_id"]).execute().data
                    t = db().table(name)
                    res = (t.upsert(rec) if c.get("up") else t.insert(rec)).execute()
                    if before:
                        after = db().table("orders").select("order_no,stage").eq("id", rec["order_id"]).execute().data
                        if before[0]["stage"] == "order_received" and after and after[0]["stage"] == "payment_confirmed":
                            msg = f"Payment saved. {after[0]['order_no']} moved to Payment Confirmed automatically."
                    if name == "payments" and res.data:
                        st.session_state["receipt_sel"] = res.data[0]["id"]
                        msg += f" Receipt {res.data[0].get('receipt_no') or ''} is ready to download below."
                    if det:  # order details (garment, fabric, style...) go to the design details record
                        db().table("fashion_order_details").upsert({"order_id": res.data[0]["id"], **det}).execute()
                    done(msg)
                except Exception as e:  # database rules show here, e.g. a refused change
                    err(e)


def list_view(name):
    c = CFG[name]
    maps = {f[0]: look(*f[3].split(":")) for f in c.get("f", []) if f[2] == "s" and isinstance(f[3], str)}
    data = rows(name, select=c.get("sel", "*"), order=c.get("order"))
    if not data:
        st.info("Nothing here yet.")
        return
    if name == "orders":
        for r in data:
            det = r.pop("fashion_order_details", None)
            det = det[0] if isinstance(det, list) and det else det
            r.update(det or {})
    if name == "fashion_order_details":
        info = stage_info()
        for r in data:
            stg = (r.pop("orders", None) or {}).get("stage")
            w = window_of(stg, r.get("change_window"), info)
            r["design_window"] = f"LOCKED (at {info[stg][1]})" if w == "locked" else w
    if name == "stock_levels":
        for r in data:
            r["status"] = "LOW" if float(r["on_hand"]) <= float(r["reorder_level"]) else "OK"
    df = pd.DataFrame(data)
    for col, m in maps.items():
        if col in df:
            df[col] = df[col].map(m).fillna(df[col])
    for col in df.columns:
        if col.endswith("_at") or col in ("fitting_date",):
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%d %b %Y")
    show = [x for x in c["cols"] if x in df]
    st.dataframe(df[show].rename(columns=lab), width="stretch", hide_index=True)


def table_view(name):
    if name == "orders":
        order_form()
    elif not CFG[name].get("ro"):
        add_form(name)
    if name == "payments":
        st.caption("Recording a payment on an order that is at Order Received moves it to Payment Confirmed "
                   "automatically. Nothing else moves by itself.")
        receipt_section()
    if name == "stock_levels":
        st.caption("**Low-stock alert at** is the level that warns you: when the yards on hand fall to this "
                   "number or below, the item shows LOW and appears on the dashboard. "
                   "It is not an amount you take out; use the Stock out tab for that.")
    list_view(name)
    if name == "orders":
        order_edit()


# ---------------------------------------------------------------- design changes (locks at Cutting)
def design_changes():
    info = stage_info()
    orders = rows("orders", "id,order_no,stage,customers(full_name)", order="created_at")
    pick = st.selectbox("Choose the order", [None] + orders,
                        format_func=lambda o: "—" if o is None else f"{o['order_no']} — {o['customers']['full_name']}")
    if pick:
        pos, label = info[pick["stage"]]
        if pos >= info["cutting"][0]:
            st.error(f"🔒 {pick['order_no']} is at the **{label}** stage. The design is LOCKED, "
                     "so no design changes are accepted.")
        else:
            st.success(f"{pick['order_no']} is at **{label}**. Design changes are still allowed.")
            with st.form("design_change", clear_on_submit=True):
                req = st.text_area("What does the customer want changed?")
                a, b = st.columns(2)
                cost = a.number_input("Extra cost", value=None, min_value=0.0)
                days = b.number_input("Delivery impact (days)", value=None, min_value=0.0)
                if st.form_submit_button("Save change request", type="primary"):
                    if not req.strip():
                        st.error("Describe the change first.")
                    else:
                        rec = {"order_id": pick["id"], "request": req.strip()}
                        if cost:
                            rec["extra_cost"] = cost
                        if days:
                            rec["delivery_impact_days"] = int(days)
                        try:
                            db().table("fashion_design_changes").insert(rec).execute()
                            done("Change request saved")
                        except Exception as e:
                            err(e)
    st.markdown("**All design change requests**")
    list_view("fashion_design_changes")


# ---------------------------------------------------------------- stock in / out
def movement_history(types):
    items = look("stock_items", "id", "name")
    orders = order_names()
    data = (db().table("stock_movements").select("*").in_("movement_type", types)
            .order("created_at", desc=True).limit(200).execute().data)
    if not data:
        st.info("Nothing recorded yet.")
        return
    df = pd.DataFrame(data)
    df["item"] = df["item_id"].map(items)
    df["order"] = df["order_id"].map(orders)
    df["date"] = pd.to_datetime(df["created_at"]).dt.strftime("%d %b %Y")
    st.dataframe(df[["item", "movement_type", "qty", "order", "note", "date"]].rename(columns=lab),
                 width="stretch", hide_index=True)


def stock_in():
    items = rows("stock_levels")
    clients = look("customers", "id", "full_name")
    orders = order_names()
    with st.expander("➕ Record stock in", expanded=True):
        with st.form("stock_in", clear_on_submit=True):
            item = st.selectbox("Existing item", [None] + items, format_func=lambda i: "— new item: fill the details below —"
                                if i is None else f"{i['name']} ({i['ownership']}) · {i['on_hand']} {i['unit']} on hand")
            st.caption("Adding to an item you already have? Choose it above and skip the new-item details.")
            a, b = st.columns(2)
            name = a.text_input("New item name")
            kind = b.selectbox("Kind", ["fabric", "material"])
            owner = a.selectbox("Ownership", ["shop", "client"])
            client = b.selectbox("Client (only if client-owned)", [None] + list(clients),
                                 format_func=lambda k: "—" if k is None else clients[k])
            colour = a.text_input("Colour")
            unit = b.text_input("Unit (materials only; fabric is always yards)", value="yards")
            alert = a.number_input("Low-stock alert at (warn me when on hand is this or less)", value=None, min_value=0.0)
            st.divider()
            qty = a.number_input("Quantity (yards for fabric)", value=None, min_value=0.0)
            mtype = b.selectbox("Type", ["Opening stock", "Received / purchased", "Adjustment (add)"])
            order = a.selectbox("For order (optional)", [None] + list(orders),
                                format_func=lambda k: "—" if k is None else orders[k])
            note = b.text_input("Note")
            go = st.form_submit_button("Save stock in", type="primary")
        if go:
            problem = None
            if not qty or qty <= 0:
                problem = "Enter a quantity above zero."
            elif not item and not name.strip():
                problem = "Choose an existing item, or type the new item's name."
            elif not item and owner == "client" and not client:
                problem = "Client-owned stock needs the client's name."
            if problem:
                st.error(problem)
            else:
                try:
                    if item:
                        iid = item["item_id"]
                    else:
                        rec = {"name": name.strip(), "kind": kind, "ownership": owner,
                               "unit": "yards" if kind == "fabric" else (unit.strip() or "pcs")}
                        if owner == "client":
                            rec["customer_id"] = client
                        if colour.strip():
                            rec["colour"] = colour.strip()
                        if alert:
                            rec["reorder_level"] = alert
                        iid = db().table("stock_items").insert(rec).execute().data[0]["id"]
                    mv = {"item_id": iid, "qty": qty,
                          "movement_type": {"Opening stock": "opening", "Received / purchased": "in",
                                            "Adjustment (add)": "adjust_up"}[mtype]}
                    if order:
                        mv["order_id"] = order
                    if note.strip():
                        mv["note"] = note.strip()
                    db().table("stock_movements").insert(mv).execute()
                    done("Stock in saved")
                except Exception as e:
                    err(e)
    st.markdown("**Stock in history**")
    movement_history(["opening", "in", "adjust_up"])


def stock_out():
    items = [i for i in rows("stock_levels") if float(i["on_hand"]) > 0]
    orders = order_names()
    with st.expander("➖ Record stock out", expanded=True):
        if not items:
            st.info("Nothing in stock yet. Record stock in first.")
        with st.form("stock_out", clear_on_submit=True):
            item = st.selectbox("Item", [None] + items, format_func=lambda i: "—" if i is None else
                                f"{i['name']} ({i['ownership']}) · {i['on_hand']} {i['unit']} available")
            a, b = st.columns(2)
            qty = a.number_input("Quantity taken out (yards for fabric)", value=None, min_value=0.0)
            reason = b.selectbox("Reason", ["Pulled for use"] if is_staff_role()
                                 else ["Pulled for use", "Adjustment (damaged / lost)"])
            order = a.selectbox("For order (optional)", [None] + list(orders),
                                format_func=lambda k: "—" if k is None else orders[k])
            note = b.text_input("Note")
            go = st.form_submit_button("Save stock out", type="primary")
        if go:
            if not item or not qty or qty <= 0:
                st.error("Choose the item and enter a quantity above zero.")
            else:
                mv = {"item_id": item["item_id"], "qty": qty,
                      "movement_type": "out" if reason == "Pulled for use" else "adjust_down"}
                if order:
                    mv["order_id"] = order
                if note.strip():
                    mv["note"] = note.strip()
                try:
                    db().table("stock_movements").insert(mv).execute()
                    done("Stock out saved. Stock levels are updated.")
                except Exception as e:
                    err(e)
    st.markdown("**Stock out history**")
    movement_history(["out", "adjust_down"])


# ---------------------------------------------------------------- receipts
def ascii_safe(t):
    """The PDF's built-in font handles plain Latin letters only, so accents are simplified."""
    t = unicodedata.normalize("NFKD", str(t or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return t.encode("latin-1", "replace").decode("latin-1")


def receipt_pdf(r):
    from fpdf import FPDF
    pdf = FPDF(format="A5")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    w = pdf.w - 2 * pdf.l_margin
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(w, 12, ascii_safe(BIZ), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(w, 6, "PAYMENT RECEIPT", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + w, pdf.get_y())
    pdf.ln(5)

    def pair(label, value, bold=False):
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(110, 110, 110)
        pdf.cell(w * 0.42, 8, ascii_safe(label))
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B" if bold else "", 11)
        pdf.cell(w * 0.58, 8, ascii_safe(value), align="R", new_x="LMARGIN", new_y="NEXT")

    pair("Receipt number", r["receipt_no"], bold=True)
    pair("Date", r["date"])
    pair("Order", r["order_no"])
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(w, 6, "Received from", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(w, 9, ascii_safe(r["customer"]), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(w, 7, "  Amount received", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(w, 14, ascii_safe(f"{r['code']} {r['amount']:,.2f}"), fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pair("Payment method", (r["method"] or "-").capitalize())
    pair("Order total", f"{r['code']} {r['total']:,.2f}")
    pair("Paid to date", f"{r['code']} {r['paid_to_date']:,.2f}")
    pair("Balance", f"{r['code']} {r['balance']:,.2f}", bold=True)
    if r.get("received_by"):
        pair("Received by", r["received_by"])
    pdf.set_y(pdf.h - 28)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + w, pdf.get_y())
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(w, 5, "Thank you for your patronage.", align="C")
    return bytes(pdf.output())


def receipt_section():
    pays = rows("payments", "id,receipt_no,amount,method,paid_at,order_id,received_by,"
                            "orders(order_no,total_amount,customers(full_name))", order="paid_at")
    if not pays:
        return
    code, sym = currency_code(), currency()
    staff = look("profiles", "id", "full_name")
    ids = [p["id"] for p in pays]
    if st.session_state.get("receipt_sel") not in ids:
        st.session_state["receipt_sel"] = ids[0]
    st.markdown("#### 🧾 Receipt")
    pick = st.selectbox("Choose a payment", ids, key="receipt_sel", format_func=lambda i: next(
        f"{p['receipt_no']} — {p['orders']['customers']['full_name']} — {sym}{float(p['amount']):,.0f} — {p['paid_at'][:10]}"
        for p in pays if p["id"] == i))
    p = next(x for x in pays if x["id"] == pick)
    so_far = sum(float(x["amount"]) for x in pays if x["order_id"] == p["order_id"] and x["paid_at"] <= p["paid_at"])
    total = float(p["orders"]["total_amount"] or 0)
    pdf = receipt_pdf({
        "receipt_no": p["receipt_no"], "date": datetime.fromisoformat(p["paid_at"].replace("Z", "+00:00")).strftime("%d %b %Y"),
        "order_no": p["orders"]["order_no"], "customer": p["orders"]["customers"]["full_name"],
        "amount": float(p["amount"]), "method": p.get("method"), "code": code, "total": total,
        "paid_to_date": so_far, "balance": max(total - so_far, 0), "received_by": staff.get(p.get("received_by"))})
    st.download_button("⬇ Download receipt (PDF)", data=pdf, file_name=f"{p['receipt_no']}.pdf",
                       mime="application/pdf", type="primary")


# ---------------------------------------------------------------- new order (new or existing customer)
def order_form():
    customers = look("customers", "id", "full_name")
    offerings = look("offerings", "id", "name")
    stages = look("stages", "key", "label")
    keys = list(stages)
    with st.expander("➕ New order"):
        with st.form("add_orders", clear_on_submit=True):
            a, b = st.columns(2)
            cust = a.selectbox("Existing customer", [None] + list(customers),
                               format_func=lambda k: "—" if k is None else customers[k])
            newname = b.text_input("…or a NEW customer's name")
            phone = a.text_input("New customer's phone / WhatsApp (optional)")
            offering = b.selectbox("Offering", [None] + list(offerings),
                                   format_func=lambda k: "—" if k is None else offerings[k])
            due = a.date_input("Due date", value=None)
            total = b.number_input("Total price", value=None, min_value=0.0)
            stage = "order_received"  # every order starts here; recording a payment moves it on
            a.caption("New orders start at **Order Received** and move on automatically once a payment is recorded.")
            instr = st.text_area("Original instructions (paste WhatsApp text)")
            st.markdown("**Design details**")
            c, d = st.columns(2)
            garment = c.text_input("Garment type")
            fabric = d.text_input("Fabric (text description)")
            style = c.text_input("Style")
            mods = d.text_area("Modifications")
            special = st.text_area("Special requirements")
            go = st.form_submit_button("Save order", type="primary")
        if go:
            problem = None
            if cust and newname.strip():
                problem = "Choose an existing customer OR type a new name, not both."
            elif not cust and not newname.strip():
                problem = "Choose a customer, or type a new customer's name."
            if problem:
                st.error(problem)
            else:
                try:
                    cid, added = cust, False
                    if not cid:
                        rec = {"full_name": newname.strip()}
                        if phone.strip():
                            rec["phone"] = phone.strip()
                            rec["whatsapp"] = phone.strip()
                        cid = db().table("customers").insert(rec).execute().data[0]["id"]
                        added = True
                    order_no = db().rpc("make_order_no", {"p_customer": cid, "p_garment": garment.strip(),
                                                          "p_date": date.today().isoformat()}).execute().data
                    order = {"customer_id": cid, "stage": stage, "order_no": order_no}
                    if offering:
                        order["offering_id"] = offering
                    if due:
                        order["due_date"] = due.isoformat()
                    if total:
                        order["total_amount"] = total
                    if instr.strip():
                        order["original_instructions"] = instr.strip()
                    res = db().table("orders").insert(order).execute()
                    det = {k: v.strip() for k, v in [("garment_type", garment), ("fabric", fabric), ("style", style),
                                                     ("modifications", mods), ("special_requirements", special)]
                           if v and v.strip()}
                    if det:
                        db().table("fashion_order_details").upsert({"order_id": res.data[0]["id"], **det}).execute()
                    done("Order saved" + (" and the new customer was added." if added else "."))
                except Exception as e:
                    err(e)


# ---------------------------------------------------------------- customer details (profile + measurements per attire)
MEAS = ["Neck", "Shoulder", "Chest / Bust", "Waist", "Hip", "Sleeve length", "Round sleeve", "Armhole",
        "Top length", "Trouser / skirt length", "Thigh", "Knee", "Ankle / bottom", "Inseam"]


def customer_details():
    add_form("customers")
    custs = rows("customers", "id,full_name,phone,whatsapp,email,address,notes", order="full_name", desc=False)
    if not custs:
        st.info("No customers yet. Add the first one above.")
        return
    q = st.text_input("Search customers", placeholder="Name or phone").strip().lower()
    shown = [c for c in custs if q in f"{c['full_name']} {c['phone'] or ''}".lower()] if q else custs
    if not shown:
        st.info("No customer matches that search.")
        return
    pick = st.selectbox("Customer", shown, format_func=lambda c: c["full_name"] + (f" · {c['phone']}" if c["phone"] else ""))
    st.subheader(pick["full_name"])
    bits = [x for x in [pick.get("phone"), pick.get("whatsapp"), pick.get("email"), pick.get("address")] if x]
    if bits:
        st.caption("  ·  ".join(dict.fromkeys(bits)))
    if pick.get("notes"):
        st.write(pick["notes"])

    st.markdown("### Measurements")
    sets = (db().table("fashion_measurements").select("*").eq("customer_id", pick["id"])
            .order("taken_at", desc=True).execute().data)
    for m in sets:
        title = f"{m.get('attire') or 'Measurements'} · {m['taken_at']} · {m['unit']}"
        with st.expander(title):
            vals = m.get("measurement_values") or {}
            if vals:
                st.dataframe(pd.DataFrame(list(vals.items()), columns=["Measurement", m["unit"]]),
                             width="stretch", hide_index=True)
            if m.get("note"):
                st.caption(m["note"])
    if not sets:
        st.info("No measurements yet. Add the first set below.")
    label = "➕ Add new measurements (another attire)" if sets else "➕ Add first measurements"
    with st.expander(label, expanded=not sets):
        with st.form(f"meas_{pick['id']}", clear_on_submit=True):
            a, b = st.columns(2)
            attire = a.text_input("Attire / garment (e.g. Agbada, Gown, Suit)")
            unit = b.selectbox("Unit", ["inches", "cm"])
            table = pd.DataFrame({"Measurement": MEAS, "Value": pd.Series([None] * len(MEAS), dtype="float64")})
            edited = st.data_editor(table, num_rows="dynamic", hide_index=True, width="stretch",
                                    column_config={"Value": st.column_config.NumberColumn(min_value=0.0, step=0.1)},
                                    key=f"ed_{pick['id']}_{len(sets)}")
            st.caption("Fill only what this attire needs. Add your own rows at the bottom of the table.")
            note = st.text_input("Note")
            go = st.form_submit_button("Save measurements", type="primary")
        if go:
            vals = {}
            for _, r in edited.iterrows():
                name, v = r["Measurement"], r["Value"]
                if name and str(name).strip() and pd.notna(v):
                    vals[str(name).strip()] = int(v) if float(v).is_integer() else float(v)
            if not vals:
                st.error("Enter at least one measurement.")
            else:
                rec = {"customer_id": pick["id"], "unit": unit, "measurement_values": vals}
                if attire.strip():
                    rec["attire"] = attire.strip()
                if note.strip():
                    rec["note"] = note.strip()
                try:
                    db().table("fashion_measurements").insert(rec).execute()
                    done("Measurements saved")
                except Exception as e:
                    err(e)

    st.markdown("### Orders")
    sym = currency()
    stage_names = look("stages", "key", "label")
    orders = (db().table("orders").select("id,order_no,stage,due_date,total_amount").eq("customer_id", pick["id"])
              .order("created_at", desc=True).execute().data)
    if orders:
        paid_by = {b["order_id"]: float(b["paid"] or 0) for b in
                   db().table("order_balances").select("order_id,paid")
                   .in_("order_id", [o["id"] for o in orders]).execute().data}
        df = pd.DataFrame(orders)
        df["paid"] = df["id"].map(paid_by).fillna(0)
        df["balance"] = (df["total_amount"].astype(float) - df["paid"]).clip(lower=0)
        st.caption(f"Billed {sym}{df['total_amount'].astype(float).sum():,.0f} · Paid {sym}{df['paid'].sum():,.0f} "
                   f"· Outstanding {sym}{df['balance'].sum():,.0f}")
        df["stage"] = df["stage"].map(stage_names)
        st.dataframe(df[["order_no", "stage", "due_date", "total_amount", "paid", "balance"]].rename(columns=lab),
                     width="stretch", hide_index=True)
    else:
        st.caption("No orders yet for this customer.")

    with st.expander("🗑 Delete this customer"):
        n = len(orders)
        st.warning(f"Deleting {pick['full_name']} removes the customer, their contact details and all their measurements. "
                   + ("They have no orders. " if not n else
                      f"They have {n} order(s), which must be deleted first. ") + "This cannot be undone.")
        with_orders = False
        if n:
            with_orders = st.checkbox(f"Also delete their {n} order(s), including each order's payments and records",
                                      key=f"delcust_orders_{pick['id']}")
        typed = st.text_input("Type the customer's full name to confirm", key=f"delcust_{pick['id']}")
        if st.button("Delete customer", type="primary", key=f"delcustbtn_{pick['id']}"):
            if typed.strip().lower() != pick["full_name"].strip().lower():
                st.error("The name you typed doesn't match.")
            elif n and not with_orders:
                st.error("Tick the box to delete their orders too, or delete those orders first under Orders.")
            else:
                try:
                    if n:
                        db().table("orders").delete().eq("customer_id", pick["id"]).execute()
                    gone = db().table("customers").delete().eq("id", pick["id"]).execute().data
                    if gone:
                        done(f"{pick['full_name']} deleted.")
                    else:
                        st.error("Only an owner or manager can delete customers.")
                except Exception as e:
                    err(e)


# ---------------------------------------------------------------- edit or delete an order
def order_edit():
    sym = currency()
    orders = rows("orders", "id,order_no,customer_id,offering_id,due_date,total_amount,original_instructions,"
                            "customers(full_name),fashion_order_details(garment_type,fabric,style,modifications,"
                            "special_requirements)", order="created_at")
    if not orders:
        return
    customers = look("customers", "id", "full_name")
    offerings = look("offerings", "id", "name")
    st.divider()
    st.markdown("### ✏️ Edit or delete an order")
    pick = st.selectbox("Choose the order", [None] + orders, key="edit_pick",
                        format_func=lambda o: "—" if o is None else
                        f"{o['order_no']} — {o['customers']['full_name']} — {sym}{float(o['total_amount'] or 0):,.0f}")
    if not pick:
        return
    det = pick.get("fashion_order_details")
    det = det[0] if isinstance(det, list) and det else (det or {})
    cust_keys = list(customers)
    off_keys = [None] + list(offerings)
    with st.form(f"edit_order_{pick['id']}"):
        a, b = st.columns(2)
        cust = a.selectbox("Customer", cust_keys, format_func=lambda k: customers[k],
                           index=cust_keys.index(pick.get("customer_id")) if pick.get("customer_id") in cust_keys else 0)
        offering = b.selectbox("Offering", off_keys, format_func=lambda k: "—" if k is None else offerings[k],
                               index=off_keys.index(pick.get("offering_id")) if pick.get("offering_id") in off_keys else 0)
        due = a.date_input("Due date", value=date.fromisoformat(pick["due_date"]) if pick.get("due_date") else None)
        total = b.number_input("Total price", min_value=0.0,
                               value=float(pick["total_amount"]) if pick["total_amount"] is not None else None)
        instr = st.text_area("Original instructions", value=pick.get("original_instructions") or "")
        st.markdown("**Design details**")
        c, d = st.columns(2)
        garment = c.text_input("Garment type", value=det.get("garment_type") or "")
        fabric = d.text_input("Fabric (text description)", value=det.get("fabric") or "")
        style = c.text_input("Style", value=det.get("style") or "")
        mods = d.text_area("Modifications", value=det.get("modifications") or "")
        special = st.text_area("Special requirements", value=det.get("special_requirements") or "")
        save = st.form_submit_button("Save changes", type="primary")
    if save:
        try:
            db().table("orders").update({
                "customer_id": cust, "offering_id": offering,
                "due_date": due.isoformat() if due else None,
                "total_amount": float(total) if total is not None else 0,
                "original_instructions": instr.strip() or None}).eq("id", pick["id"]).execute()
            db().table("fashion_order_details").upsert({
                "order_id": pick["id"], "garment_type": garment.strip() or None, "fabric": fabric.strip() or None,
                "style": style.strip() or None, "modifications": mods.strip() or None,
                "special_requirements": special.strip() or None}).execute()
            done(f"{pick['order_no']} updated")
        except Exception as e:
            err(e)

    with st.expander("👷 Assigned staff"):
        people = [p for p in rows("profiles", "id,full_name,responsibility,active", order="full_name", desc=False)
                  if p["active"]]
        names = {p["id"]: p["full_name"] + (f" · {p['responsibility']}" if p.get("responsibility") else "")
                 for p in people}
        current = [a["staff_id"] for a in db().table("order_assignments").select("staff_id")
                   .eq("order_id", pick["id"]).execute().data]
        chosen = st.multiselect("Staff working on this order", list(names), default=[c for c in current if c in names],
                                format_func=lambda k: names[k], key=f"assign_{pick['id']}")
        if st.button("Save assignment", key=f"assignbtn_{pick['id']}"):
            try:
                db().table("order_assignments").delete().eq("order_id", pick["id"]).execute()
                if chosen:
                    db().table("order_assignments").insert(
                        [{"order_id": pick["id"], "staff_id": k} for k in chosen]).execute()
                done("Assignment saved")
            except Exception as e:
                err(e)

    with st.expander("🗑 Delete this order"):
        pays = db().table("payments").select("amount").eq("order_id", pick["id"]).execute().data
        paid = sum(float(p["amount"]) for p in pays)
        st.warning(
            f"Deleting {pick['order_no']} removes the order and everything attached to it: its design details, "
            "quality control, fittings, work updates, status history and recorded payments"
            + (f" ({len(pays)} payment(s), {sym}{paid:,.0f} in total)" if pays else "") +
            ". The customer and their measurements stay exactly as they are. This cannot be undone.")
        typed = st.text_input("Type the order number to confirm", key=f"del_{pick['id']}")
        if st.button("Delete order", type="primary", key=f"delbtn_{pick['id']}"):
            if typed.strip().upper() != pick["order_no"].upper():
                st.error("The order number you typed doesn't match.")
            else:
                try:
                    gone = db().table("orders").delete().eq("id", pick["id"]).execute().data
                    if gone:
                        done(f"{pick['order_no']} deleted. The customer is unchanged.")
                    else:
                        st.error("Only an owner or manager can delete orders.")
                except Exception as e:
                    err(e)


# ---------------------------------------------------------------- staff, my account, my tasks
RESPS = ["Cutter", "Tailor", "Fitter", "Quality control", "Sales / front desk", "Stock keeper", "Other"]
ROLE_LABEL = {"owner": "Owner", "manager": "Manager", "staff": "General staff"}


def password_box(key):
    with st.expander("🔑 Change my password"):
        with st.form(f"pw_{key}", clear_on_submit=True):
            p1 = st.text_input("New password", type="password")
            p2 = st.text_input("Repeat new password", type="password")
            go = st.form_submit_button("Change password", type="primary")
        if go:
            if len(p1) < 8:
                st.error("Use at least 8 characters.")
            elif p1 != p2:
                st.error("The two passwords don't match.")
            else:
                try:
                    db().auth.update_user({"password": p1})
                    st.success("Password changed.")
                except Exception as e:
                    err(e)


def my_account():
    me = st.session_state["me"]
    st.subheader(me["full_name"])
    st.caption(ROLE_LABEL.get(me["role"], me["role"]) + (f" · {me['responsibility']}" if me.get("responsibility") else ""))
    password_box("account")


def staff_page():
    me = st.session_state["me"]
    owner = me["role"] == "owner"
    people = rows("profiles", "id,full_name,phone,role,responsibility,active", order="full_name", desc=False)
    with st.expander("➕ Add staff"):
        with st.form("add_staff", clear_on_submit=True):
            a, b = st.columns(2)
            name = a.text_input("Full name")
            email = b.text_input("Email (this is their login)")
            pw = a.text_input("Temporary password (at least 8 characters)", type="password")
            phone = b.text_input("Phone")
            role = a.selectbox("Access level", ["staff", "manager", "owner"] if owner else ["staff"],
                               format_func=lambda r: ROLE_LABEL[r])
            resp = b.selectbox("Responsibility", RESPS)
            go = st.form_submit_button("Create login", type="primary")
        st.caption("Give them the email and temporary password privately, and ask them to change it under My account.")
        if go:
            if not name.strip() or "@" not in email or len(pw) < 8:
                st.error("Enter the name, a valid email and a password of at least 8 characters.")
            else:
                try:
                    user = create_client(URL, KEY).auth.sign_up({"email": email.strip(), "password": pw}).user
                    ids = getattr(user, "identities", None)
                    if not user or not getattr(user, "id", None) or (ids is not None and len(ids) == 0):
                        st.error("That email already has a login. Ask an owner to fix it in Supabase.")
                    else:
                        rec = {"id": user.id, "full_name": name.strip(), "role": role, "responsibility": resp}
                        if phone.strip():
                            rec["phone"] = phone.strip()
                        db().table("profiles").insert(rec).execute()
                        done(f"{name.strip()} added. If they cannot sign in, check that 'Confirm email' is switched "
                             "off in Supabase under Authentication.")
                except Exception as e:
                    err(e)
    if not people:
        return
    df = pd.DataFrame(people)
    df["role"] = df["role"].map(ROLE_LABEL)
    df["active"] = df["active"].map({True: "Active", False: "Switched off"})
    st.dataframe(df[["full_name", "role", "responsibility", "phone", "active"]].rename(columns=lab),
                 width="stretch", hide_index=True)
    st.markdown("### Edit a staff member")
    pick = st.selectbox("Choose", people, format_func=lambda p: p["full_name"], key="staff_pick")
    resp_opts = RESPS + ([pick["responsibility"]] if pick.get("responsibility") and pick["responsibility"] not in RESPS else [])
    with st.form(f"edit_staff_{pick['id']}"):
        a, b = st.columns(2)
        name = a.text_input("Full name", value=pick["full_name"])
        phone = b.text_input("Phone", value=pick.get("phone") or "")
        resp = a.selectbox("Responsibility", resp_opts,
                           index=resp_opts.index(pick["responsibility"]) if pick.get("responsibility") in resp_opts else 0)
        roles = ["staff", "manager", "owner"]
        role = b.selectbox("Access level", roles, index=roles.index(pick["role"]), disabled=not owner,
                           format_func=lambda r: ROLE_LABEL[r])
        active = st.checkbox("Account is active (untick to switch this person off)", value=pick["active"])
        save = st.form_submit_button("Save changes", type="primary")
    if save:
        try:
            upd = {"full_name": name.strip(), "phone": phone.strip() or None, "responsibility": resp, "active": active}
            if owner:
                upd["role"] = role
            gone = db().table("profiles").update(upd).eq("id", pick["id"]).execute().data
            if gone:
                done(f"{name.strip()} updated")
            else:
                st.error("You do not have permission to change this person.")
        except Exception as e:
            err(e)
    with st.expander("🗑 Delete this person"):
        if not owner:
            st.info("Only an owner can delete staff. To stop someone using the app, untick Account is active above.")
        elif pick["id"] == me.get("id"):
            st.info("You cannot delete your own account.")
        else:
            st.warning(f"Deleting {pick['full_name']} removes their login, their profile, their task assignments and "
                       "their attendance records. Orders and everything they recorded stay. This cannot be undone. "
                       "If they have simply left the business, untick Account is active above instead.")
            typed = st.text_input("Type their full name to confirm", key=f"delstaff_{pick['id']}")
            if st.button("Delete this person", type="primary", key=f"delstaffbtn_{pick['id']}"):
                if typed.strip().lower() != pick["full_name"].strip().lower():
                    st.error("The name you typed doesn't match.")
                else:
                    try:
                        db().rpc("delete_staff", {"p_id": pick["id"]}).execute()
                        done(f"{pick['full_name']} deleted.")
                    except Exception as e:
                        err(e)
    password_box("staffpage")


def task_card_html(o, pct, color, lock):
    due = f"Due {o['due_date']}" if o.get("due_date") else "No due date"
    look_ = " · ".join(x for x in [o.get("fabric"), o.get("style")] if x) or "—"
    return (f'<div class="oc"><div class="id">{html.escape(o["order_no"])}</div>'
            f'<div class="row"><span>👤 {html.escape(o["customer"])}</span></div>'
            f'<div class="row sub"><span>🧵 {html.escape(o.get("garment_type") or "—")}</span></div>'
            f'<div class="row sub"><span>{html.escape(look_)}</span></div>'
            f'<div class="row sub"><span>📅 {due}</span><span>{lock}</span></div>'
            f'<div class="bar"><span style="width:{pct}%;background:{color}"></span></div></div>')


def staff_move(order_id, stage):
    try:
        db().rpc("staff_set_stage", {"p_order": order_id, "p_stage": stage}).execute()
        st.rerun()
    except Exception as e:
        err(e)


def my_tasks():
    stages = rows("stages", order="position", desc=False)
    keys = [s["key"] for s in stages]
    pos = {s["key"]: s["position"] for s in stages}
    orders = [o for o in rows("my_orders") if o["stage"] != keys[-1]]
    if not orders:
        st.info("No orders are assigned to you right now.")
        return
    meas = rows("my_measurements")
    live = [s for s in stages if any(o["stage"] == s["key"] for o in orders)]
    for r in range(0, len(live), 4):
        chunk = live[r:r + 4]
        cols = st.columns(4)
        for col, s in zip(cols, chunk):
            here = [o for o in orders if o["stage"] == s["key"]]
            color = COLORS[(s["position"] - 1) % len(COLORS)]
            with col:
                st.markdown(f'<div class="coltitle"><span style="color:{color}">●</span> {s["label"]} '
                            f'<span style="opacity:.6">({len(here)})</span></div>', unsafe_allow_html=True)
                for o in here:
                    pct = round(100 * pos[o["stage"]] / len(stages))
                    lock = "🔒 Design locked" if pos[o["stage"]] >= pos["cutting"] else ""
                    with st.container(border=True):
                        st.markdown(task_card_html(o, pct, color, lock), unsafe_allow_html=True)
                        i = keys.index(s["key"])
                        if s["key"] == "order_received":
                            st.caption("⏳ Awaiting payment")
                        l, rr = st.columns(2)
                        if i > 0 and s["key"] != "payment_confirmed" and l.button("‹ Back", key=f"tb{o['id']}"):
                            staff_move(o["id"], keys[i - 1])
                        if i < len(keys) - 1 and s["key"] != "order_received" and rr.button("Next ›", key=f"tn{o['id']}"):
                            staff_move(o["id"], keys[i + 1])
                        with st.expander("Details and measurements"):
                            if o.get("modifications"):
                                st.write(f"**Modifications:** {o['modifications']}")
                            if o.get("special_requirements"):
                                st.write(f"**Special requirements:** {o['special_requirements']}")
                            sets = [m for m in meas if m["customer_id"] == o["customer_id"]]
                            for m in sets:
                                st.caption(f"{m.get('attire') or 'Measurements'} · {m['unit']}")
                                vals = m.get("measurement_values") or {}
                                if vals:
                                    st.dataframe(pd.DataFrame(list(vals.items()), columns=["Measurement", m["unit"]]),
                                                 width="stretch", hide_index=True)
                            if not sets:
                                st.caption("No measurements recorded yet.")
                            with st.form(f"wu_{o['id']}", clear_on_submit=True):
                                kind = st.selectbox("Work update", ["started", "progress", "completed", "delayed"],
                                                    key=f"wuk_{o['id']}")
                                note = st.text_input("Note", key=f"wun_{o['id']}")
                                if st.form_submit_button("Save update"):
                                    try:
                                        rec = {"order_id": o["id"], "kind": kind}
                                        if note.strip():
                                            rec["note"] = note.strip()
                                        db().table("work_updates").insert(rec).execute()
                                        done("Update saved")
                                    except Exception as e:
                                        err(e)


CUSTOM = {"staff_page": staff_page, "my_account": my_account, "customer_details": customer_details, "stock_in": stock_in, "stock_out": stock_out, "fashion_design_changes": design_changes}


# ---------------------------------------------------------------- dashboard & board
STYLE = """
<style>
[data-testid="stSidebar"]{background:#14202e}
@media (min-width:769px){[data-testid="stSidebar"]{width:220px !important;min-width:220px !important;max-width:220px !important}}
[data-testid="stSidebarUserContent"]{padding:1rem .75rem}
[data-testid="stSidebar"] *{color:#e6edf5}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.15rem}
[data-testid="stSidebar"] button{background:transparent !important;border:none !important;border-radius:0 !important;
  box-shadow:none !important;color:#e6edf5 !important;justify-content:flex-start !important;
  padding:.6rem .9rem !important;min-height:0}
[data-testid="stSidebar"] button p{margin:0;font-size:15px;text-align:left}
[data-testid="stSidebar"] button:hover{background:rgba(255,255,255,.08) !important}
[data-testid="stSidebar"] button[kind="primary"],[data-testid="stSidebar"] [data-testid="stBaseButton-primary"]{
  background:rgba(255,255,255,.16) !important;font-weight:600}
[data-testid="stSidebar"] .brand{background:#243a52;border:1px solid #3a5876;border-radius:12px;padding:10px 14px;
  margin-bottom:10px;font-size:20px;font-weight:700;letter-spacing:.05em;color:#ffffff}
[data-testid="stSidebar"] .sum{background:#243a52;border:1px solid #3a5876;border-radius:12px;padding:12px 14px;
  margin-top:14px;font-size:14px;line-height:1.7;color:#f1f5f9;word-break:break-word}
[data-testid="stSidebar"] .who{margin:10px 2px 6px;font-size:13px;color:#b9c6d6}
.oc{font-size:14px;line-height:1.35}
.oc .id{font-weight:700;font-size:13px}
.oc .row{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:5px}
.oc .sub{opacity:.75;font-size:12.5px}
.oc .price{font-weight:700}
.bdg{padding:1px 9px;border-radius:6px;font-size:12px;font-weight:600}
.b-paid{background:#d4edda;color:#1e6b34}.b-unpaid{background:#fde9b8;color:#8a5a00}.b-part{background:#d7e6fb;color:#1f4f99}
.bar{height:4px;background:rgba(128,128,128,.25);border-radius:9px;margin-top:9px;overflow:hidden}
.bar>span{display:block;height:100%;border-radius:9px}
.coltitle{font-weight:600;margin:4px 0 8px}
</style>
"""
SYM = {"NGN": "₦", "USD": "$", "GBP": "£", "EUR": "€", "GHS": "₵", "KES": "KSh "}
COLORS = ["#3b82f6", "#06b6d4", "#f59e0b", "#fb923c", "#a855f7", "#ec4899", "#22c55e", "#10b981"]
BADGE = {"unpaid": ("Unpaid", "b-unpaid"), "partially_paid": ("Part paid", "b-part"), "fully_paid": ("Paid", "b-paid")}


def currency_code():
    return next((r["value"] for r in rows("settings") if r["key"] == "currency"), "NGN")


def currency():
    cur = currency_code()
    return SYM.get(cur, f"{cur} ")


def card_html(o, det, bal, pct, color, sym):
    badge = BADGE.get(bal.get("payment_status", "unpaid"), BADGE["unpaid"])
    due = f"Due {o['due_date']}" if o.get("due_date") else "No due date"
    garment = html.escape(det.get("garment_type") or "—")
    paid = float(bal.get("paid") or 0)
    owing = max(float(o["total_amount"] or 0) - paid, 0)
    return (f'<div class="oc"><div class="id">{html.escape(o["order_no"])}</div>'
            f'<div class="row"><span>👤 {html.escape(o["customers"]["full_name"])}</span>'
            f'<span class="price">{sym}{float(o["total_amount"] or 0):,.0f}</span></div>'
            f'<div class="row sub"><span>📅 {due}</span></div>'
            f'<div class="row sub"><span>💵 Paid {sym}{paid:,.0f} · Balance {sym}{owing:,.0f}</span></div>'
            f'<div class="row sub"><span>🧵 {garment}</span>'
            f'<span class="bdg {badge[1]}">{badge[0]}</span></div>'
            f'<div class="bar"><span style="width:{pct}%;background:{color}"></span></div></div>')


def dashboard():
    sym = currency()
    stages = rows("stages", order="position", desc=False)
    keys = [s["key"] for s in stages]
    labels = {s["key"]: s["label"] for s in stages}
    pos = {s["key"]: s["position"] for s in stages}
    cut = pos["cutting"]
    orders = rows("orders", "id,order_no,stage,order_date,due_date,total_amount,tracking_token,"
                            "customers(full_name),fashion_order_details(change_window,garment_type)",
                  order="due_date", desc=False)
    bal = {b["order_id"]: b for b in rows("order_balances")}

    order_form()
    f1, f2, f3, f4 = st.columns([5, 2, 2, 1])
    q = f1.text_input("Search", placeholder="🔍 Search orders, customers, or ID",
                      label_visibility="collapsed").strip().lower()
    when = f2.selectbox("When", ["All dates", "Ordered today", "Due this week", "Overdue"],
                        label_visibility="collapsed")
    stf = f3.selectbox("Status", [None] + keys, label_visibility="collapsed",
                       format_func=lambda k: "All statuses" if k is None else labels[k])
    f4.button("↻", help="Refresh")

    today = date.today()

    def keep(o):
        det = o.get("fashion_order_details")
        det = det[0] if isinstance(det, list) and det else (det or {})
        hay = f"{o['order_no']} {o['customers']['full_name']} {det.get('garment_type') or ''}".lower()
        if q and q not in hay:
            return False
        due = date.fromisoformat(o["due_date"]) if o.get("due_date") else None
        if when == "Ordered today":
            return o.get("order_date") == today.isoformat()
        if when == "Due this week":
            return due is not None and today <= due <= today + timedelta(days=7)
        if when == "Overdue":
            return due is not None and due < today and o["stage"] != keys[-1]
        return True

    shown = [o for o in orders if keep(o)]
    cols_stages = [s for s in stages if stf in (None, s["key"])]
    for r in range(0, len(cols_stages), 4):
        chunk = cols_stages[r:r + 4]
        cols = st.columns(4)
        for col, s in zip(cols, chunk):
            here = [o for o in shown if o["stage"] == s["key"]]
            color = COLORS[(s["position"] - 1) % len(COLORS)]
            with col:
                st.markdown(f'<div class="coltitle"><span style="color:{color}">●</span> {s["label"]} '
                            f'<span style="opacity:.6">({len(here)})</span></div>', unsafe_allow_html=True)
                for o in here:
                    det = o.get("fashion_order_details")
                    det = det[0] if isinstance(det, list) and det else (det or {})
                    win = "locked" if pos[o["stage"]] >= cut else \
                        ("limited" if det.get("change_window") == "limited" else "open")
                    pct = round(100 * pos[o["stage"]] / len(stages))
                    with st.container(border=True):
                        st.markdown(card_html(o, det, bal.get(o["id"], {}), pct, color, sym), unsafe_allow_html=True)
                        i = keys.index(s["key"])
                        if s["key"] == "order_received":
                            st.caption("⏳ Awaiting payment. It moves on by itself once a payment is recorded under Money.")
                        l, m, rr = st.columns(3)
                        if i > 0 and s["key"] != "payment_confirmed" and l.button("‹", key=f"p{o['id']}", help="Move back a stage"):
                            move(o["id"], keys[i - 1])
                        with m.popover("⋮"):
                            st.caption("🔒 Design locked" if win == "locked" else f"Design {win}")
                            st.caption("Customer tracking link")
                            st.code(f"{APP_URL}/?t={o['tracking_token']}")
                        if i < len(keys) - 1 and s["key"] != "order_received" and rr.button("›", key=f"n{o['id']}", help="Move to next stage"):
                            move(o["id"], keys[i + 1])
    if not shown:
        st.info("No orders match. Add one with ➕ New order.")

    with st.expander("⚠ Alerts"):
        alerts = rows("alerts_orders")
        low_f, low_r = rows("alerts_low_stock"), rows("alerts_low_rtw")
        a, b, c = st.columns(3)
        a.metric("Delayed / due soon", len(alerts))
        b.metric("Low fabric / material", len(low_f))
        c.metric("Low ready-to-wear", len(low_r))
        if alerts:
            st.dataframe(pd.DataFrame(alerts)[["order_no", "customer", "due_date", "stage", "alert"]]
                         .rename(columns=lab), width="stretch", hide_index=True)
        if low_f:
            st.dataframe(pd.DataFrame(low_f)[["name", "ownership", "on_hand", "unit", "reorder_level"]]
                         .rename(columns=lab), width="stretch", hide_index=True)
        if low_r:
            st.dataframe(pd.DataFrame(low_r)[["sku", "name", "size", "colour", "on_hand"]]
                         .rename(columns=lab), width="stretch", hide_index=True)


def sidebar_summary():
    try:
        if is_staff_role():
            n = sum(1 for o in rows("my_orders", "id,stage") if o["stage"] != "delivered")
            st.markdown(f'<div class="sum"><b>Your work</b><br>✅ {n} orders assigned to you</div>',
                        unsafe_allow_html=True)
            return
        sym = currency()
        active = sum(1 for o in rows("orders", "stage") if o["stage"] != "delivered")
        delayed = sum(1 for a in rows("alerts_orders") if a["alert"] == "delayed")
        paid = sum(float(p["amount"]) for p in db().table("payments").select("amount")
                   .gte("paid_at", date.today().isoformat()).execute().data)
        st.markdown(f'<div class="sum"><b>Today\'s Summary</b><br>📋 {active} active orders<br>'
                    f'⚠ {delayed} delayed<br>💵 {sym}{paid:,.0f} received today</div>', unsafe_allow_html=True)
    except Exception:
        pass


def move(order_id, stage):
    try:
        db().table("orders").update({"stage": stage}).eq("id", order_id).execute()
        st.rerun()
    except Exception as e:
        err(e)


# ---------------------------------------------------------------- app shell
def login():
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        st.title(f"{BIZ} 🧵")
        if not URL.startswith("https://") or "YOUR-" in URL or "YOUR-" in KEY:
            st.error("The app's Secrets are not set correctly. Open Manage app > Settings > Secrets "
                     "and paste the real SUPABASE_URL (starts with https://) and SUPABASE_ANON_KEY.")
        with st.form("login"):
            email = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            go = st.form_submit_button("Sign in", type="primary")
        if go:
            try:
                cl = create_client(URL.strip(), KEY.strip())
                cl.auth.sign_in_with_password({"email": email.strip(), "password": pw})
                st.session_state["sb"] = cl
                st.rerun()
            except Exception as e:
                st.error("Sign-in failed. The details are below.")
                st.exception(e)


ICON = {"My tasks": "✅", "My account": "👤", "Dashboard": "▦", "Orders": "🛍", "Customers": "👥", "Fashion": "🧵", "Stock": "📦",
        "Ready-to-wear": "👗", "Money": "💳", "Team": "🧑‍🤝‍🧑"}


def main():
    st.markdown(STYLE, unsafe_allow_html=True)
    uid = db().auth.get_user().user.id
    me = db().table("profiles").select("id,full_name,role,responsibility").eq("id", uid).execute().data
    if me:
        st.session_state["me"] = me[0]
    nav = NAV_STAFF if (me and me[0]["role"] == "staff") else NAV
    with st.sidebar:
        st.markdown(f'<div class="brand">{html.escape(BIZ)}</div>', unsafe_allow_html=True)
        section = st.session_state.get("section")
        if section not in nav:
            section = next(iter(nav))
        for name in nav:
            if st.button(f"{ICON.get(name, '•')}  {name}", key=f"nav_{name}", width="stretch",
                         type="primary" if name == section else "secondary"):
                st.session_state["section"] = name
                st.rerun()
        sidebar_summary()
        who = f"{me[0]['full_name']} · {me[0]['role']}" if me else "No staff profile"
        st.markdown(f'<div class="who">{html.escape(who)}</div>', unsafe_allow_html=True)
        if st.button("Sign out"):
            st.session_state.pop("sb")
            st.rerun()
    if not me:
        st.warning("Your login has no active staff profile yet. Ask the owner to add you.")
        return
    st.header(section)
    flash = st.session_state.pop("flash", None)
    if flash:
        st.success(flash)
    if section == "Dashboard":
        dashboard()
    elif section == "My tasks":
        my_tasks()
    else:
        tabs = nav[section]
        pick = st.radio("View", tabs, format_func=lambda t: CFG[t]["title"], horizontal=True,
                        label_visibility="collapsed") if len(tabs) > 1 else tabs[0]
        CUSTOM[pick]() if pick in CUSTOM else table_view(pick)


token = st.query_params.get("t")
if token:
    tracking(token)
elif "sb" not in st.session_state:
    login()
else:
    main()

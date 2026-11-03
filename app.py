"""Nexxora Business Brain: Fashion branch (staff app + customer tracking page).
Streamlit + Supabase. Works on phone and desktop (columns stack on narrow screens)."""
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Nexxora Fashion", page_icon="🧵", layout="wide")

URL, KEY = st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"]
BIZ = st.secrets.get("BUSINESS_NAME", "B3")
APP_URL = st.secrets.get("APP_URL", "").rstrip("/")


# ---------------------------------------------------------------- tracking page
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
        a.metric("Expected", (o.get("expected_date") or "—"))
        b.metric("Last updated", (o.get("last_updated") or "—")[:10])
        if o.get("timeline"):
            st.markdown("**Progress**")
            for t in o["timeline"]:
                st.write(f"• {t['label']}  ·  {t['at'][:10]}")


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


def lab(c):
    return c.replace("_", " ").capitalize()


def F(col, label=None, kind="t", extra=None, default=None):
    return (col, label or lab(col), kind, extra, default)


# kinds: t text, n number, d date, x long text, j key=value pairs, s select
CFG = {
    "orders": dict(title="Orders", order="created_at",
        cols=["order_no", "customer_id", "due_date", "stage", "total_amount"],
        f=[F("customer_id", "Customer", "s", "customers:id:full_name"),
           F("offering_id", "Offering", "s", "offerings:id:name"),
           F("due_date", "Due date", "d"), F("total_amount", "Total price", "n"),
           F("stage", "Stage", "s", "stages:key:label", "order_received"),
           F("original_instructions", "Original instructions (paste WhatsApp text)", "x")]),
    "offerings": dict(title="Offerings", order="created_at", cols=["name", "base_price", "description"],
        f=[F("name"), F("base_price", "Base price", "n"), F("description", kind="x")]),
    "customers": dict(title="Customers", order="created_at", cols=["full_name", "phone", "whatsapp", "email"],
        f=[F("full_name", "Name"), F("phone"), F("whatsapp", "WhatsApp"), F("email"),
           F("address"), F("notes", kind="x")]),
    "fashion_measurements": dict(title="Measurements", order="taken_at",
        cols=["customer_id", "taken_at", "unit", "measurement_values"],
        f=[F("customer_id", "Customer", "s", "customers:id:full_name"),
           F("unit", kind="s", extra=["inches", "cm"], default="inches"),
           F("measurement_values", "Measurements (e.g. bust=36, waist=28, hip=40)", "j"),
           F("note")]),
    "fashion_order_details": dict(title="Design details", order=None, up=True,
        cols=["order_id", "garment_type", "fabric", "style", "change_window"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"), F("garment_type"),
           F("fabric", "Fabric (text description)"), F("style"),
           F("modifications", kind="x"), F("special_requirements", kind="x"),
           F("change_window", "Change window", "s", ["open", "limited", "locked"])]),
    "fashion_design_changes": dict(title="Design changes", order="created_at",
        cols=["order_id", "request", "extra_cost", "delivery_impact_days"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"), F("request", kind="x"),
           F("extra_cost", "Extra cost", "n"), F("delivery_impact_days", "Delivery impact (days)", "n")]),
    "fashion_qc": dict(title="Quality control", order="checked_at",
        cols=["order_id", "result", "notes", "checked_at"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"),
           F("result", kind="s", extra=["pass", "needs_correction"]), F("notes", kind="x")]),
    "fashion_fittings": dict(title="Fittings", order="created_at",
        cols=["order_id", "fitting_date", "notes", "adjustments"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"), F("fitting_date", "Fitting date", "d"),
           F("notes", kind="x"), F("adjustments", kind="x")]),
    "payments": dict(title="Payments received", order="paid_at",
        cols=["order_id", "amount", "method", "paid_at"],
        f=[F("order_id", "Order", "s", "orders:id:order_no"), F("amount", kind="n"),
           F("method", kind="s", extra=["cash", "transfer", "POS", "other"]), F("reference")]),
    "order_balances": dict(title="Balances", ro=True, order=None,
        cols=["order_no", "total_amount", "paid", "outstanding", "payment_status"]),
    "expenses": dict(title="Expenses", order="spent_on", cols=["category", "description", "amount", "spent_on"],
        f=[F("category"), F("description"), F("amount", kind="n"), F("spent_on", "Date", "d")]),
    "stock_items": dict(title="Stock items", order="created_at",
        cols=["name", "kind", "ownership", "customer_id", "colour", "unit", "reorder_level"],
        f=[F("name"), F("kind", kind="s", extra=["fabric", "material"], default="fabric"),
           F("ownership", kind="s", extra=["shop", "client"], default="shop"),
           F("customer_id", "Client (only if client-owned)", "s", "customers:id:full_name"),
           F("colour"), F("unit", "Unit (fabric must be yards)", default="yards"),
           F("reorder_level", "Low-stock level", "n")]),
    "stock_movements": dict(title="Stock in / out", order="created_at",
        cols=["item_id", "movement_type", "qty", "order_id", "note", "created_at"],
        f=[F("item_id", "Item", "s", "stock_items:id:name"),
           F("movement_type", "Type", "s", ["opening", "in", "out", "adjust_up", "adjust_down"]),
           F("qty", "Quantity (yards)", "n"), F("order_id", "For order", "s", "orders:id:order_no"),
           F("note")]),
    "stock_levels": dict(title="Stock levels", ro=True, order=None,
        cols=["name", "kind", "ownership", "colour", "on_hand", "unit", "reorder_level"]),
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
    "Production board": None,
    "Customers": ["customers", "fashion_measurements"],
    "Fashion": ["fashion_order_details", "fashion_design_changes", "fashion_qc", "fashion_fittings"],
    "Stock": ["stock_levels", "stock_items", "stock_movements"],
    "Ready-to-wear": ["rtw_levels", "rtw_products", "rtw_variants", "rtw_movements", "quick_sales", "quick_sale_items"],
    "Money": ["payments", "order_balances", "expenses"],
    "Team": ["work_updates", "attendance", "communications", "message_templates"],
}


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


def table_view(name):
    c = CFG[name]
    maps = {f[0]: look(*f[3].split(":")) for f in c.get("f", []) if f[2] == "s" and isinstance(f[3], str)}
    if not c.get("ro"):
        with st.expander(f"➕ Add — {c['title']}"):
            with st.form(f"add_{name}", clear_on_submit=True):
                grid = st.columns(2)
                vals = {}
                for i, f in enumerate(c["f"]):
                    with grid[i % 2]:
                        vals[f[0]] = widget(name, f, maps)
                if st.form_submit_button("Save", type="primary"):
                    rec = {f[0]: clean(f, vals[f[0]]) for f in c["f"]}
                    rec = {k: v for k, v in rec.items() if v is not None}
                    try:
                        t = db().table(name)
                        (t.upsert(rec) if c.get("up") else t.insert(rec)).execute()
                        st.success("Saved")
                        st.rerun()
                    except Exception as e:  # shows database rules too, e.g. "Design is LOCKED"
                        st.error(str(e))
    data = rows(name, order=c.get("order"))
    if not data:
        st.info("Nothing here yet.")
        return
    df = pd.DataFrame(data)
    for col, m in maps.items():
        if col in df:
            df[col] = df[col].map(m).fillna(df[col])
    for col in df.columns:
        if col.endswith("_at") or col in ("fitting_date",):
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%d %b %Y")
    show = [x for x in c["cols"] if x in df]
    st.dataframe(df[show].rename(columns=lab), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------- dashboard & board
def dashboard():
    orders = rows("orders", "stage")
    alerts = rows("alerts_orders")
    low_f, low_r = rows("alerts_low_stock"), rows("alerts_low_rtw")
    active = sum(1 for o in orders if o["stage"] != "delivered")
    a, b, c, d, e = st.columns(5)
    a.metric("Active orders", active)
    b.metric("Delayed", sum(1 for x in alerts if x["alert"] == "delayed"))
    c.metric("Due soon", sum(1 for x in alerts if x["alert"] == "due_soon"))
    d.metric("Low fabric/material", len(low_f))
    e.metric("Low ready-to-wear", len(low_r))
    if alerts:
        st.markdown("**Orders needing attention**")
        st.dataframe(pd.DataFrame(alerts)[["order_no", "customer", "due_date", "stage", "alert"]]
                     .rename(columns=lab), use_container_width=True, hide_index=True)
    if low_f:
        st.markdown("**Low fabric / material**")
        st.dataframe(pd.DataFrame(low_f)[["name", "ownership", "on_hand", "unit", "reorder_level"]]
                     .rename(columns=lab), use_container_width=True, hide_index=True)
    if low_r:
        st.markdown("**Low ready-to-wear**")
        st.dataframe(pd.DataFrame(low_r)[["sku", "name", "size", "colour", "on_hand"]]
                     .rename(columns=lab), use_container_width=True, hide_index=True)


def board():
    stages = rows("stages", order="position", desc=False)
    orders = rows("orders", "id,order_no,stage,due_date,tracking_token,customers(full_name),"
                            "fashion_order_details(change_window)", order="due_date", desc=False)
    keys = [s["key"] for s in stages]
    for chunk in (stages[:4], stages[4:]):
        cols = st.columns(len(chunk))
        for col, s in zip(cols, chunk):
            here = [o for o in orders if o["stage"] == s["key"]]
            with col:
                st.markdown(f"**{s['label']}** · {len(here)}")
                for o in here:
                    det = o.get("fashion_order_details")
                    det = det[0] if isinstance(det, list) and det else det
                    win = (det or {}).get("change_window", "open")
                    with st.container(border=True):
                        st.write(f"**{o['order_no']}** — {o['customers']['full_name']}")
                        st.caption(f"Due {o['due_date'] or '—'} · design {win.upper()}")
                        i = keys.index(s["key"])
                        l, r = st.columns(2)
                        if i > 0 and l.button("‹", key=f"p{o['id']}"):
                            move(o["id"], keys[i - 1])
                        if i < len(keys) - 1 and r.button("›", key=f"n{o['id']}"):
                            move(o["id"], keys[i + 1])
    st.divider()
    pick = st.selectbox("Customer tracking link for order", [None] + orders,
                        format_func=lambda o: "—" if o is None else f"{o['order_no']} — {o['customers']['full_name']}")
    if pick:
        st.code(f"{APP_URL}/?t={pick['tracking_token']}")


def move(order_id, stage):
    try:
        db().table("orders").update({"stage": stage}).eq("id", order_id).execute()
        st.rerun()
    except Exception as e:
        st.error(str(e))


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


def main():
    uid = db().auth.get_user().user.id
    me = db().table("profiles").select("full_name,role").eq("id", uid).execute().data
    with st.sidebar:
        st.markdown(f"### {BIZ}")
        section = st.radio("Menu", list(NAV), label_visibility="collapsed")
        st.caption(f"{me[0]['full_name']} · {me[0]['role']}" if me else "No staff profile")
        if st.button("Sign out"):
            st.session_state.pop("sb")
            st.rerun()
    if not me:
        st.warning("Your login has no active staff profile yet. Ask the owner to add you.")
        return
    st.header(section)
    if section == "Dashboard":
        dashboard()
    elif section == "Production board":
        board()
    else:
        tabs = NAV[section]
        pick = st.radio("View", tabs, format_func=lambda t: CFG[t]["title"], horizontal=True,
                        label_visibility="collapsed") if len(tabs) > 1 else tabs[0]
        table_view(pick)


token = st.query_params.get("t")
if token:
    tracking(token)
elif "sb" not in st.session_state:
    login()
else:
    main()

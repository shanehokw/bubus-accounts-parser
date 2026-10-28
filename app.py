"""Statement → Excel. Run with ./run.command (or .venv/bin/streamlit run app.py)."""

import hashlib
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from statement_parser import PasswordRequired, parse_statement
from statement_parser import rules as rules_store
from statement_parser.excel import to_xlsx

ACCOUNTS = ["HSBC", "Cash", "Maybank", "Grab", "TNG", "SC CC", "RHB", "Ryt"]
CATEGORY_OPTIONS = rules_store.CATEGORIES + rules_store.SPECIAL_CATEGORIES
COLUMNS = ["date", "month", "settled", "account", "value", "category", "type", "description", "source", "key"]

st.set_page_config(page_title="Statements to Excel", page_icon="📄", layout="wide")
state = st.session_state
state.setdefault("parsed", {})  # file id -> {"name", "statement" | "error" | "needs_password"}
state.setdefault("passwords", {})
state.setdefault("table", pd.DataFrame(columns=COLUMNS))
state.setdefault("table_files", ())  # file ids the table was built from
state.setdefault("uploader", 0)
state.setdefault("editor_version", 0)  # bumped to redraw the table after the app changes it
state.setdefault("message", "")


def parse_upload(file_id: str, name: str, data: bytes):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "statement.pdf"
        path.write_bytes(data)
        try:
            statement = parse_statement(path, state.passwords.get(file_id, ""))
            state.parsed[file_id] = {"name": name, "statement": statement}
        except PasswordRequired:
            state.parsed[file_id] = {"name": name, "needs_password": True}
        except Exception as e:
            state.parsed[file_id] = {"name": name, "error": f"{type(e).__name__}: {e}"}


def rows_for(file_id: str, rules: dict) -> list:
    statement = state.parsed[file_id]["statement"]
    rows = []
    for t in statement.transactions:
        rows.append({
            "date": t.date, "month": t.date.strftime("%B"), "settled": t.settled,
            "account": t.account, "value": t.value,
            "category": t.category or rules_store.guess(t.key, t.description, rules),
            "type": t.type, "description": t.description, "source": state.parsed[file_id]["name"],
            "key": t.key, "file": file_id,
        })
    return rows


def rebuild_table(file_ids: tuple, edited: pd.DataFrame):
    """Keeps edited rows of files still uploaded, adds rows for new files."""
    rules = rules_store.load()
    kept = edited[edited["file"].isin(file_ids) | edited["file"].isna()] if "file" in edited else edited
    new_ids = [f for f in file_ids if f not in state.table_files]
    new_rows = [r for f in new_ids for r in rows_for(f, rules)]
    table = pd.concat([kept, pd.DataFrame(new_rows)], ignore_index=True) if new_rows else kept
    if len(table):
        is_start = table["category"].eq("Starting Balance")
        table = (table.assign(_start=~is_start)
                 .sort_values(["date", "_start"], kind="stable")
                 .drop(columns="_start")
                 .reset_index(drop=True))
    state.table, state.table_files = table, file_ids


def learn_and_save(pairs, downloaded: bool):
    rules = rules_store.load()
    changed = rules_store.learn(pairs, rules)
    rules_store.save(rules)
    state.message = ("Excel file downloaded. " if downloaded else "") + \
        f"{changed} category rule(s) added or updated."
    state.ask_apply = not downloaded and changed > 0


def rule_changes(table: pd.DataFrame, rules: dict) -> list:
    """Rows whose category the rules would change: (row index, new category, row was blank)."""
    changes = []
    for i, r in table.iterrows():
        current = r["category"] if isinstance(r["category"], str) else ""
        if current == "Starting Balance":
            continue
        text = lambda col: r[col] if isinstance(r.get(col), str) else ""
        new = rules_store.guess(text("key"), text("description"), rules)
        if new and new != current:
            changes.append((i, new, current == ""))
    return changes


@st.dialog("Update categories in the table?")
def ask_apply_rules(changes: list):
    blank = sum(1 for c in changes if c[2])
    st.write(f"The rules give a different category for **{len(changes)}** row(s) in the table:")
    st.markdown(f"- {blank} row(s) with no category\n- {len(changes) - blank} row(s) with a different "
                "category already set")
    c1, c2, c3 = st.columns(3)
    if c1.button("Update all", type="primary", width="stretch"):
        apply_rule_changes(changes)
    if c2.button("Only empty ones", width="stretch", disabled=blank == 0):
        apply_rule_changes([c for c in changes if c[2]])
    if c3.button("No", width="stretch"):
        st.rerun()


def apply_rule_changes(changes: list):
    table = state.edited.copy()
    for i, category, _ in changes:
        table.at[i, "category"] = category
    state.table = table
    state.editor_version += 1
    state.message = f"Updated the category of {len(changes)} row(s)."
    st.rerun()


# ---------------------------------------------------------------- page

st.title("Statements to Excel")
st.caption("Everything runs on this Mac. Nothing is uploaded to the internet.")

uploads = st.file_uploader(
    "Upload statement PDFs (Maybank, HSBC, SC, RHB, Ryt, TNG)", type="pdf", accept_multiple_files=True,
    key=f"uploader_{state.uploader}",
)

file_ids = []
for up in uploads or []:
    data = up.getvalue()
    file_id = hashlib.sha1(data).hexdigest()
    file_ids.append(file_id)
    if file_id not in state.parsed:
        with st.spinner(f"Reading {up.name}… (HSBC statements take a few seconds per page)"):
            parse_upload(file_id, up.name, data)

    info = state.parsed[file_id]
    if info.get("needs_password"):
        with st.form(f"pw_{file_id}"):
            pw = st.text_input(f"🔒 {up.name} is password-protected. Password:", type="password")
            if st.form_submit_button("Open"):
                state.passwords[file_id] = pw
                with st.spinner(f"Reading {up.name}…"):
                    parse_upload(file_id, up.name, data)
                st.rerun()

ready = tuple(f for f in file_ids if "statement" in state.parsed[f])

# Per-file summary
for file_id in file_ids:
    info = state.parsed[file_id]
    if "error" in info:
        st.error(f"**{info['name']}**: could not read it. {info['error']}")
    elif "statement" in info:
        s = info["statement"]
        icon = "✅" if s.check_ok else "⚠️"
        with st.expander(f"{icon} **{info['name']}**: {s.kind} → {s.account}, "
                         f"{len(s.transactions)} rows", expanded=not s.check_ok or bool(s.warnings)):
            (st.success if s.check_ok else st.warning)(f"Balance check: {s.check}")
            for w in s.warnings:
                st.warning(w)

if ready != state.table_files:
    edited = state.get("edited", state.table)
    rebuild_table(ready, edited if isinstance(edited, pd.DataFrame) else state.table)

if not len(state.table) and not ready:
    st.info("Upload one or more statements to begin. You can add Cash rows by hand once the table appears.")
    st.stop()

st.subheader("Transactions")
st.caption("Edit any cell. Add rows (e.g. Cash) with the + at the bottom; delete rows by selecting them "
           "and pressing Delete. Categories you pick are remembered when you click Save rules or Download Excel.")

edited = st.data_editor(
    state.table,
    key=f"editor_{hash(state.table_files)}_{state.editor_version}",
    num_rows="dynamic",
    width="stretch",
    height=600,
    hide_index=True,
    column_order=["date", "month", "settled", "account", "value", "category", "type", "description",
                  "source"],
    column_config={
        "date": st.column_config.DateColumn("DATE", format="DD/MM/YYYY", required=True),
        "month": st.column_config.TextColumn("MONTH", disabled=True, help="Follows DATE"),
        "settled": st.column_config.CheckboxColumn("SETTLED", default=False),
        "account": st.column_config.SelectboxColumn("ACCOUNT", options=ACCOUNTS, required=True),
        "value": st.column_config.NumberColumn("VALUE", format="%.2f", required=True,
                                               help="Negative = money out"),
        "category": st.column_config.SelectboxColumn("CATEGORY", options=CATEGORY_OPTIONS),
        "type": st.column_config.TextColumn("TYPE"),
        "description": st.column_config.TextColumn("DESCRIPTION", width="large"),
        "source": st.column_config.TextColumn("SOURCE", disabled=True,
                                              help="The file this row came from. Not written to Excel."),
    },
)
state.edited = edited

# Keep MONTH in step with DATE after a date is edited or a row is added.
months = [d.strftime("%B") if isinstance(d, date) else "" for d in edited["date"]]
if months != list(edited["month"].fillna("")):
    state.table = edited.assign(month=months)
    state.editor_version += 1
    st.rerun()

valid = edited.dropna(subset=["date", "account", "value"])
valid = valid[valid["date"].apply(lambda d: isinstance(d, date))]
skipped = len(edited) - len(valid)
rows = [
    {**r, "settled": bool(r.get("settled")) if pd.notna(r.get("settled")) else False,
     "category": r["category"] if pd.notna(r["category"]) else "",
     "type": r["type"] if pd.notna(r["type"]) else "",
     "description": r["description"] if pd.notna(r["description"]) else ""}
    for r in valid.sort_values("date", kind="stable").to_dict("records")
]
pairs = [(r.get("key"), r["category"]) for r in rows if isinstance(r.get("key"), str)]

col1, col2, col3 = st.columns([1, 1, 3])
with col1:
    st.download_button(
        "⬇️ Download Excel", data=to_xlsx(rows), file_name=f"statements_{date.today():%Y-%m-%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary", on_click=learn_and_save, args=(pairs, True), width="stretch",
    )
with col2:
    st.button("💾 Save rules", on_click=learn_and_save, args=(pairs, False), width="stretch",
              help="Remember the categories picked in the table, without downloading")
with col3:
    note = f"{len(rows)} rows."
    if skipped:
        note += f" {skipped} row(s) without a date, account or value will be left out."
    st.caption(note)
if state.message:
    st.success(state.message)
    state.message = ""

if st.button("Start over"):
    for k in ["parsed", "passwords", "table", "table_files", "edited"]:
        state.pop(k, None)
    state.uploader += 1
    st.rerun()

# ---------------------------------------------------------------- rules

with st.expander("Category rules"):
    st.caption(f"Saved in `{rules_store.RULES_FILE.name}` in the app folder. A rule applies when its "
               "text appears in a transaction's description; the longest matching text wins.")
    rules = rules_store.load()
    rules_df = pd.DataFrame(sorted(rules.items(), key=lambda kv: kv[0].upper()),
                            columns=["text", "category"])
    new_rules = st.data_editor(
        rules_df, num_rows="dynamic", hide_index=True, width="stretch", key="rules_editor",
        column_config={
            "text": st.column_config.TextColumn("Text in description", required=True),
            "category": st.column_config.SelectboxColumn("Category", options=rules_store.RULE_CATEGORIES,
                                                         required=True),
        },
    )
    if st.button("Save rule list"):
        cleaned = {r["text"].strip(): r["category"] for r in new_rules.dropna().to_dict("records")
                   if r["text"].strip()}
        rules_store.save(cleaned)
        st.success(f"Saved {len(cleaned)} rule(s). New uploads will use them.")
        state.ask_apply = True

# After the rules change, offer to re-apply them to the table.
if state.pop("ask_apply", False):
    changes = rule_changes(state.edited, rules_store.load())
    if changes:
        ask_apply_rules(changes)

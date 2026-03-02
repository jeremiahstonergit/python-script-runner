#TITLE: Tariffs pivots (VH/VPS regs & payments)
#INPUT_HINT: Загрузите created_accounts.csv (разделитель ';', кодировка utf-8-sig или cp1251). Скрипт строит 4 листа в Excel.
#OUTPUT_EXT: .xlsx

import argparse
from pathlib import Path

import pandas as pd


def read_df(path: Path, sep: str = ";") -> pd.DataFrame:
    # UTF-8 с BOM (utf-8-sig) или cp1251
    for enc in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            return pd.read_csv(path, sep=sep, quotechar='"', engine="python", encoding=enc)
        except Exception:
            continue
    raise RuntimeError("Не удалось прочитать CSV (пробовал: utf-8-sig, cp1251, utf-8)")


def build_pivots(df: pd.DataFrame, service: str):
    d = df[df["Услуга"] == service].copy()

    months = (
        d.loc[d["Месяц"].notna(), "Месяц"]
        .drop_duplicates()
        .sort_values(key=lambda s: pd.to_datetime(s, format="%Y-%m", errors="coerce"))
        .tolist()
    )

    tariffs = d["Тариф"].fillna("(пусто)").astype(str)
    tariff_order = tariffs.drop_duplicates().tolist()

    paid_col = "Была ли оплата"

    reg = (
        d.pivot_table(
            index="Тариф",
            columns="Месяц",
            values="Id заказа",
            aggfunc="count",
            fill_value=0,
        )
        .rename_axis(index=None, columns=None)
    )

    pay = (
        d.pivot_table(
            index="Тариф",
            columns="Месяц",
            values=paid_col,
            aggfunc="sum",
            fill_value=0,
        )
        .rename_axis(index=None, columns=None)
    )

    reg.index = reg.index.fillna("(пусто)").astype(str)
    pay.index = pay.index.fillna("(пусто)").astype(str)

    reg = reg.reindex(index=tariff_order, columns=months, fill_value=0).astype(int)
    pay = pay.reindex(index=tariff_order, columns=months, fill_value=0).astype(int)

    return reg, pay


def main():
    ap = argparse.ArgumentParser(description="Пивоты по тарифам для VH/VPS (регистрации и оплаты).")
    ap.add_argument("--input", required=True, help="Путь к created_accounts.csv")
    ap.add_argument("--output", required=True, help="Путь к summary_pivots.xlsx")
    ap.add_argument("--sep", default=";", help="Разделитель CSV (default: ';')")
    args = ap.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise SystemExit(f"Файл {input_path} не найден.")

    df = read_df(input_path, sep=args.sep)

    # Нормализация
    df["Время поступления"] = pd.to_datetime(df["Время поступления"], errors="coerce")
    df = df[df["Статус"].astype(str).str.lower().eq("success")].copy()

    df["Услуга"] = df["Услуга"].astype(str).str.strip().str.lower()
    df = df[df["Услуга"].isin(["vh", "vps"])].copy()

    df["Месяц"] = df["Время поступления"].dt.to_period("M").astype(str)

    paid_col = "Была ли оплата"
    df[paid_col] = (
        df[paid_col].astype(str).str.strip().str.lower()
        .str.replace(r"[^a-z]", "", regex=True)
        .map(lambda s: 1 if s.startswith("y") else 0)
        .fillna(0).astype(int)
    )

    vh_reg, vh_pay = build_pivots(df, "vh")
    vps_reg, vps_pay = build_pivots(df, "vps")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as xw:
        vh_reg.to_excel(xw, sheet_name="VH_Регистрации")
        vh_pay.to_excel(xw, sheet_name="VH_Оплаты")
        vps_reg.to_excel(xw, sheet_name="VPS_Регистрации")
        vps_pay.to_excel(xw, sheet_name="VPS_Оплаты")

        for sheet in ("VH_Регистрации", "VH_Оплаты", "VPS_Регистрации", "VPS_Оплаты"):
            ws = xw.sheets[sheet]
            ws.set_column(0, 0, 26)
            ws.set_column(1, 100, 12)

    print(f"OK: {output_path.resolve()}")


if __name__ == "__main__":
    main()

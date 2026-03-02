#TITLE: Conversion VPS+VH (monthly + daily) -> ZIP
#INPUT_HINT: Загрузите created_accounts.csv (разделитель ';'). На выходе .zip с 4 CSV: vps_conversion.csv, vps_paid_daily.csv, vh_conversion.csv, vh_paid_daily.csv.
#OUTPUT_EXT: .zip

import argparse
import tempfile
import zipfile
from pathlib import Path

import pandas as pd


def norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip().str.replace("\ufeff", "", regex=True)
    return df


def y_to_bool(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .str.replace(r"[^a-z]", "", regex=True)
        .map(lambda s: 1 if s.startswith("y") else 0)
        .fillna(0)
        .astype(int)
    )


def build_reports_for_service(df: pd.DataFrame, service_value: str):
    subset = df[(df["Услуга"] == service_value) & (df["Статус"] == "success")].copy()
    if subset.empty:
        monthly = pd.DataFrame(columns=["месяц", "всего_заказов", "оплачено", "конверсия (%)"])
        daily = pd.DataFrame(columns=["дата", "всего_заказов", "оплачено"])
        return monthly, daily

    subset["месяц"] = subset["Время поступления"].dt.to_period("M").astype(str)
    subset["дата"] = subset["Время поступления"].dt.date

    monthly = subset.groupby("месяц").agg(
        всего_заказов=("Услуга", "count"),
        оплачено=("paid_bool", "sum"),
    ).reset_index()
    monthly["конверсия (%)"] = (monthly["оплачено"] / monthly["всего_заказов"] * 100).round(2)

    daily = subset.groupby("дата").agg(
        всего_заказов=("Услуга", "count"),
        оплачено=("paid_bool", "sum"),
    ).reset_index()

    return monthly, daily


def main():
    ap = argparse.ArgumentParser(description="VPS+VH conversion exporter (ZIP with CSVs).")
    ap.add_argument("--input", required=True, help="Путь к created_accounts.csv")
    ap.add_argument("--output", required=True, help="Путь к .zip (результат)")
    ap.add_argument("--sep", default=";", help="Разделитель CSV (default: ';')")
    ap.add_argument("--encoding", default="utf-8", help="Кодировка CSV (default: utf-8)")
    args = ap.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise SystemExit(f"Файл {input_path} не найден.")

    df = pd.read_csv(input_path, encoding=args.encoding, sep=args.sep, low_memory=False)
    df = norm_cols(df)

    df["Время поступления"] = pd.to_datetime(df["Время поступления"], errors="coerce")
    df = df.dropna(subset=["Время поступления"]).copy()

    for col in ["Услуга", "Статус", "Была ли оплата"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str).str.strip().str.lower().replace({"nan": ""})

    df["paid_bool"] = y_to_bool(df["Была ли оплата"])

    vps_monthly, vps_daily = build_reports_for_service(df, "vps")
    vh_monthly, vh_daily = build_reports_for_service(df, "vh")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        files = {
            "vps_conversion.csv": vps_monthly,
            "vps_paid_daily.csv": vps_daily,
            "vh_conversion.csv": vh_monthly,
            "vh_paid_daily.csv": vh_daily,
        }

        for name, frame in files.items():
            frame.to_csv(td_path / name, index=False, encoding="utf-8-sig")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name in files.keys():
                zf.write(td_path / name, arcname=name)

    print(f"OK: {output_path.resolve()}")


if __name__ == "__main__":
    main()

#TITLE: Conversion VPS (monthly + daily) -> ZIP
#INPUT_HINT: Загрузите created_accounts.csv (разделитель ';'). На выходе .zip с 2 CSV: vps_conversion.csv и vps_paid_daily.csv.
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
        series.astype(str).str.strip().str.lower()
        .str.replace(r"[^a-z]", "", regex=True)
        .map(lambda s: 1 if s.startswith("y") else 0)
        .fillna(0).astype(int)
    )


def main():
    ap = argparse.ArgumentParser(description="VPS conversion exporter (ZIP with CSVs).")
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

    filtered = df[(df["Услуга"] == "vps") & (df["Статус"] == "success")].copy()
    filtered["месяц"] = filtered["Время поступления"].dt.to_period("M").astype(str)
    filtered["дата"] = filtered["Время поступления"].dt.date
    filtered["paid_bool"] = y_to_bool(filtered["Была ли оплата"])

    monthly_summary = filtered.groupby("месяц").agg(
        всего_заказов=("Id заказа", "count"),
        оплачено=("paid_bool", "sum"),
    ).reset_index()
    monthly_summary["конверсия (%)"] = (
        monthly_summary["оплачено"] / monthly_summary["всего_заказов"] * 100
    ).round(2)

    daily_summary = filtered.groupby("дата").agg(
        всего_заказов=("Id заказа", "count"),
        оплачено=("paid_bool", "sum"),
    ).reset_index()

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        monthly_summary.to_csv(td_path / "vps_conversion.csv", index=False, encoding="utf-8-sig")
        daily_summary.to_csv(td_path / "vps_paid_daily.csv", index=False, encoding="utf-8-sig")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(td_path / "vps_conversion.csv", arcname="vps_conversion.csv")
            zf.write(td_path / "vps_paid_daily.csv", arcname="vps_paid_daily.csv")

    print(f"OK: {output_path.resolve()}")


if __name__ == "__main__":
    main()

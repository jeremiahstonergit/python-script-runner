#TITLE: Promocodes analytics (monthly + top10)
#INPUT_HINT: Загрузите created_accounts.csv (разделитель ';'). Нужные колонки: Время поступления, Промокод партнера, Услуга, Была ли оплата.
#OUTPUT_EXT: .xlsx

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd


# ---------------- helpers ----------------
def to_bool_y(series: pd.Series) -> pd.Series:
    # ожидается "y"/"Y", но переживём и человеческий фактор
    return series.fillna("").astype(str).str.strip().str.lower().eq("y")


def conv(paid: int, total: int) -> float:
    return round(paid / total * 100, 2) if total else 0.0


def parse_ymd(s: str) -> dt.datetime:
    # "2026-01-31" -> datetime(2026,1,31,0,0)
    return dt.datetime.strptime(s, "%Y-%m-%d")


def default_output_name(input_path: str, date_min: pd.Timestamp, date_max: pd.Timestamp) -> str:
    base = Path(input_path).stem
    d1 = date_min.strftime("%Y-%m")
    d2 = date_max.strftime("%Y-%m")
    return f"{base}_analytics_{d1}_to_{d2}.xlsx"


# ---------------- main ----------------
def main():
    parser = argparse.ArgumentParser(
        description="Помесячная аналитика по промокодам без привязки к году (по датам из файла)."
    )
    parser.add_argument("--input", required=True, help="Путь к CSV")
    parser.add_argument("--output", required=True, help="Путь к XLSX")
    parser.add_argument("--from", dest="date_from", default=None, help="Начальная дата YYYY-MM-DD (включительно)")
    parser.add_argument("--to", dest="date_to", default=None, help="Конечная дата YYYY-MM-DD (включительно)")
    parser.add_argument("--sep", default=";", help="Разделитель в CSV (default: ';')")
    parser.add_argument("--encoding", default="utf-8", help="Кодировка CSV (default: utf-8)")
    args = parser.parse_args()

    INPUT_FILE = args.input

    # -------- load & normalize --------
    df = pd.read_csv(INPUT_FILE, encoding=args.encoding, sep=args.sep)
    df.columns = df.columns.str.strip().str.replace("\ufeff", "", regex=True)

    required_cols = {"Время поступления", "Промокод партнера", "Услуга", "Была ли оплата"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"В CSV не хватает колонок: {', '.join(sorted(missing))}")

    df["Время поступления"] = pd.to_datetime(df["Время поступления"], errors="coerce")
    df = df.dropna(subset=["Время поступления"]).copy()

    df["Промокод партнера"] = df["Промокод партнера"].fillna("").astype(str).str.strip().str.lower()
    df["Услуга"] = df["Услуга"].fillna("").astype(str).str.strip().str.lower()
    df["Была ли оплата"] = df["Была ли оплата"].fillna("").astype(str).str.strip().str.lower()

    # -------- optional date range filter --------
    if args.date_from:
        dt_from = parse_ymd(args.date_from)
        df = df[df["Время поступления"] >= dt_from].copy()

    if args.date_to:
        # включительно, поэтому +1 день и строго меньше
        dt_to_excl = parse_ymd(args.date_to) + dt.timedelta(days=1)
        df = df[df["Время поступления"] < dt_to_excl].copy()

    if df.empty:
        raise ValueError("После фильтрации по датам не осталось строк. Проверь CSV и диапазон дат.")

    # month column (YYYY-MM)
    df["месяц"] = df["Время поступления"].dt.to_period("M")

    # только строки с любым промокодом
    promos_df = df[df["Промокод партнера"] != ""].copy()

    # если промокодов нет вообще, всё равно сделаем сводку по месяцам (она будет нулевая)
    date_min = df["Время поступления"].min()
    date_max = df["Время поступления"].max()

    months_range = pd.period_range(date_min.to_period("M"), date_max.to_period("M"), freq="M")

    # контекстные промокоды и разметка услуг (как в твоём исходном скрипте)
    CTX_PROMOS = {"vds20y", "skidka30"}
    VPS_SERVICES = {"vps", "s3", "dbaas", "kaas"}
    VH_SERVICE = "vh"

    # -------- monthly summary --------
    rows = []

    for m in months_range:
        m_df = promos_df[promos_df["месяц"] == m].copy() if not promos_df.empty else promos_df

        # маски по Быкову (внутри месяца)
        m_bykov_partner_mask = m_df["Промокод партнера"].str.contains(r"\bstascode\b", regex=True)
        m_bykov_discount_mask = m_df["Промокод партнера"].str.contains(r"\bstasbykov\b|\bsuperstas\b", regex=True)

        # итого по промокодам
        total_regs = len(m_df)
        total_paid = int(to_bool_y(m_df["Была ли оплата"]).sum()) if total_regs else 0
        total_conv = conv(total_paid, total_regs)

        # контекст VH
        vh_df = m_df[(m_df["Услуга"] == VH_SERVICE) & (m_df["Промокод партнера"].isin(CTX_PROMOS))]
        vh_regs = len(vh_df)
        vh_paid = int(to_bool_y(vh_df["Была ли оплата"]).sum()) if vh_regs else 0
        vh_conv = conv(vh_paid, vh_regs)

        # контекст VPS
        vps_df = m_df[(m_df["Услуга"].isin(VPS_SERVICES)) & (m_df["Промокод партнера"].isin(CTX_PROMOS))]
        vps_regs = len(vps_df)
        vps_paid = int(to_bool_y(vps_df["Была ли оплата"]).sum()) if vps_regs else 0
        vps_conv = conv(vps_paid, vps_regs)

        # Быков оплаченные
        m_bykov_partner_paid = int(to_bool_y(m_df.loc[m_bykov_partner_mask, "Была ли оплата"]).sum()) if total_regs else 0
        m_bykov_discount_paid = int(to_bool_y(m_df.loc[m_bykov_discount_mask, "Была ли оплата"]).sum()) if total_regs else 0
        m_bykov_total_paid = m_bykov_partner_paid + m_bykov_discount_paid

        rows.append(
            {
                "Месяц": str(m),  # YYYY-MM
                "Всего рег. по промокодам": total_regs,
                "Оплачено всего": total_paid,
                "Конверсия всего (%)": total_conv,
                "VH рег. (контекст)": vh_regs,
                "VH оплачено": vh_paid,
                "VH конверсия (%)": vh_conv,
                "VPS рег. (контекст)": vps_regs,
                "VPS оплачено": vps_paid,
                "VPS конверсия (%)": vps_conv,
                "Быков оплачено всего": m_bykov_total_paid,
                "Быков оплачено (скидка)": m_bykov_discount_paid,
                "Быков оплачено (партнер)": m_bykov_partner_paid,
            }
        )

    summary_df = pd.DataFrame(rows).sort_values("Месяц")

    # -------- monthly top-10 promos (exclude context promos) --------
    exclude_promos = {"skidka30", "vds20y"}
    top_rows = []

    if not promos_df.empty:
        for m in months_range:
            m_df = promos_df[(promos_df["месяц"] == m) & (~promos_df["Промокод партнера"].isin(exclude_promos))].copy()
            if m_df.empty:
                continue

            stats = (
                m_df.groupby("Промокод партнера", as_index=False)
                .agg(
                    Регистраций=("Промокод партнера", "size"),
                    Оплачено=("Была ли оплата", lambda s: int(to_bool_y(s).sum())),
                )
            )
            stats["Конверсия (%)"] = stats.apply(lambda r: conv(int(r["Оплачено"]), int(r["Регистраций"])), axis=1)
            stats["Месяц"] = str(m)

            stats = stats.sort_values(["Оплачено", "Регистраций"], ascending=[False, False]).head(10)
            stats = stats[["Месяц", "Промокод партнера", "Регистраций", "Оплачено", "Конверсия (%)"]]
            top_rows.append(stats)

    top10_df = (
        pd.concat(top_rows, ignore_index=True)
        if top_rows
        else pd.DataFrame(columns=["Месяц", "Промокод партнера", "Регистраций", "Оплачено", "Конверсия (%)"])
    )

    # -------- write Excel --------
    output_file = args.output or default_output_name(INPUT_FILE, date_min, date_max)

    with pd.ExcelWriter(output_file) as writer:
        summary_df.to_excel(writer, sheet_name="Сводка по месяцам", index=False)
        top10_df.to_excel(writer, sheet_name="Топ-10 промокодов", index=False)

    print(f"OK: файл '{output_file}' создан без ошибок.")
    print(f"Диапазон данных: {date_min.date()} .. {date_max.date()}")


if __name__ == "__main__":
    main()
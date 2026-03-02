#TITLE: Cohort analysis (retention + revenue)
#INPUT_HINT: Загрузите stat_provided_goods.csv (без заголовков): date(mm-YYYY), current_customer_id, type, amount.
#OUTPUT_EXT: .xlsx

import argparse
import warnings

import numpy as np
import pandas as pd
from openpyxl.styles import numbers

warnings.simplefilter(action="ignore", category=FutureWarning)


def cohort_analysis(data: pd.DataFrame, service_type: str):
    # Когорты на основе первого месяца активности клиента
    data["cohort"] = data.groupby("current_customer_id")["date"].transform("min").dt.to_period("M")
    data["cohort_month"] = (data["date"].dt.to_period("M") - data["cohort"]).apply(lambda x: x.n)

    cohort_pivot_retention = data.pivot_table(
        index="cohort",
        columns="cohort_month",
        values="current_customer_id",
        aggfunc=pd.Series.nunique,
    )
    cohort_size = cohort_pivot_retention.iloc[:, 0]
    retention_matrix = cohort_pivot_retention.divide(cohort_size, axis=0)

    retention_matrix["cohort_size"] = cohort_size
    retention_matrix.loc["Среднее"] = retention_matrix.mean()

    cohort_pivot_revenue = data.pivot_table(
        index="cohort",
        columns="cohort_month",
        values="amount",
        aggfunc=np.sum,
    )
    cohort_pivot_revenue["cohort_size"] = cohort_size
    cohort_pivot_revenue["Сумма выручки"] = cohort_pivot_revenue.sum(axis=1)

    retention_matrix.index = retention_matrix.index.astype(str)
    cohort_pivot_revenue.index = cohort_pivot_revenue.index.astype(str)

    return retention_matrix, cohort_pivot_revenue


def main():
    parser = argparse.ArgumentParser(description="Cohort analysis exporter (xlsx).")
    parser.add_argument("--input", required=True, help="Путь к stat_provided_goods.csv")
    parser.add_argument("--output", required=True, help="Путь к cohort_analysis.xlsx")
    args = parser.parse_args()

    # Загрузка данных (без заголовков)
    df = pd.read_csv(args.input, header=None)
    df.columns = ["date", "current_customer_id", "type", "amount"]

    df["date"] = pd.to_datetime(df["date"], format="%m-%Y", errors="coerce")
    df = df.dropna(subset=["date"]).copy()

    unique_service_types = df["type"].dropna().unique()

    with pd.ExcelWriter(args.output, engine="openpyxl") as writer:
        for service_type in unique_service_types:
            df_service = df[df["type"] == service_type].copy()
            retention_matrix, revenue_matrix = cohort_analysis(df_service, service_type)

            retention_matrix.to_excel(writer, sheet_name=f"{service_type}_Retention")
            revenue_matrix.to_excel(writer, sheet_name=f"{service_type}_Revenue")

        workbook = writer.book
        for sheet_name in writer.sheets:
            sheet = writer.sheets[sheet_name]
            if sheet_name.endswith("_Retention"):
                for row in sheet.iter_rows(
                    min_row=2, max_row=sheet.max_row,
                    min_col=2, max_col=sheet.max_column - 1
                ):
                    for cell in row:
                        if isinstance(cell.value, (int, float)):
                            cell.number_format = numbers.FORMAT_PERCENTAGE_00
            elif sheet_name.endswith("_Revenue"):
                for row in sheet.iter_rows(
                    min_row=2, max_row=sheet.max_row,
                    min_col=2, max_col=sheet.max_column
                ):
                    for cell in row:
                        if isinstance(cell.value, (int, float)):
                            cell.number_format = "#,##0.00 ₽"

    print(f"OK: Данные экспортированы в '{args.output}'.")


if __name__ == "__main__":
    main()

#TITLE: Zone/date sorter (chunked CSV)
#INPUT_HINT: Загрузите input.csv (UTF-8). Ожидаемые колонки: 'Зона', 'зона/дата', 'количество'. Разделитель по умолчанию: ','.
#OUTPUT_EXT: .csv

import argparse

import pandas as pd
from tqdm import tqdm


def process_data(input_path: str, output_path: str, sep: str, encoding: str, chunksize: int):
    reader = pd.read_csv(
        input_path,
        dtype={"Зона": "string", "зона/дата": "string", "количество": "float64"},
        chunksize=chunksize,
        engine="python",
        sep=sep,
        encoding=encoding,
    )

    first_chunk = True
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        for chunk in tqdm(reader, desc="Обработка"):
            for col in ("Зона", "зона/дата", "количество"):
                if col not in chunk.columns:
                    raise SystemExit(f"В CSV нет колонки '{col}'. Найдено: {list(chunk.columns)}")

            reference = chunk["Зона"].astype("string").tolist()
            data_map = (
                chunk.drop_duplicates("зона/дата")
                .set_index("зона/дата")["количество"]
                .to_dict()
            )

            result = pd.DataFrame(
                {
                    "Зона": pd.Series(reference, dtype="string"),
                    "зона/дата": pd.Series(reference, dtype="string").map(data_map),
                    "количество": chunk["количество"].astype("float64"),
                }
            )

            result.to_csv(
                f,
                header=first_chunk,
                index=False,
                lineterminator="\n",
            )
            first_chunk = False


def main():
    ap = argparse.ArgumentParser(description="Chunked CSV processing to sorted_result.csv")
    ap.add_argument("--input", required=True, help="Путь к input.csv")
    ap.add_argument("--output", required=True, help="Путь к result.csv")
    ap.add_argument("--sep", default=",", help="Разделитель CSV (default: ',')")
    ap.add_argument("--encoding", default="utf-8", help="Кодировка (default: utf-8)")
    ap.add_argument("--chunksize", type=int, default=10000, help="Размер чанка (default: 10000)")
    args = ap.parse_args()

    process_data(args.input, args.output, args.sep, args.encoding, args.chunksize)
    print(f"OK: файл создан: {args.output}")


if __name__ == "__main__":
    main()

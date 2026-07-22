#TITLE: Domains migration report (in/out -> SpaceWeb)
#INPUT_HINT: Загрузите .zip с файлами domains_in.txt и domains_out.txt (в корне архива). Формат строк — как в исходных выгрузках (TSV).
#OUTPUT_EXT: .xlsx

import argparse
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

SOURCE_PROVIDERS = [
    "TIMEWEB",
    "BeGet",
    "SPRINTHOST.RU",
    "Tilda Publishing",
    "Selectel",
    "Yandex",
    "McHost",
    "Jino",
    "DigitalOcean",
    "masterhost",
    "internet-pro",
    "ihc.ru",
    "vkcs",
    "adminvps",
]
TARGET_PROVIDER = "SpaceWeb"
PROVIDER_ALIASES = {
    ".masterhost": "masterhost",
}


def normalize_provider(provider: str):
    if not provider:
        return provider
    return PROVIDER_ALIASES.get(provider, provider)


def normalize_service(service: str):
    """Определяет тип сервиса SpaceWeb: shared или vps_dedic"""
    if not service:
        return None
    s = str(service).lower()
    if "vh" in s or "shared" in s:
        return "shared"
    if "vps" in s or "dedic" in s:
        return "vps_dedic"
    return None


def parse_line(line: str):
    parts = line.strip().split("\t")
    if len(parts) < 3:
        return None
    domain, transition, ip = parts[0], parts[1], parts[2].strip(", ")

    if "->" not in transition:
        return None

    source_part, target_part = transition.split("->", 1)
    source_part = source_part.strip().strip("'")
    target_part = target_part.strip().strip("'")

    def parse_provider(part: str):
        if "[" in part and "]" in part:
            provider = part.split("[", 1)[0].strip()
            service = part.split("[", 1)[1].split("]", 1)[0].strip()
            return provider, service
        return None, None

    src_provider, src_service = parse_provider(source_part)
    tgt_provider, tgt_service = parse_provider(target_part)

    src_provider = normalize_provider(src_provider)
    tgt_provider = normalize_provider(tgt_provider)

    return domain, ip, src_provider, src_service, tgt_provider, tgt_service


def process_file(filename: Path, direction: str = "in"):
    rows = []
    with filename.open("r", encoding="utf-8", errors="replace") as file:
        for line in file:
            parsed = parse_line(line)
            if not parsed:
                continue
            domain, ip, src_provider, src_service, tgt_provider, tgt_service = parsed

            if direction == "in":
                # Приходы: провайдер != SpaceWeb -> SpaceWeb
                if src_provider in SOURCE_PROVIDERS and tgt_provider == TARGET_PROVIDER:
                    service = normalize_service(tgt_service)  # тип по SpaceWeb (куда пришёл)
                    if service:
                        rows.append((domain, ip, src_provider, service))
            else:
                # Уходы: SpaceWeb -> другой провайдер
                if src_provider == TARGET_PROVIDER and tgt_provider in SOURCE_PROVIDERS:
                    service = normalize_service(src_service)  # тип по SpaceWeb (откуда ушёл)
                    if service:
                        rows.append((domain, ip, tgt_provider, service))
    return rows


def build_analytics(incoming, outgoing):
    rows = []
    providers = sorted({row[2] for row in incoming + outgoing})

    for provider in providers:
        shared_in = sum(1 for row in incoming if row[2] == provider and row[3] == "shared")
        vps_in = sum(1 for row in incoming if row[2] == provider and row[3] == "vps_dedic")
        shared_out = sum(1 for row in outgoing if row[2] == provider and row[3] == "shared")
        vps_out = sum(1 for row in outgoing if row[2] == provider and row[3] == "vps_dedic")
        rows.append((
            provider,
            shared_in,
            vps_in,
            shared_in + vps_in,
            shared_out,
            vps_out,
            shared_out + vps_out,
            shared_in + vps_in + shared_out + vps_out,
        ))

    rows.append((
        "TOTAL",
        sum(row[1] for row in rows),
        sum(row[2] for row in rows),
        sum(row[3] for row in rows),
        sum(row[4] for row in rows),
        sum(row[5] for row in rows),
        sum(row[6] for row in rows),
        sum(row[7] for row in rows),
    ))

    return pd.DataFrame(rows, columns=[
        "Provider",
        "Shared in",
        "VPS in",
        "Total in",
        "Shared out",
        "VPS out",
        "Total out",
        "Grand total",
    ])


def load_inputs_from_zip(zip_path: Path) -> tuple[Path, Path, tempfile.TemporaryDirectory]:
    """
    Ожидаем zip, внутри которого:
      - domains_in.txt
      - domains_out.txt
    Возвращаем пути к распакованным файлам и объект TemporaryDirectory (его нужно держать живым).
    """
    td = tempfile.TemporaryDirectory()
    out_dir = Path(td.name)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(out_dir)

    in_file = out_dir / "domains_in.txt"
    out_file = out_dir / "domains_out.txt"

    if not in_file.exists() or not out_file.exists():
        present = sorted([p.name for p in out_dir.rglob("*") if p.is_file()])
        raise SystemExit(
            "В архиве не найдены domains_in.txt и/или domains_out.txt. "
            f"Найденные файлы: {present}"
        )
    return in_file, out_file, td


def main():
    parser = argparse.ArgumentParser(description="Domains in/out report -> Excel (4 sheets).")
    parser.add_argument("--input", required=True, help="Путь к .zip (domains_in.txt + domains_out.txt)")
    parser.add_argument("--output", required=True, help="Путь к .xlsx")
    args = parser.parse_args()

    inp = Path(args.input)
    outp = Path(args.output)

    if not inp.exists():
        raise SystemExit(f"Input not found: {inp}")

    if inp.suffix.lower() != ".zip":
        raise SystemExit("Ожидается .zip с domains_in.txt и domains_out.txt")

    domains_in, domains_out, td = load_inputs_from_zip(inp)
    try:
        incoming = process_file(domains_in, "in")
        outgoing = process_file(domains_out, "out")

        shared_in = pd.DataFrame([r for r in incoming if r[3] == "shared"],
                                 columns=["Domain", "Original IP", "From Provider", "Service"])
        vps_in = pd.DataFrame([r for r in incoming if r[3] == "vps_dedic"],
                              columns=["Domain", "Original IP", "From Provider", "Service"])
        shared_out = pd.DataFrame([r for r in outgoing if r[3] == "shared"],
                                  columns=["Domain", "Original IP", "To Provider", "Service"])
        vps_out = pd.DataFrame([r for r in outgoing if r[3] == "vps_dedic"],
                               columns=["Domain", "Original IP", "To Provider", "Service"])

        for df, provider_col in (
            (shared_out, "To Provider"),
            (vps_out, "To Provider"),
            (shared_in, "From Provider"),
            (vps_in, "From Provider"),
        ):
            df.sort_values([provider_col, "Domain"], inplace=True, ignore_index=True)

        analytics = build_analytics(incoming, outgoing)

        outp.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(outp) as writer:
            shared_out.to_excel(writer, sheet_name="Shared out", index=False)
            vps_out.to_excel(writer, sheet_name="VPS out", index=False)
            shared_in.to_excel(writer, sheet_name="Shared in", index=False)
            vps_in.to_excel(writer, sheet_name="VPS in", index=False)
            analytics.to_excel(writer, sheet_name="Analytics", index=False)

        print(f"OK: создан файл {outp}")
    finally:
        td.cleanup()


if __name__ == "__main__":
    main()

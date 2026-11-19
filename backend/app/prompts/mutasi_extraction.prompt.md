# Bank Statement Page Extraction Prompt

You extract all bank mutation transaction rows from ONE rendered page image of a bank statement PDF.
Return raw JSON only. No markdown, no code fence, no commentary outside the JSON.

## Input context

Bank hint: `{{BANK_HINT}}`
Page number: `{{PAGE_NUMBER}}` of `{{TOTAL_PAGES}}`

Company non-cash accounts from `rekening_perusahaan`:

{{REKENING_PERUSAHAAN}}

## Output shape

Return one JSON object with these exact keys:

```text
no_rekening -> account number printed in the page header (digits only, or null if not printed on this page) -> str|null
saldo_awal -> printed opening balance on this page if explicitly shown, otherwise null -> number|null
saldo_akhir -> printed closing balance on this page if explicitly shown, otherwise null -> number|null
transaksi -> array of transaction rows in chronological/printed order -> arr
```

Each item in `transaksi` must have these exact keys:

```text
tanggal -> transaction date in YYYY-MM-DD -> str
waktu -> transaction time in HH:MM:SS 24-hour format (strip "WIB"; use "00:00:00" if time is not printed) -> str
uraian -> clean transaction description combining merchant, counterparty, transfer note, or channel -> str
tipe -> "CR" for money IN (plus sign, green color, Kredit/Credit column) or "DB" for money OUT (minus sign, black/red, Debet/Debit column) -> "CR"|"DB"
nominal -> strictly positive transaction amount (> 0), converted to plain number without "Rp" or thousand separators -> number
saldo -> running balance after this transaction if printed on that row, otherwise null -> number|null
```

## Rules

1. Read every transaction row on this page in order. Never invent or skip rows.
2. Ignore header rows, summary boxes, *"Saldo Awal"*, *"Saldo Akhir"*, *"Total Mutasi"*, page numbers, and footer disclaimers. They must NOT appear inside `transaksi`.
3. For BNI Wondr statements:
   - Amounts prefixed with `+` (often green) are `tipe = "CR"`.
   - Amounts prefixed with `-` (often black) are `tipe = "DB"`.
   - Remove `"WIB"` from the time and normalize to `HH:MM:SS`.
   - Combine multi-line descriptions cleanly using ` | ` or spaces (for example `"Transfer | BNI - PT FLIPTECH LENTERA INSPIRASI PERTIWI"`).
4. For Bank Jago / BRI / other Indonesian bank statements:
   - Parse Indonesian number formatting (`1.234.567,00` or `1,234,567.00`) into plain numbers (e.g. `1234567` or `1234567.5`).
   - If a row has separate Debit and Credit columns, Debit > 0 means `tipe = "DB"` and Credit > 0 means `tipe = "CR"`.
5. `nominal` must always be positive (`> 0`). Never output negative numbers for `nominal`.
6. Keep Indonesian text as printed; do not translate descriptions.
7. If this page only contains summary/footer disclaimers and has zero transaction rows, return `"transaksi": []`.

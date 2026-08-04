# Tuesday Drivers List vs. SIGN IN Master Log — Cross-Check

**Master sign-in log** (Google Drive, SIGN IN, last edited 2026-05-11 19:18 UTC): Tuesday = column 'T'.
**Routes / drivers list** (GOJ_Master_Routes.json T1+T2): used to build today's 3 PM PDFs.

## Counts

| Source | Shift 1 | Shift 2 | Total |
|---|---:|---:|---:|
| Master log (T=1 / T=2) | 83 | 59 | 142 |
| Drivers / routes | 88 | 49 | 137 |
| **Δ (routes − master)** | **+5** | **-10** | **-5** |

Master log also flags **19 client(s) as currently OFF Tuesday** (value like `0(1)` or `0(2)` meaning the shift is paused — vacation/hospital/etc.).

## 1) Shift mismatches — on a different shift in the routes than the master log

| Client | Master log says | Drivers list has |
|---|---|---|
| Bekerman Alla | S2 | S1 |
| Gadilova Nina | S1 | S2 |
| Gukovskaja Natasha V | S2 | S1 |
| Kagan Dina | S1 | S2 |
| Katsen Natalia | S2 | S1 |
| Likhtenshteyn Milya | S2 | S1 |
| Lvova Tamara | S2 | S1 |
| Rozenberg Larisa | S2 | S1 |
| Rudaya Nina | S2 | S1 |
| Serhiyenko Oleksandra | S1 | S2 |
| Sivak Svetlana | S1 | S2 |

## 2) On the SIGN IN master log for Tuesday but MISSING from the drivers list

**Master S1, not on any route (10):**
  - Fishman Mera
  - Goryachkovskaya Svetlana
  - Goryachkovsky Alexandr
  - Krupnik Eduard
  - Lurye Frida
  - Magalnik Malvina
  - Perepelitsa Nina
  - Shulkin Faina
  - Starikov Brayna
  - Syrtsova Nina

**Master S2, not on any route (9):**
  - Fridman Mikhail
  - Gurevich Emma
  - Kravets Aron
  - Leykina Margatita
  - Lysenko Tetiana
  - Matanseva Ofelia
  - Milshteyn Lizaveta
  - Rukhlevich Svetlana
  - Solovyeva Svetlana

## 3) On the drivers list but NOT scheduled for Tuesday in the master log

(Either marked OFF — `0(1)/0(2)` — or absent from the master entirely.)

**Routes S1, not active on master Tuesday (12):**
  - Belopolskaya Svitlana  — master flag: `0(2)` (currently off)
  - Breicher Larisa  — master flag: `0(1)` (currently off)
  - Brikker Ella  — master flag: `0(1)` (currently off)
  - Khalfin Inna  — _not in master log at all_
  - Krasnov Boris  — master flag: `0(1)` (currently off)
  - Krasnov Valerina  — master flag: `0(1)` (currently off)
  - Kravets Sima  — master flag: `0(1)` (currently off)
  - Meltser Eugene  — master flag: `0(1)` (currently off)
  - Meltser Larisa  — master flag: `0(1)` (currently off)
  - Nesterova Lyudmila  — master flag: `0(2)` (currently off)
  - Tokar Polina  — master flag: `0(1)` (currently off)
  - Umanskiy Boris  — master flag: `0(1)` (currently off)

**Routes S2, not active on master Tuesday (2):**
  - Liberman Simon  — master flag: `0(2)` (currently off)
  - Melamud Klara  — master flag: `0(2)` (currently off)

## Summary

- ✅ Match on correct shift: **69** S1 clients + **43** S2 clients = 112.
- 🔀 Shift mismatches (wrong shift on drivers list): **11**.
- ➖ Missing from drivers list: **10 S1 + 9 S2 = 19** clients.
- ➕ Extra on drivers list (off / not in master): **12 S1 + 2 S2 = 14** clients.
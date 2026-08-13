# Representative open data used by CarePath Tokyo

This list is derived directly from `data/tokyo/sources.json`. It contains only sources present in the submitted implementation.

| # | Source ID | Dataset | Publisher | Product use | Source date | Licence |
| ---: | --- | --- | --- | --- | --- | --- |
| 1 | `mhlw-medical-hospitals-20260601` | 医療情報ネットのオープンデータ 2026-06-01 病院（施設票） | Ministry of Health, Labour and Welfare | `healthcare` hospital navigation | 2026-06-01 | Public Data License 1.0 |
| 2 | `mhlw-medical-clinics-20260601` | 医療情報ネットのオープンデータ 2026-06-01 診療所（施設票） | Ministry of Health, Labour and Welfare | `healthcare` clinic navigation | 2026-06-01 | Public Data License 1.0 |
| 3 | `koto-cooling-shelters` | クーリングシェルター(指定暑熱避難施設)一覧 | Koto City | `cooling_shelter` navigation | 2026-02-06 | CC BY 4.0 |
| 4 | `tokyo-child-family-support-centres-202510` | 社会福祉施設等一覧 子供家庭支援センター | Tokyo Bureau of Social Welfare | `family_support` navigation | 2025-10-01 | CC BY 4.0 |
| 5 | `tokyo-mental-health-welfare-centres-202510` | 社会福祉施設等一覧 精神保健福祉センター | Tokyo Bureau of Social Welfare | `mental_health_support` navigation | 2025-10-01 | CC BY 4.0 |

## Canonical catalogue/source links

1. MHLW Medical Information Net open data catalogue: https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/kenkou_iryou/iryou/newpage_43373.html
2. Koto Cooling Shelter dataset in the Tokyo Open Data Catalog: https://catalog.data.metro.tokyo.lg.jp/dataset/t131083d3100000016
3. Tokyo social-welfare facilities dataset in the Tokyo Open Data Catalog: https://catalog.data.metro.tokyo.lg.jp/dataset/t000054d0000000374

The hospital and clinic entries share the MHLW catalogue, while the two welfare subsets share the Tokyo catalogue dataset. They remain separate representative dataset entries because they are separately ingested resource types in the product.

## Claim boundary

- The service does not claim that any listed facility is open, has capacity or accepts patients in real time unless the source explicitly provides a current value.
- Language support is shown only when the source reports it.
- Missing access/contact/eligibility fields remain unknown.
- The source inventory, retrieval dates, adapters, licences and freshness policy remain machine-readable in `data/tokyo/sources.json`.

# Scenario catalogue: multi-scenario environmental WSN

Common network for every scenario: the RL-Hybrid model of `[Config V2_200Node_Environmental]` with N = 200 (validated reference) or N = 500 nodes. That means a 600 × 50 m area with one BS at (600, 25) m, 500 rounds, 2 J per node, the same node positions and the same routing configuration. Every node senses and forwards, and there are no relay-only nodes. Only the application layer (what is measured, how often, how much is sent) differs between scenarios.

Exact field definitions are in `SENSOR_PARAMETER_MATRIX.csv`, generated from `dataset_metadata/sensor_profiles.json`.

| | Scenario | Transmitted fields | Data (N = 200 / 500) | Nodes | Reporting |
|---|---|---|---|---|---|
| A | River water quality (Periyar) | temperature_C, pH, conductivity_uScm, TDS_mgL (DO_mgL is read locally for the DO < 4 mg/L alarm, not transmitted) | **Real** KSPCB, 10 station streams + 190 / 490 replay nodes | 200 / 500 | every 2 rounds; every round while an alarm is active |
| B | Industrial effluent / wastewater | temperature_C, pH, conductivity_uScm, TDS_mgL, DO_mgL, turbidity_NTU, COD_mgL, BOD_mgL, NH3N_mgL | **Synthetic** (20 virtual outfalls × 10 / 25 nodes) | 200 / 500 | every round (hourly compliance), alarms flagged priority |
| C | Ambient air quality | PM25_ugm3, PM10_ugm3, CO_mgm3, NO2_ugm3, SO2_ugm3, O3_ugm3, temperature_C, RH_pct, wind_ms | **Real** UCI Beijing hourly data, 12 station streams + 188 / 488 replay nodes | 200 / 500 | every round (hourly averages) |
| D | Soil / agriculture | VWC_pct, soil_temperature_C, bulk_EC_dSm (continuous); soil_pH, N_mgkg, P_mgkg, K_mgkg (once per 24 rounds) | **Synthetic** (10 virtual fields × 20 / 50 nodes) | 200 / 500 | every 4 rounds; chemistry every 24 rounds; every round while an alarm is active |
| E | Mixed heterogeneous | each node keeps its own profile's fields | 50 / 125 of each profile (water always includes the 10 real stations), scaled from the configured split | 200 / 500 | each node follows its profile |

## A: River water quality

- **Real data:** KSPCB "Analysis report of River Periyar", January–July 2025. The CSV is the unchanged MATLAB V2 loader table `data/v2_consdata_loaded.csv` (workbook MD5 `6100b728…`, not touched).
- **What goes into the dataset:** the measurement rows are byte-identical to the validated 200-node OMNeT++ workload (96,500 reports). That workload carries Temperature, pH, Conductivity and TDS, as in MATLAB `create_periyar_workload_continuous.m`.
- **Node mapping:** nodes 1–10 are the 10 station streams. Node k > 10 is a virtual replay of station ((k−1) mod 10)+1.
- **Dissolved oxygen (DO):** the MATLAB loader reads DO but the workload never uses it.
  - Of the 1,273 loader records, 390 are NaN and 328 are above 20 mg/L (up to 11,404, an extraction or unit error at 6 stations).
  - DO is kept as an extension column only. A value is valid if 0 < DO ≤ 15 mg/L; anything else is flagged `DO_invalid_value`.
  - DO is not in the payload. The payload keeps the MATLAB V2 four-field workload, and the loader's DO column first needs a review of the workbook-to-loader preprocessing.
  - DO is still measured locally. Every water node reads its DO probe each round for the CPCB alarm DO < 4 mg/L (valid values only).
    - At 200 nodes this alarm alone raises 3,060 alarm rows and 1,560 extra reports out of 68,700.
    - The probe's energy (4 × 49.5 mJ = 198 mJ per node-round, 32.5 % of the water ledger) stays in the sensing ledger.
    - The analysis reports it separately as local-only sensing energy.
- **Turbidity:** excluded. The workbook's Turbidity rows hold 1,654 `*` cells (turbidity meter out of order) and 35 `A` cells, and no numeric reading, so no value was fabricated.
- **How it differs from the others:** the data are daily laboratory grab samples, so values are held between sampling dates and change in steps. Alarms come from the CPCB designated-best-use criteria:
  - pH outside 6.5–8.5 (Class B);
  - EC above 2,250 µS/cm (Class E).

  The downstream stations are brackish (up to 82,362 µS/cm at Pathalam Bund D/S), so 40.8% of node-rounds are in alarm. Alarms therefore drive water traffic.

## B: Industrial effluent

- **Why it differs from river monitoring:**
  - It is a point source with high, fast-changing organic load (COD, BOD, ammonia).
  - It has a regulatory pass/fail purpose under the Environment (Protection) Rules 1986, Schedule VI, inland surface water limits: pH 5.5–9.0, BOD 30 mg/L, COD 250 mg/L, ammoniacal N 50 mg/L.
  - Abnormal discharges cause sudden, simultaneous excursions at all sensors downstream of an outfall.
- **No verified public dataset with clear reuse terms was found:**
  - CPCB online monitoring (OCEMS) data are not openly licensed.
  - The UCI "Water Treatment Plant" set is a 1990s daily inflow/outflow series. It lacks DO, turbidity and ammonia, so it was not used.
- **Synthetic model** (deterministic, seed 2101):
  - **Sources:** 20 outfalls, each with its own baseline. COD is 80–180 mg/L, and BOD is set as a fraction of COD (0.12–0.18).
  - **Time behaviour:** a diurnal production cycle, plus AR(1) multiplicative noise in log space, so values are always positive.
  - **Related fields:** TDS = (0.60–0.70) × EC, and DO = DO saturation at the water temperature × an organic-load factor.
  - **Events:** about 2.5 abnormal discharges per outfall (2–10 h, COD × 2.5–6, pH ±1.5–3, EC × 1.3–2.5), plus treatment upsets in half of the outfalls (24–48 h, COD × 1.5–2).
  - **Node behaviour:** each node sees its outfall's events attenuated (× 0.6–1.0) and lagged by 0–2 h.
  - **Faults:** rare COD sensor spikes, sensor outages of 3–12 rounds, and 0.2% missing single fields.

## C: Air quality

- **Real data:** UCI Beijing Multi-Site Air Quality (Chen 2017, DOI 10.24432/C5RK5G, CC BY 4.0). The window is 500 consecutive hours from 2016-12-01 00:00, which contains the December 2016 haze episode (hourly PM2.5 up to 646 µg/m³).
- **Unit conversions:**
  - CO: the source gives µg/m³; the dataset stores mg/m³ (÷ 1000).
  - RH: the source has no RH. It is derived from temperature and dew point with the Magnus formula (17.625 / 243.04 °C) and labelled derived.
  - All other fields keep the source units (µg/m³, °C, m/s).
- **Kept as recorded:** NA values stay missing. In 332 node-rounds PM10 < PM2.5 in the source; these are flagged, not altered.
- **No synthetic events added:** none were injected into real data. Traffic-related and pollution events are observed and labelled from the data:
  - `observed_no2_peak_rush_hour`: NO₂ above 80 µg/m³ at 07–09 h or 17–20 h;
  - `observed_pm_episode`: PM2.5 above 150 µg/m³.
- **Alarms:** India NAAQS 2009. The 24-hour limits are applied to hourly values as a screening trigger.

## D: Soil / agriculture

- **Synthetic model** (seed 2102):
  - Hourly root-zone water balance over 300 mm: regional rainfall (4 storms), diurnal potential evapotranspiration of about 4–5 mm/day, drainage above field capacity, and morning irrigation when moisture falls below a trigger.
  - Bounds keep VWC between the residual and saturation values, inside 0–100%.
  - Soil temperature follows a damped diurnal wave and cools after wetting.
  - Bulk EC = pore-water EC × θ^1.5 and rises after fertiliser.
  - Soil pH starts at 4.8–6.5 (acidic, as is typical of Kerala soils) and drops slightly after fertiliser.
  - N leaches with cumulative rain; P and K step up after fertiliser.
- **Continuous vs occasional:** VWC, temperature and EC come from one probe reading every 30 min. pH and N/P/K are chemistry readings taken once per 24 rounds; in other rounds those cells are empty, flagged `chem_not_scheduled`, never 0.

## E: Mixed

- **Node map:** `data/scenarios/mixed_environment_<N>/node_map.csv` gives each node its profile. Nodes 1–10 are always water (the real stations). The other N − 10 nodes are assigned with seed 2103 to match the configured distribution (50/50/50/50 for 200 nodes, scaled to 125/125/125/125 for 500).
- **No duplicated data:** node k reads its own rows (node_id = k) from its profile's dataset. Positions, rounds and routing are therefore identical to the single-profile scenarios.

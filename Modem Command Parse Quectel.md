## Conventions

* `→` command sent
* `←` modem response
* `OK / ERROR` final status
* `-` (dash) in Quectel responses usually means **invalid / not available in the current condition**

> This file targets **Quectel LTE/5G modules** (RG50x / RM50x / RG52x / RM52x families, etc.).  
> Some formats vary by firmware. When in doubt, prefer **AT+QENG="servingcell"** as the source of truth.

---

## 1. ATI — Modem Identification

### Command

```text
ATI
```

### Purpose

Quick ID: vendor, model, firmware revision, IMEI (often shown), capability flags.

### Parsing (common fields)

| Field | Description |
| --- | --- |
| Manufacturer | Usually `Quectel` |
| Model | Module model (e.g., `RG502Q-EA`, `RM502Q-AE`) |
| Revision | Firmware build / release string |
| IMEI | Device unique identifier |

---

## 2. Basic Identity (3GPP) — Vendor / Model / Firmware / IMEI

### Commands

```text
AT+CGMI      // Manufacturer
AT+CGMM      // Model
AT+CGMR      // Firmware revision
AT+GSN       // IMEI (may also work as AT+CGSN)
```

### Parsing

* Keep these as **strings** (they can contain build suffixes)
* IMEI is a 15‑digit numeric string

---

## 3. SIM / Subscription — PIN, ICCID, IMSI

### Commands

```text
AT+CPIN?     // SIM ready? PIN needed?
AT+QCCID     // ICCID (SIM serial)
AT+CIMI      // IMSI
```

### Examples (typical)

```text
→ AT+CPIN?
← +CPIN: READY
← OK
```

```text
→ AT+QCCID
← +QCCID: 8939XXXXXXXXXXXXXXX
← OK
```

### Parsing

| Command | Key fields |
| --- | --- |
| `AT+CPIN?` | `READY`, `SIM PIN`, `SIM PUK`, etc. |
| `AT+QCCID` | ICCID string |
| `AT+CIMI` | IMSI string |

---

## 4. Registration Status — LTE / 5G

### Commands (common)

```text
AT+CREG?     // 2G/3G registration
AT+CGREG?    // GPRS/EDGE registration
AT+CEREG?    // LTE registration (EPS)
```

### Optional (module/firmware dependent)

```text
AT+C5GREG?   // 5G registration (if supported)
```

### Parsing

3GPP registration responses are generally:

```text
+<X>REG: <n>,<stat>[,...]
```

Where `<stat>` typically means:

| stat | Meaning |
| ---: | --- |
| 0 | Not registered, not searching |
| 1 | Registered (home) |
| 2 | Not registered, searching |
| 3 | Registration denied |
| 4 | Unknown |
| 5 | Registered (roaming) |

---

## 5. Operator / RAT / Band (Quick View)

### 5.1 AT+QNWINFO — Current Access Technology & Band

```text
AT+QNWINFO
```

### Example (from vendor/router docs)

```text
→ AT+QNWINFO
← +QNWINFO: "LTE","24701","LTE BAND 20",6300
← OK
```

### Parsing

| Position | Field | Notes |
| ---: | --- | --- |
| 1 | RAT / access tech | e.g. `LTE`, `NR5G`, `eMTC` |
| 2 | Operator (numeric) | MCC+MNC (or operator numeric) |
| 3 | Band string | e.g. `LTE BAND 20` |
| 4 | Channel | EARFCN/ARFCN (integer) |

> `AT+QNWINFO` is widely available, but not always present on every 5G firmware branch.

### 5.2 AT+COPS? — Operator Selection

```text
AT+COPS?
```

Parse the operator numeric/name according to the configured format.

---

## 6. Signal Basics — CSQ / CESQ / QCSQ

### 6.1 AT+CSQ (Classic)

```text
AT+CSQ
```

Returns RSSI & BER (coarse; not ideal for LTE/5G dashboards).

### 6.2 AT+CESQ (Better, standardized)

```text
AT+CESQ
```

Gives technology‑aware quality indexes (still needs conversion tables).

### 6.3 AT+QCSQ (Quectel extended, recommended quick KPI)

```text
AT+QCSQ
```

### Example (LTE)

```text
→ AT+QCSQ
← +QCSQ: "LTE",-52,-81,195,-10
← OK
```

### Parsing (per sysmode)

For LTE the values are:

| Field | Meaning |
| --- | --- |
| `lte_rssi` | RSSI (dBm) |
| `lte_rsrp` | RSRP (dBm) |
| `lte_sinr` | SINR (often in 0.1 dB or vendor-defined units; treat as integer and verify per firmware) |
| `lte_rsrq` | RSRQ (dB) |

If the module is not camped or mode is unknown, `NOSERVICE` can be returned.

---

## 7. Serving Cell (Full Details) — AT+QENG="servingcell"

```text
AT+QENG="servingcell"
```

### Purpose

This is the **main command** to parse for dashboards:

* LTE cell ID / TAC / band / EARFCN / PCI
* LTE RSRP/RSRQ/RSSI/SINR + CQI + TX power
* 5G NSA (ENDC) NR metrics (RSRP/RSRQ/SINR + NR ARFCN/band/bandwidth/SCS)
* 5G SA metrics (RSRP/RSRQ/SINR + NR ARFCN/band/bandwidth/SCS + TAC + cellID)

### Formats (as documented)

#### LTE mode

```text
+QENG: "servingcell",<state>,"LTE",<is_tdd>,<MCC>,<MNC>,<cellID>,<PCID>,<earfcn>,<freq_band_ind>,<UL_bandwidth>,<DL_bandwidth>,<TAC>,<RSRP>,<RSRQ>,<RSSI>,<SINR>,<CQI>,<tx_power>,<srxlev>
```

#### EN‑DC (LTE + NR5G NSA)

```text
+QENG: "servingcell",<state>
+QENG: "LTE",<is_tdd>,<MCC>,<MNC>,<cellID>,<PCID>,<earfcn>,<freq_band_ind>,<UL_bandwidth>,<DL_bandwidth>,<TAC>,<RSRP>,<RSRQ>,<RSSI>,<SINR>,<CQI>,<tx_power>,<srxlev>
+QENG: "NR5G-NSA",<MCC>,<MNC>,<PCID>,<RSRP>,<SINR>,<RSRQ>,<ARFCN>,<band>,<NR_DL_bandwidth>,<scs>
```

#### SA (NR5G‑SA)

```text
+QENG: "servingcell",<state>,"NR5G-SA",<duplex_mode>,<MCC>,<MNC>,<cellID>,<PCID>,<TAC>,<ARFCN>,<band>,<NR_DL_bandwidth>,<RSRP>,<RSRQ>,<SINR>,<scs>,<srxlev>
```

### Example outputs (from the manual)

**LTE:**

```text
+QENG: "servingcell","NOCONN","LTE","FDD",460,01,5F1EA15,12,1650,3,5,5,DE10,-100,-12,-68,11,-,-,27
OK
```

**LTE + NR (NSA / EN‑DC):**

```text
+QENG: "servingcell","NOCONN"
+QENG: "LTE","FDD",460,01,5F1EA15,12,1650,3,5,5,DE10,-99,-12,-67,11,9,230,-
+QENG:"NR5G-NSA",460,01,747,-71,13,-11,627264,78,12,1
OK
```

**NR SA:**

```text
+QENG: "servingcell","NOCONN","NR5G-SA","TDD",460,01,9013B004,299,690E0F,633984,78,12,-107,-13,2,1,-
OK
```

### Field Parsing Cheat‑Sheet

#### LTE fields

| Field | Type | Notes |
| --- | --- | --- |
| `<state>` | string | `NOCONN`, `CONNECT`, etc. |
| `<is_tdd>` | string | `FDD`/`TDD` (name varies; manual calls it `<is_tdd>`) |
| `<MCC>,<MNC>` | int | Operator codes |
| `<cellID>` | hex string | Convert hex → int if needed |
| `<PCID>` | int | PCI |
| `<earfcn>` | int | LTE EARFCN |
| `<freq_band_ind>` | int | LTE band number |
| `<UL_bandwidth>,<DL_bandwidth>` | int | Usually 1.4/3/5/10/15/20 MHz encoded values (module-defined) |
| `<TAC>` | hex string | Convert hex → int if needed |
| `<RSRP>,<RSRQ>,<RSSI>` | int | dBm / dB (as printed) |
| `<SINR>` | int | dB (as printed) |
| `<CQI>` | int or `-` | 0–15 typical |
| `<tx_power>` | int or `-` | TX power (unit per firmware; often dBm) |
| `<srxlev>` | int or `-` | rx level index |

#### NR5G‑NSA fields

| Field | Type | Notes |
| --- | --- | --- |
| `<PCID>` | int | NR PCI |
| `<RSRP>,<RSRQ>` | int | dBm / dB (as printed) |
| `<SINR>` | int | dB (as printed) |
| `<ARFCN>` | int | NR‑ARFCN |
| `<band>` | int | NR band number (e.g. 78 for n78) |
| `<NR_DL_bandwidth>` | int | bandwidth code (see AT+QCAINFO table for common codes) |
| `<scs>` | int | sub‑carrier spacing index |

#### NR5G‑SA fields

Same idea as NSA, but includes `<cellID>` and `<TAC>` and `<duplex_mode>`.

---

## 8. Neighbour Cells — AT+QENG="neighbourcell"

```text
AT+QENG="neighbourcell"
```

### Example (LTE neighbour cells)

```text
+QENG: "neighbourcell intra","LTE",38950,276,-3,-88,-65,0,37,7,16,6,44
+QENG: "neighbourcell inter","LTE",39148,-,-,-,-,-,37,0,30,7
+QENG: "neighbourcell inter","LTE",37900,-,-,-,-,-,0,0,30,6
OK
```

### Parsing tips

* The first token tells you **scope**: `intra` (same frequency), `inter` (different frequency), etc.
* Dashes mean the value is not valid in the current condition.
* Use this mainly for:
  * discovering candidate EARFCNs/PCIs for locking
  * scoring multi-cell environments

---

## 9. Carrier Aggregation — AT+QCAINFO

```text
AT+QCAINFO
```

### Purpose

Shows the LTE PCC/SCC(s) (and, in EN‑DC, NR component carriers too).

### Formats (documented)

**LTE mode:**

```text
+QCAINFO: "PCC",<freq>,<bandwidth>,<band>,<pcell_state>,<PCID>,<RSRP>,<RSRQ>,<RSSI>,<RSSNR>
[+QCAINFO: "SCC",<freq>,<bandwidth>,<band>,<scell_state>,<PCID>,<RSRP>,<RSRQ>,<RSSI>,<RSSNR>,<UL_configured>,<UL_bandwidth>,<UL_EARFCN>]
...
OK
```

**EN‑DC mode:**

Same as LTE, plus possible NR SCC lines like:

```text
+QCAINFO: "SCC",<freq>,<NR_DL_bandwidth>,<NR_band>,<PCID>
```

### Example

```text
AT+QCAINFO
+QCAINFO: "PCC",300,100,"LTE BAND 1",1,23,-66,-12,-34,30
+QCAINFO: "SCC",1575,100,"LTE BAND 3",2,43,-64,-7,-24,30,0,-,-
OK
```

### Parsing

| Field | Notes |
| --- | --- |
| `"PCC"/"SCC"` | primary/secondary component carrier |
| `<freq>` | channel/frequency index (module-defined) |
| `<bandwidth>` | LTE bandwidth code |
| `<band>` | a human band string (`"LTE BAND 3"`, `"NR5G BAND 78"`, …) |
| `<RSRP/RSRQ/RSSI/RSSNR>` | signal per carrier |

---

## 10. Temperature — AT+QTEMP

```text
AT+QTEMP
```

### Purpose

Read internal temperature sensors (often PMIC, XO, PA). Some modules/firmwares return only `OK` and then report values as URC.

### Documented response format (example)

```text
+QADC: <pmic_temp>,<xo_temp>,<pa_temp>
OK
```

### Parsing

| Field | Meaning | Unit |
| --- | --- | --- |
| `<pmic_temp>` | PMIC temperature | °C |
| `<xo_temp>` | Crystal oscillator temp | °C |
| `<pa_temp>` | Power amplifier temp | °C |

### Notes

* Some firmware branches may behave differently (e.g. temperature delivered as URC after `OK`).  
* If you only get `OK`, check whether your terminal/app is filtering URCs.

---

## 11. Cell Lock (LTE) — AT+QNWLOCK="common/lte"

> ⚠️ This is powerful: wrong values can push the modem into **no service** until unlocked.

### Commands

```text
AT+QNWLOCK="common/lte"                 // Query current lock
AT+QNWLOCK="common/lte",0               // Disable lock (unlock)
AT+QNWLOCK="common/lte",1,<EARFCN>,0    // Lock to EARFCN only
AT+QNWLOCK="common/lte",2,<EARFCN>,<PCI>// Lock to EARFCN + PCI
```

### Requirements / Notes

* Often you should force LTE scan mode first:

```text
AT+QCFG="nwscanmode",3
```

### Query output

```text
+QNWLOCK: "common/lte",<action>,<EARFCN>,<PCI>,<status>
OK
```

Where:

| Field | Meaning |
| --- | --- |
| `<action>` | 0=off, 1=EARFCN lock, 2=EARFCN+PCI lock |
| `<status>` | 0=finished, 1=still processing |

---

## 12. Cell Lock (NR 5G SA) — AT+QNWLOCK="common/5g" (firmware dependent)

Some Quectel 5G firmwares support a 5G SA lock form similar to:

```text
AT+QNWLOCK="common/5g",<pci>,<freq>,<scs>,<band>
```

### Tips

* Use **AT+QENG="servingcell"** (SA mode) to collect:
  * NR PCI
  * NR ARFCN
  * NR band
  * SCS
* Apply the lock, then re-check `AT+QENG="servingcell"` to confirm the same ARFCN/PCI.

> Exact `common/5g` syntax can vary by module/firmware branch. Always validate with `AT+QNWLOCK=?` first.

---

## 13. Enable/Disable 5G & Select Search Modes — AT+QNWPREFCFG (5G series)

### Common commands

```text
AT+QNWPREFCFG="mode_pref"            // Query or set mode preference (LTE/NR5G/etc)
AT+QNWPREFCFG="nr5g_disable_mode"    // Enable/disable NR (NSA/SA)
AT+QNWPREFCFG="nr5g_band"            // Query allowed NR bands (format depends on firmware)
```

### Example scenario: prefer 5G

```text
AT+QNWPREFCFG="mode_pref",LTE:NR5G
```

### Example scenario: connect only to 5G SA (typical recipe)

```text
AT+QNWPREFCFG="mode_pref",NR5G
AT+QNWPREFCFG="nr5g_disable_mode",2
```

---

## 14. Useful “Info” Commands (Quick Grab Bag)

```text
AT+QCFG="data_interface"     // Data interface selection/status (e.g., MBIM vs ECM)
AT+QCFG="usbcfg"             // USB composition/config (vendor-specific)
AT+QMBNCFG?                  // MBN config status (carrier profiles; firmware dependent)
AT+CGDCONT?                  // PDP contexts/APNs
AT+CGPADDR                   // IP address per context
```

---

## 15. Minimal Diagnostics Bundle (Copy/Paste)

When you need a quick snapshot for logs:

```text
ATI
AT+CGMI
AT+CGMM
AT+CGMR
AT+GSN
AT+CPIN?
AT+QCCID
AT+CIMI
AT+CEREG?
AT+QENG="servingcell"
AT+QCAINFO
AT+QTEMP
```

## Conventions

* `→` command sent
* `←` modem response
* `OK / ERROR` final status

---

## 1. ATI — Modem Identification

### Command

```text
ATI
```

### Example Output

```text
Manufacturer: QUALCOMM
Model: T99W175
Revision: T99W175.F0.1.0.0.9.DF.015
SVN: 01
IMEI: XXXXXXXXXXXXX
+GCAP: +CGSM
MPN: 32
OK
```

### Field Parsing

| Field        | Description              |
| ------------ | ------------------------ |
| Manufacturer | Chipset vendor           |
| Model        | Modem model              |
| Revision     | Firmware / build version |
| SVN          | Sub‑version number       |
| IMEI         | Modem unique identifier  |
| GCAP         | Legacy capability flags  |

---

## 2. AT^DEBUG? — Get Serving Cell Information

### Command

```text
AT^DEBUG?
```

### Purpose

Returns serving cell information for the current network (LTE, LTE+NR, or NR5G SA).

---

## Supported RAT Values

* `WCDMA`
* `LTE`
* `LTE+NR` (5G NSA / ENDC)
* `NR5G_SA` (5G Standalone)

---

## Parameters

| Parameter                  | Description                          |
| -------------------------- | ------------------------------------ |
| RAT                        | Radio Access Technology              |
| mcc / mnc                  | Mobile Country / Network Code        |
| band                       | Active band                          |
| band_width                 | Channel bandwidth                    |
| channel                    | EARFCN / NRARFCN                     |
| cell_id                    | Cell ID                              |
| lte_tac / nr_tac           | Tracking Area Code                   |
| tx_pwr                     | UE transmit power                    |
| pcell                      | Primary serving cell                 |
| scell                      | Secondary cell (Carrier Aggregation) |
| pci                        | Physical Cell ID                     |
| rsrp                       | Reference Signal Received Power      |
| rsrq                       | Reference Signal Received Quality    |
| rssi                       | Received Signal Strength Indicator   |
| snr                        | Signal‑to‑Noise Ratio                |
| rx_diversity               | RX chain validity bitmask            |
| lte_ant_rsrp / nr_ant_rsrp | Per‑antenna RSRP values              |

---

## Example 1 — LTE + NR (5G NSA / ENDC)

```text
AT^DEBUG?
RAT:LTE+NR
mcc:222,mnc:88
lte_cell_id:80389889
lte_tac:30648
lte_tx_pwr:9.0dBm
lte_ant_rsrp:rx_diversity:1 (-84.4dBm,NA,NA,NA)
pcell: lte_band:3 lte_band_width:20.0MHz
channel:1650 pci:28
lte_rsrp:-84.1dBm,rsrq:-13.6dB
lte_rssi:-50.6dBm,lte_snr:13.4dB
scell: lte_band:1 lte_band_width:20.0MHz
channel:100 pci:28
scell: lte_band:7 lte_band_width:20.0MHz
channel:3350 pci:85
nr_band:n78
nr_band_width:80.0MHz
nr_channel:638016
nr_pci:532
nr_rsrp:-87dBm rx_diversity:15 (-84.8,-112.4,-84.7,-116.1)
nr_rsrq:-11dB
nr_snr:29.0dB
OK
```

---

## Example 2 — NR5G SA (Standalone)

```text
AT^DEBUG?
RAT:NR5G_SA
mcc:202,mnc:01
nr_cell_id:4946788483
nr_tac:5615
nr_band:n78
nr_band_width:100.0MHz
nr_channel:634080
nr_pci:363
nr_rsrp:-83dBm rx_diversity:15 (-87.8,-83.0,-97.0,-88.7)
nr_rsrq:-11dB
nr_snr:8.5dB
OK
```
---
## Example 3 — LTE Only

```text
AT^DEBUG?
RAT:LTE
mcc:222,mnc:10
lte_cell_id:12176170
lte_tac:22097
lte_tx_pwr:18.2dBm
lte_ant_rsrp:rx_diversity:3 (-79.5dBm,-75.9dBm,NA,NA)
pcell: lte_band:1 lte_band_width:15.0MHz
channel:525 pci:263
lte_rsrp:-75.7dBm,rsrq:-10.2dB
lte_rssi:-46.6dBm,lte_snr:4.8dB
OK
```

---



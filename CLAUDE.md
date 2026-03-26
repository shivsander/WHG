# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This file contains aggregated time-series environmental sensor data from EyeSense IoT devices. There is no application source code, build system, or tests — this is a pure data repository.

## Data Organization

```
WHG/
└── WHG_data/                              # Geographic region
    └── weather_data/
        └── EYESENSE_<MAC_ID>/            # 33 sensor directories
            └── EYESENSE_<MAC_ID>-5min-<DATE_RANGE>_weather.csv
```

- Data is organized by **geographic location** (currently only `WHG`)
- Each sensor has its own directory named by MAC address (e.g., `EYESENSE_34CDB0622E8C`)
- CSV files contain 5-minute interval readings spanning June 2025 – February 2026

## CSV Schema (24 columns)

| Column           | Description                                                                                                                                         |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `index`          | Row index                                                                                                                                           |
| `name`           | Sensor MAC in format `EyeSense:34:CD:B0:62:2E:8C`                                                                                                   |
| `vtime`          | Timestamp (UTC, e.g., `2025-11-29 14:50:00+00:00`)                                                                                                  |
| `avgT`, `avgTcs` | Temperature (°C), temperature setpoint (°C)                                                                                                         |
| `avgH`           | Relative humidity (%)                                                                                                                               |
| `avgLux`         | Light level (lux)                                                                                                                                   |
| `avgRe`          | Occupancy Energy (%)                                                                                                                                |
| `avgP`           | Total Electrical Power (W)                                                                                                                          |
| `avgE`           | Total Electrical Energy (kWh)                                                                                                                       |
| `avgUV`          | UV index                                                                                                                                            |
| `avgCO2`         | CO2 concentration (ppm)                                                                                                                             |
| `avgC`, `avgrdr` | avgDutyCycle (%), occupancy fraction (&)                                                                                                            |
| `weather_*`      | Correlated external weather: temperature, humidity, pressure, wind_speed, wind_direction, cloud_cover, visibility, precipitation, code, description |

## Data Format

EyeSense CSV with 5-minute intervals:

```
vtime              — UTC timestamp
avgT               — indoor air temperature (°C) → THIS IS T_obs
avgH               — indoor relative humidity (%)
avgLux             — indoor light intensity (lux) → solar gain proxy
avgRe              — motion sensor (>15 = occupied)
avgCO2             — indoor CO2 (ppm) → ventilation proxy
avgUV              — UV index
avgP               - if large, denotes electrical heater and can be used as Pheat, if not large Pheat, this is a wet radiator system
avgC               - this is controller duty for the heater.
avgTcs             - this is the controller setpoint, good to see when the system controller requested the change and a way to know what the target temperature is. Also can be used to see estimate heater response and lag.
weather_temperature — outdoor temperature (°C) → T_out .T_out is in a staircase looking data. Use SG filter of 168 minto smooth staircase. Do this for all staircase looking weather data.
avgrdr             - fraction of occupancy for that duration of the sampling window.
weather_humidity    — outdoor RH (%)
weather_wind_speed  — wind speed (m/s)
weather_cloud_cover — cloud cover (%)
weather_precipitation — precipitation (mm)
```

For the weather data, use SG filter of 168 minutes to smooth staircase. Do this for all staircase looking weather data.
If used as a monitor, it means that avgTcs, avgC, avgP, avgE are not used. Only if it a controller, then these variables are useful. If there is a wet radiator, the avgP is not the heat input into the system.

## Key Details for Analysis

- Timestamps are UTC with timezone offset (`+00:00`)
- Many fields contain sparse/missing data (empty cells)
- Sensor readings are averaged over 5-minute windows
- Weather columns come from an external weather API correlated by time
- Sensor MAC IDs in directory names use underscores; in CSV `name` column they use colons

## Files

The folders are arranged per house, usually the last 3 numbers of the MAC xx:xx:xx is used as the house ID. If in the folder there is an EYESENSE_XXXXXXXXXXXX, this is the parent sensor and is usually placed in the corridor of the house. If the folder has a SENS_XXXXXXXXXXXX, this is a child sensor places in a room where the person live or works. This is done to understand how the house differs between measuring in a lived in space vs the corridor measurement.

## Data Patching

There will be breaks in the data, if the data break is less than 60 minutes, interpolate the data, If larger than 60 minutes, consider this as a chunk. This will allow small breaks to still allow data continuity.
Resample the data to make it consistantly 5 minute intervals.
ere
Note for this Lambeth Analysis, this is purely monitoring data, there is no control for these devices.

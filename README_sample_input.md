# Sample Input Format for Travel Parser

This document explains the expected input format for the travel parser system when using your own email inbox data.

## Sample Input File

See `sample_travel_input.csv` for a complete example of the expected format.

## Required Columns

Your input CSV file must contain exactly these columns in this order:

| Column | Description | Example | Notes |
|--------|-------------|---------|-------|
| `departure_country` | Country code or name of departure location | `GB`, `US`, `France` | Use ISO codes when possible |
| `departure_city` | City name of departure location | `London (LHR)`, `New York`, `Paris` | Airport codes in parentheses |
| `departure_date` | Departure date in YYYY-MM-DD format | `2023-02-05` | Required |
| `departure_time` | Departure time in HH:MM format | `18:25`, `14:30` | Optional, can be empty |
| `arrival_country` | Country code or name of arrival location | `QA`, `TH`, `Germany` | Use ISO codes when possible |
| `arrival_city` | City name of arrival location | `Doha (DOH)`, `Bangkok (BKK)` | Airport codes in parentheses |
| `arrival_date` | Arrival date in YYYY-MM-DD format | `2023-02-06` | Required |
| `arrival_time` | Arrival time in HH:MM format | `04:15`, `21:30` | Optional, can be empty |
| `notes` | Additional travel details | `Flight (Qatar Airways QR012)`, `Train (Eurostar)` | Transport type and details |
| `source_file` | Source of the data | `Original`, `Email_2023_01_15.eml` | Usually "Original" for manual entries |

## Data Format Guidelines

### Dates
- **Format**: `YYYY-MM-DD` (ISO 8601)
- **Examples**: `2023-02-05`, `2024-12-25`
- **Required**: Yes for both departure and arrival

### Times
- **Format**: `HH:MM` (24-hour format)
- **Examples**: `18:25`, `09:30`, `14:45`
- **Required**: No, can be empty if unknown

### Locations
- **Countries**: Use ISO country codes when possible (`GB`, `US`, `FR`, `DE`)
- **Cities**: Include airport codes in parentheses when relevant (`London (LHR)`, `Bangkok (BKK)`)
- **Unknown locations**: Use `Unknown` for missing data

### Notes
- **Transport type**: Include the method of transport (`Flight`, `Train`, `Bus`, `Car`, `Walk`)
- **Details**: Add airline, train company, or other relevant details
- **Examples**: 
  - `Flight (Qatar Airways QR012)`
  - `Train (Eurostar E3201)`
  - `Tube (Northern Line)`
  - `Bus (Arriva)`

## Example Usage

1. **Create your input file** following the format above
2. **Run the connection analysis**:
   ```bash
   python add_connection_analysis.py your_travel_data.csv
   ```
3. **View the results** in `your_travel_data_with_connections.csv`

## What the System Adds

The system will add these columns to your output file:

- `next_country_match`: ✅ if next row's departure country matches current arrival country, ❌ otherwise
- `next_city_match`: ✅ if next row's departure city matches current arrival city, ❌ otherwise

## Tips for Best Results

1. **Chronological order**: Sort your data by departure date before processing
2. **Consistent formatting**: Use the same format for similar data (e.g., always include airport codes)
3. **Complete data**: Fill in as many fields as possible for better analysis
4. **Standard codes**: Use ISO country codes and IATA airport codes when available
5. **Clear notes**: Include transport type and company details in the notes field

## Common Issues

- **Missing dates**: The system requires both departure and arrival dates
- **Inconsistent country codes**: Mixing `GB` and `United Kingdom` will cause matching issues
- **Wrong date format**: Use `YYYY-MM-DD` format, not `DD/MM/YYYY` or `MM/DD/YYYY`
- **Empty required fields**: Don't leave departure/arrival dates empty

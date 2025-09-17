# Connection Analysis Utility

This utility adds connection analysis columns to existing travel CSV files to identify whether consecutive travel entries match in country and city.

## Usage

```bash
python add_connection_analysis.py <input_csv_file>
```

## Example

```bash
python add_connection_analysis.py all-travel-20250917-2154.csv
```

This will create `all-travel-20250917-2154_with_connections.csv` with the following new columns:

- `next_country_match`: ✅ if next row's departure country matches current row's arrival country, ❌ otherwise
- `next_city_match`: ✅ if next row's departure city matches current row's arrival city, ❌ otherwise  
- `next_country`: The country code of the next row's departure location
- `next_city`: The city name of the next row's departure location

## What It Does

1. **Reads** the input CSV file
2. **Analyzes** each consecutive pair of travel entries
3. **Extracts** country codes and city names from location strings
4. **Compares** arrival location of current row with departure location of next row
5. **Adds** four new columns with the analysis results
6. **Saves** the enhanced data to a new file

## Output

The script provides:
- Real-time analysis showing which entries have matching connections
- Summary statistics of total matches found
- A new CSV file with the original data plus connection analysis columns

## Use Cases

- **Identify continuous travel**: Find entries where you stayed in the same city/country
- **Spot data quality issues**: Detect potential duplicate or overlapping entries
- **Analyze travel patterns**: Understand how often you have direct connections vs. gaps
- **Validate chronological order**: Ensure the travel data makes logical sense

#!/usr/bin/env python3
"""
Add connection analysis columns to an existing travel CSV file.
This script adds columns to check if consecutive rows match country and city.
"""

import csv
import re
import sys
from typing import List, Dict

def extract_country(location: str) -> str:
    """Extract country from location string (e.g., 'London (GB)' -> 'GB')"""
    if not location or location == 'Unknown':
        return ''
    
    # Look for country code in parentheses
    match = re.search(r'\(([A-Z]{2})\)', location)
    if match:
        return match.group(1)
    
    # If no country code, return the full location
    return location

def extract_city(location: str) -> str:
    """Extract city from location string (e.g., 'London (GB)' -> 'London')"""
    if not location or location == 'Unknown':
        return ''
    
    # Remove country code in parentheses
    city = re.sub(r'\s*\([A-Z]{2}\)', '', location).strip()
    return city

def add_connection_analysis(data: List[Dict]) -> List[Dict]:
    """Add columns to analyze connections between consecutive travel entries"""
    if not data or len(data) < 2:
        return data
    
    print("\n🔗 ANALYZING CONNECTIONS BETWEEN CONSECUTIVE ENTRIES")
    print("=" * 60)
    
    # Add connection analysis columns to each entry
    for i in range(len(data)):
        entry = data[i].copy()
        
        if i < len(data) - 1:  # Not the last entry
            next_entry = data[i + 1]
            
            # Extract country and city from current entry's ARRIVAL location
            current_arrival_country = entry.get('arrival_country', '')
            current_arrival_city = entry.get('arrival_city', '')
            
            # Extract country and city from next entry's DEPARTURE location
            next_departure_country = next_entry.get('departure_country', '')
            next_departure_city = next_entry.get('departure_city', '')
            
            # Check if countries match (arrival country == next departure country)
            country_match = current_arrival_country.lower() == next_departure_country.lower() if current_arrival_country and next_departure_country else False
            
            # Check if cities match (arrival city == next departure city)
            city_match = current_arrival_city.lower() == next_departure_city.lower() if current_arrival_city and next_departure_city else False
            
            # Add analysis columns (only the match indicators)
            entry['next_country_match'] = '✅' if country_match else '❌'
            entry['next_city_match'] = '✅' if city_match else '❌'
            
            # Log the analysis
            if country_match or city_match:
                print(f"  {i+1}. {current_arrival_city} ({current_arrival_country}) → {next_departure_city} ({next_departure_country})")
                if country_match:
                    print(f"     ✅ Country match: {current_arrival_country}")
                if city_match:
                    print(f"     ✅ City match: {current_arrival_city}")
        else:
            # Last entry - no next entry to compare
            entry['next_country_match'] = 'N/A'
            entry['next_city_match'] = 'N/A'
        
        data[i] = entry
    
    # Count matches
    country_matches = sum(1 for entry in data if entry.get('next_country_match') == '✅')
    city_matches = sum(1 for entry in data if entry.get('next_city_match') == '✅')
    
    print(f"\n📊 CONNECTION ANALYSIS SUMMARY:")
    print(f"   • Country matches: {country_matches}/{len(data)-1}")
    print(f"   • City matches: {city_matches}/{len(data)-1}")
    print(f"   • Total connections: {country_matches + city_matches}")
    
    return data

def test_connection_analysis():
    """Test the connection analysis logic with sample data"""
    print("🧪 TESTING CONNECTION ANALYSIS LOGIC")
    print("=" * 50)
    
    # Test data that should have matches
    test_data = [
        {
            'departure_country': 'GB',
            'departure_city': 'London',
            'arrival_country': 'ME', 
            'arrival_city': 'Tivat (TIV)',
            'departure_date': '2025-08-01',
            'departure_time': '11:35',
            'arrival_date': '2025-08-01',
            'arrival_time': '13:40',
            'notes': 'Flight',
            'source_file': 'test1'
        },
        {
            'departure_country': 'ME',
            'departure_city': 'Tivat (TIV)', 
            'arrival_country': 'GB',
            'arrival_city': 'London',
            'departure_date': '2025-08-07',
            'departure_time': '12:00',
            'arrival_date': '2025-08-07',
            'arrival_time': '14:00',
            'notes': 'Flight',
            'source_file': 'test2'
        },
        {
            'departure_country': 'GB',
            'departure_city': 'London',
            'arrival_country': 'ES',
            'arrival_city': 'Tenerife South',
            'departure_date': '2025-08-23',
            'departure_time': '10:45',
            'arrival_date': '2025-08-22',
            'arrival_time': '23:25',
            'notes': 'Flight',
            'source_file': 'test3'
        }
    ]
    
    # Run the analysis
    result = add_connection_analysis(test_data)
    
    # Check results
    print("\n🔍 TEST RESULTS:")
    
    # First entry: arrives in ME, next departs from ME (should match)
    assert result[0]['next_country_match'] == '✅', f"Expected ✅, got {result[0]['next_country_match']}"
    assert result[0]['next_city_match'] == '✅', f"Expected ✅, got {result[0]['next_city_match']}"
    print("✅ Test 1 passed: ME → ME country and city match")
    
    # Second entry: arrives in GB, next departs from GB (should match)
    assert result[1]['next_country_match'] == '✅', f"Expected ✅, got {result[1]['next_country_match']}"
    assert result[1]['next_city_match'] == '✅', f"Expected ✅, got {result[1]['next_city_match']}"
    print("✅ Test 2 passed: GB → GB country and city match")
    
    # Third entry: Last entry (should be N/A)
    assert result[2]['next_country_match'] == 'N/A', f"Expected N/A, got {result[2]['next_country_match']}"
    assert result[2]['next_city_match'] == 'N/A', f"Expected N/A, got {result[2]['next_city_match']}"
    print("✅ Test 3 passed: Last entry N/A")
    
    print("\n🎉 ALL TESTS PASSED!")

def main():
    if len(sys.argv) != 2:
        print("Usage: python add_connection_analysis.py <input_csv_file>")
        print("Example: python add_connection_analysis.py all-travel-20250917-2154.csv")
        print("        python add_connection_analysis.py --test")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    # Run tests if requested
    if input_file == "--test":
        test_connection_analysis()
        return
    
    output_file = input_file.replace('.csv', '_with_connections.csv')
    
    print(f"📁 Reading travel data from: {input_file}")
    
    # Read the CSV file
    data = []
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
    except FileNotFoundError:
        print(f"❌ Error: File '{input_file}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        sys.exit(1)
    
    print(f"📊 Loaded {len(data)} travel entries")
    
    # Add connection analysis
    data_with_connections = add_connection_analysis(data)
    
    # Save the updated data
    print(f"\n💾 Saving updated data to: {output_file}")
    
    # Define fieldnames including new columns
    fieldnames = [
        'departure_country', 'departure_city', 'departure_date', 'departure_time',
        'arrival_country', 'arrival_city', 'arrival_date', 'arrival_time', 'notes',
        'source_file', 'next_country_match', 'next_city_match'
    ]
    
    try:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data_with_connections)
        
        print(f"✅ Successfully saved {len(data_with_connections)} entries with connection analysis")
        print(f"📄 Output file: {output_file}")
        
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

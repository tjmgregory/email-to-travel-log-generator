#!/usr/bin/env python3
"""
Async Travel Parser - Maximum performance version with async/await and batching
"""

import os
import csv
import json
import re
import glob
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import openai
from pathlib import Path
import email
from email.header import decode_header
from bs4 import BeautifulSoup
import asyncio
import aiofiles
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
import time
import aiohttp
import logging
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load OpenAI API key
def load_openai_key():
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('OPEN_AI_KEY='):
                    return line.split('=', 1)[1].strip()
    return None

# Initialize OpenAI
openai.api_key = load_openai_key()

class AsyncTravelParser:
    def __init__(self, csv_file: str, email_dir: str, max_workers: int = None, batch_size: int = 50):
        self.csv_file = csv_file
        self.email_dir = email_dir
        self.travel_data = []
        self.gaps = []
        self.found_entries = []
        self.max_workers = max_workers or min(cpu_count(), 12)  # Increased for async
        self.batch_size = batch_size
        
    def load_travel_data(self):
        """Load existing travel data from CSV and sort chronologically"""
        print("Loading existing travel data...")
        with open(self.csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            self.travel_data = list(reader)
        
        # Normalize country codes in all entries
        print("Normalizing country codes to ISO 3166-1 alpha-2 format...")
        normalized_count = 0
        for entry in self.travel_data:
            original_departure = entry.get('departure_country', '')
            original_arrival = entry.get('arrival_country', '')
            
            normalized_entry = self.normalize_travel_entry_country_codes(entry)
            
            if (normalized_entry.get('departure_country', '') != original_departure or 
                normalized_entry.get('arrival_country', '') != original_arrival):
                normalized_count += 1
            
            # Update the entry with normalized country codes
            entry.update(normalized_entry)
        
        if normalized_count > 0:
            print(f"Normalized country codes in {normalized_count} entries")
        
        # Sort data chronologically by departure date
        self.travel_data = self.sort_travel_data_chronologically(self.travel_data)
        print(f"Loaded {len(self.travel_data)} travel entries (sorted chronologically)")
    
    def sort_travel_data_chronologically(self, travel_data):
        """Sort travel data chronologically by departure date and time"""
        def get_sort_key(entry):
            try:
                # Parse departure date
                departure_date = datetime.strptime(entry['departure_date'], '%Y-%m-%d')
                
                # Parse departure time if available
                departure_time = entry.get('departure_time', '00:00')
                if departure_time and departure_time != 'N/A' and departure_time != '':
                    try:
                        time_parts = departure_time.split(':')
                        if len(time_parts) == 2:
                            hour, minute = map(int, time_parts)
                            departure_time_obj = datetime.strptime(f"{hour:02d}:{minute:02d}", '%H:%M').time()
                        else:
                            departure_time_obj = datetime.strptime('00:00', '%H:%M').time()
                    except:
                        departure_time_obj = datetime.strptime('00:00', '%H:%M').time()
                else:
                    departure_time_obj = datetime.strptime('00:00', '%H:%M').time()
                
                # Combine date and time for sorting
                return datetime.combine(departure_date, departure_time_obj)
            except:
                # If date parsing fails, use a very early date
                return datetime(1900, 1, 1)
        
        # Sort by departure date and time
        sorted_data = sorted(travel_data, key=get_sort_key)
        
        # Verify sorting worked by checking for negative day gaps
        negative_gaps = 0
        for i in range(len(sorted_data) - 1):
            try:
                current_date = datetime.strptime(sorted_data[i]['arrival_date'], '%Y-%m-%d')
                next_date = datetime.strptime(sorted_data[i + 1]['departure_date'], '%Y-%m-%d')
                if (next_date - current_date).days < 0:
                    negative_gaps += 1
            except:
                pass
        
        if negative_gaps > 0:
            print(f"⚠️  Warning: {negative_gaps} negative day gaps detected after sorting - data may have overlapping or inconsistent dates")
        
        return sorted_data
        
    def identify_gaps(self, verbose=True):
        """Identify gaps in travel itinerary where arrival city != next departure city"""
        if verbose:
            print("🔍 IDENTIFYING GAPS IN TRAVEL ITINERARY")
            print("=" * 60)
        
        self.gaps = []
        country_gaps = 0
        city_gaps = 0
        
        for i in range(len(self.travel_data) - 1):
            current = self.travel_data[i]
            next_entry = self.travel_data[i + 1]
            
            # Extract city names (remove airport codes and country info)
            current_arrival = self.extract_city_name(current['arrival_city'])
            next_departure = self.extract_city_name(next_entry['departure_city'])
            
            # Check if there's a gap
            if current_arrival.lower() != next_departure.lower():
                # Determine gap type based on country
                current_country = current['arrival_country']
                next_country = next_entry['departure_country']
                is_country_gap = current_country.lower() != next_country.lower()
                
                gap_type = "COUNTRY" if is_country_gap else "CITY"
                priority_icon = "🔴" if is_country_gap else "🟡"
                
                gap = {
                    'gap_index': i,
                    'gap_number': len(self.gaps) + 1,
                    'current_arrival': current_arrival,
                    'current_arrival_country': current_country,
                    'current_arrival_date': current['arrival_date'],
                    'next_departure': next_departure,
                    'next_departure_country': next_country,
                    'next_departure_date': next_entry['departure_date'],
                    'gap_period': f"{current['arrival_date']} to {next_entry['departure_date']}",
                    'days_between': self.calculate_days_between(current['arrival_date'], next_entry['departure_date']),
                    'gap_type': gap_type,
                    'is_country_gap': is_country_gap
                }
                self.gaps.append(gap)
                
                if is_country_gap:
                    country_gaps += 1
                else:
                    city_gaps += 1
                
                if verbose:
                    days = gap['days_between']
                    print(f"{priority_icon} GAP #{gap['gap_number']:2d} ({gap_type}): {current_arrival} ({current_country}) → {next_departure} ({next_country}) [{days} days]")
        
        if verbose:
            print(f"\n📊 SUMMARY: Found {len(self.gaps)} gaps in travel itinerary")
            print(f"   • 🔴 Country gaps: {country_gaps} (critical for visa calculations)")
            print(f"   • 🟡 City gaps: {city_gaps} (may indicate car lifts/local transport)")
            if self.gaps:
                total_days = sum(gap['days_between'] for gap in self.gaps)
                avg_days = total_days / len(self.gaps)
                print(f"   • Total gap time: {total_days} days")
                print(f"   • Average gap: {avg_days:.1f} days")
            print("=" * 60)
        
        return self.gaps
    
    def calculate_days_between(self, date1_str, date2_str):
        """Calculate days between two date strings"""
        try:
            date1 = datetime.strptime(date1_str, '%Y-%m-%d')
            date2 = datetime.strptime(date2_str, '%Y-%m-%d')
            return (date2 - date1).days
        except:
            return 0
    
    def extract_city_name(self, city_string: str) -> str:
        """Extract city name from city string, removing airport codes and country info"""
        # Remove airport codes in parentheses
        city = re.sub(r'\s*\([^)]*\)', '', city_string)
        # Remove country info after dash
        city = city.split(' - ')[0].split(',')[0]
        return city.strip()
    
    async def parse_email_async(self, email_file: str) -> Optional[Dict]:
        """Parse email asynchronously from .eml file"""
        try:
            async with aiofiles.open(email_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
                msg = email.message_from_string(content)
            
            # Extract headers
            subject = self.decode_header(msg.get('Subject', ''))
            sender = self.decode_header(msg.get('From', ''))
            date_str = msg.get('Date', '')
            
            # Parse date
            email_date = None
            if date_str:
                try:
                    # Parse email date
                    email_date = datetime.strptime(date_str.split(',')[1].strip()[:11], '%d %b %Y')
                except:
                    try:
                        email_date = datetime.strptime(date_str.split(',')[1].strip()[:11], '%d %b %Y')
                    except:
                        pass
            
            # Extract content
            content_text = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        content_text += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    elif part.get_content_type() == "text/html":
                        html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        soup = BeautifulSoup(html_content, 'html.parser')
                        content_text += soup.get_text()
            else:
                if msg.get_content_type() == "text/plain":
                    content_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                elif msg.get_content_type() == "text/html":
                    html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    soup = BeautifulSoup(html_content, 'html.parser')
                    content_text += soup.get_text()
            
            return {
                'file': email_file,
                'subject': subject,
                'sender': sender,
                'date': email_date,
                'content': content_text.strip()
            }
            
        except Exception as e:
            return None
    
    def decode_header(self, header_value: str) -> str:
        """Decode email header value"""
        if not header_value:
            return ""
        
        decoded_parts = decode_header(header_value)
        decoded_string = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                if encoding:
                    try:
                        decoded_string += part.decode(encoding)
                    except:
                        decoded_string += part.decode('utf-8', errors='ignore')
                else:
                    decoded_string += part.decode('utf-8', errors='ignore')
            else:
                decoded_string += part
        
        return decoded_string
    
    def load_travel_keywords(self) -> List[str]:
        """Load travel keywords from file"""
        keywords_file = os.path.join(os.path.dirname(__file__), 'travel_keywords.txt')
        keywords = []
        
        try:
            with open(keywords_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if line and not line.startswith('#'):
                        keywords.append(line.lower())
        except FileNotFoundError:
            print(f"⚠️  Keywords file not found: {keywords_file}")
            # Fallback to basic keywords
            keywords = [
                'flight', 'airline', 'airport', 'departure', 'arrival', 'boarding',
                'ticket', 'booking', 'reservation', 'itinerary', 'hotel', 'travel',
                'trip', 'journey', 'vacation', 'holiday', 'tour', 'tourism'
            ]
        
        return keywords
    
    def get_gap_location_keywords(self, gaps: List[Dict]) -> List[str]:
        """Extract location keywords from gaps for enhanced email filtering"""
        gap_keywords = []
        
        for gap in gaps:
            # Add city names
            current_city = gap.get('current_arrival', '').lower().strip()
            next_city = gap.get('next_departure', '').lower().strip()
            
            if current_city:
                gap_keywords.append(current_city)
            if next_city:
                gap_keywords.append(next_city)
            
            # Add country names
            current_country = gap.get('current_arrival_country', '').lower().strip()
            next_country = gap.get('next_departure_country', '').lower().strip()
            
            if current_country:
                gap_keywords.append(current_country)
            if next_country:
                gap_keywords.append(next_country)
            
            # Add common country name variations
            country_variations = {
                'gb': ['united kingdom', 'uk', 'britain', 'england', 'scotland', 'wales'],
                'us': ['united states', 'usa', 'america'],
                'th': ['thailand'],
                'my': ['malaysia'],
                'sg': ['singapore'],
                'id': ['indonesia'],
                'ph': ['philippines'],
                'vn': ['vietnam'],
                'kh': ['cambodia'],
                'la': ['laos'],
                'mm': ['myanmar', 'burma'],
                'bn': ['brunei'],
                'fr': ['france'],
                'de': ['germany'],
                'it': ['italy'],
                'es': ['spain'],
                'nl': ['netherlands', 'holland'],
                'be': ['belgium'],
                'ch': ['switzerland'],
                'at': ['austria'],
                'dk': ['denmark'],
                'se': ['sweden'],
                'no': ['norway'],
                'fi': ['finland'],
                'pl': ['poland'],
                'cz': ['czech republic', 'czechia'],
                'hu': ['hungary'],
                'sk': ['slovakia'],
                'si': ['slovenia'],
                'hr': ['croatia'],
                'rs': ['serbia'],
                'bg': ['bulgaria'],
                'ro': ['romania'],
                'gr': ['greece'],
                'tr': ['turkey'],
                'ru': ['russia'],
                'ua': ['ukraine'],
                'by': ['belarus'],
                'lt': ['lithuania'],
                'lv': ['latvia'],
                'ee': ['estonia'],
                'ie': ['ireland'],
                'pt': ['portugal'],
                'lu': ['luxembourg'],
                'mt': ['malta'],
                'cy': ['cyprus'],
                'is': ['iceland'],
                'li': ['liechtenstein'],
                'mc': ['monaco'],
                'ad': ['andorra'],
                'sm': ['san marino'],
                'va': ['vatican'],
                'jp': ['japan'],
                'kr': ['south korea', 'korea'],
                'cn': ['china'],
                'tw': ['taiwan'],
                'hk': ['hong kong'],
                'mo': ['macau'],
                'in': ['india'],
                'pk': ['pakistan'],
                'bd': ['bangladesh'],
                'lk': ['sri lanka'],
                'mv': ['maldives'],
                'np': ['nepal'],
                'bt': ['bhutan'],
                'af': ['afghanistan'],
                'ir': ['iran'],
                'iq': ['iraq'],
                'sy': ['syria'],
                'lb': ['lebanon'],
                'jo': ['jordan'],
                'il': ['israel'],
                'ps': ['palestine'],
                'sa': ['saudi arabia'],
                'ae': ['united arab emirates', 'uae'],
                'qa': ['qatar'],
                'kw': ['kuwait'],
                'bh': ['bahrain'],
                'om': ['oman'],
                'ye': ['yemen'],
                'eg': ['egypt'],
                'ly': ['libya'],
                'tn': ['tunisia'],
                'dz': ['algeria'],
                'ma': ['morocco'],
                'sd': ['sudan'],
                'ss': ['south sudan'],
                'et': ['ethiopia'],
                'er': ['eritrea'],
                'dj': ['djibouti'],
                'so': ['somalia'],
                'ke': ['kenya'],
                'ug': ['uganda'],
                'tz': ['tanzania'],
                'rw': ['rwanda'],
                'bi': ['burundi'],
                'mw': ['malawi'],
                'zm': ['zambia'],
                'zw': ['zimbabwe'],
                'bw': ['botswana'],
                'na': ['namibia'],
                'za': ['south africa'],
                'sz': ['swaziland', 'eswatini'],
                'ls': ['lesotho'],
                'mg': ['madagascar'],
                'mu': ['mauritius'],
                'sc': ['seychelles'],
                'km': ['comoros'],
                'mz': ['mozambique'],
                'ao': ['angola'],
                'cd': ['congo', 'democratic republic of congo'],
                'cg': ['congo', 'republic of congo'],
                'cf': ['central african republic'],
                'td': ['chad'],
                'cm': ['cameroon'],
                'gq': ['equatorial guinea'],
                'ga': ['gabon'],
                'st': ['sao tome and principe'],
                'gh': ['ghana'],
                'tg': ['togo'],
                'bj': ['benin'],
                'ne': ['niger'],
                'bf': ['burkina faso'],
                'ml': ['mali'],
                'sn': ['senegal'],
                'gm': ['gambia'],
                'gw': ['guinea-bissau'],
                'gn': ['guinea'],
                'sl': ['sierra leone'],
                'lr': ['liberia'],
                'ci': ['ivory coast', 'cote d\'ivoire'],
                'gh': ['ghana'],
                'tg': ['togo'],
                'bj': ['benin'],
                'ne': ['niger'],
                'bf': ['burkina faso'],
                'ml': ['mali'],
                'sn': ['senegal'],
                'gm': ['gambia'],
                'gw': ['guinea-bissau'],
                'gn': ['guinea'],
                'sl': ['sierra leone'],
                'lr': ['liberia'],
                'ci': ['ivory coast', 'cote d\'ivoire'],
                'ca': ['canada'],
                'mx': ['mexico'],
                'gt': ['guatemala'],
                'bz': ['belize'],
                'sv': ['el salvador'],
                'hn': ['honduras'],
                'ni': ['nicaragua'],
                'cr': ['costa rica'],
                'pa': ['panama'],
                'cu': ['cuba'],
                'jm': ['jamaica'],
                'ht': ['haiti'],
                'do': ['dominican republic'],
                'pr': ['puerto rico'],
                'tt': ['trinidad and tobago'],
                'bb': ['barbados'],
                'ag': ['antigua and barbuda'],
                'dm': ['dominica'],
                'gd': ['grenada'],
                'kn': ['saint kitts and nevis'],
                'lc': ['saint lucia'],
                'vc': ['saint vincent and the grenadines'],
                'bs': ['bahamas'],
                'ar': ['argentina'],
                'bo': ['bolivia'],
                'br': ['brazil'],
                'cl': ['chile'],
                'co': ['colombia'],
                'ec': ['ecuador'],
                'fk': ['falkland islands'],
                'gf': ['french guiana'],
                'gy': ['guyana'],
                'py': ['paraguay'],
                'pe': ['peru'],
                'sr': ['suriname'],
                'uy': ['uruguay'],
                've': ['venezuela'],
                'au': ['australia'],
                'nz': ['new zealand'],
                'fj': ['fiji'],
                'pg': ['papua new guinea'],
                'sb': ['solomon islands'],
                'vu': ['vanuatu'],
                'nc': ['new caledonia'],
                'pf': ['french polynesia'],
                'ws': ['samoa'],
                'to': ['tonga'],
                'ki': ['kiribati'],
                'tv': ['tuvalu'],
                'nr': ['nauru'],
                'pw': ['palau'],
                'fm': ['micronesia'],
                'mh': ['marshall islands'],
                'as': ['american samoa'],
                'gu': ['guam'],
                'mp': ['northern mariana islands'],
                'vi': ['us virgin islands'],
                'vg': ['british virgin islands'],
                'ai': ['anguilla'],
                'aw': ['aruba'],
                'bq': ['bonaire'],
                'cw': ['curacao'],
                'sx': ['sint maarten'],
                'bl': ['saint barthelemy'],
                'mf': ['saint martin'],
                'gp': ['guadeloupe'],
                'mq': ['martinique'],
                're': ['reunion'],
                'yt': ['mayotte'],
                'sh': ['saint helena'],
                'ac': ['ascension island'],
                'ta': ['tristan da cunha'],
                'gs': ['south georgia and the south sandwich islands'],
                'hm': ['heard island and mcdonald islands'],
                'tf': ['french southern territories'],
                'aq': ['antarctica'],
                'bv': ['bouvet island'],
                'sj': ['svalbard and jan mayen'],
                'no': ['norway'],
                'gl': ['greenland'],
                'fo': ['faroe islands'],
                'ax': ['aland islands'],
                'je': ['jersey'],
                'gg': ['guernsey'],
                'im': ['isle of man'],
                'gi': ['gibraltar'],
                'ad': ['andorra'],
                'sm': ['san marino'],
                'va': ['vatican'],
                'li': ['liechtenstein'],
                'mc': ['monaco'],
                'mt': ['malta'],
                'cy': ['cyprus'],
                'tr': ['turkey'],
                'ru': ['russia'],
                'ua': ['ukraine'],
                'by': ['belarus'],
                'md': ['moldova'],
                'ro': ['romania'],
                'bg': ['bulgaria'],
                'gr': ['greece'],
                'al': ['albania'],
                'me': ['montenegro'],
                'rs': ['serbia'],
                'ba': ['bosnia and herzegovina'],
                'hr': ['croatia'],
                'si': ['slovenia'],
                'sk': ['slovakia'],
                'cz': ['czech republic', 'czechia'],
                'hu': ['hungary'],
                'at': ['austria'],
                'ch': ['switzerland'],
                'li': ['liechtenstein'],
                'de': ['germany'],
                'lu': ['luxembourg'],
                'be': ['belgium'],
                'nl': ['netherlands', 'holland'],
                'dk': ['denmark'],
                'se': ['sweden'],
                'no': ['norway'],
                'fi': ['finland'],
                'is': ['iceland'],
                'ie': ['ireland'],
                'gb': ['united kingdom', 'uk', 'britain', 'england', 'scotland', 'wales'],
                'fr': ['france'],
                'es': ['spain'],
                'pt': ['portugal'],
                'it': ['italy'],
                'mt': ['malta'],
                'cy': ['cyprus'],
                'gr': ['greece'],
                'tr': ['turkey'],
                'ru': ['russia'],
                'ua': ['ukraine'],
                'by': ['belarus'],
                'md': ['moldova'],
                'ro': ['romania'],
                'bg': ['bulgaria'],
                'al': ['albania'],
                'me': ['montenegro'],
                'rs': ['serbia'],
                'ba': ['bosnia and herzegovina'],
                'hr': ['croatia'],
                'si': ['slovenia'],
                'sk': ['slovakia'],
                'cz': ['czech republic', 'czechia'],
                'hu': ['hungary'],
                'at': ['austria'],
                'ch': ['switzerland'],
                'li': ['liechtenstein'],
                'de': ['germany'],
                'lu': ['luxembourg'],
                'be': ['belgium'],
                'nl': ['netherlands', 'holland'],
                'dk': ['denmark'],
                'se': ['sweden'],
                'no': ['norway'],
                'fi': ['finland'],
                'is': ['iceland'],
                'ie': ['ireland'],
                'gb': ['united kingdom', 'uk', 'britain', 'england', 'scotland', 'wales'],
                'fr': ['france'],
                'es': ['spain'],
                'pt': ['portugal'],
                'it': ['italy']
            }
            
            # Add country variations
            if current_country in country_variations:
                gap_keywords.extend(country_variations[current_country])
            if next_country in country_variations:
                gap_keywords.extend(country_variations[next_country])
        
        # Remove duplicates and empty strings
        gap_keywords = list(set([kw for kw in gap_keywords if kw.strip()]))
        
        return gap_keywords
    
    def normalize_country_code(self, country_code: str) -> str:
        """Normalize country codes to ISO 3166-1 alpha-2 format"""
        if not country_code or country_code.strip() == '':
            return 'Unknown'
        
        country_code = country_code.strip().upper()
        
        # Common country code mappings to ISO 3166-1 alpha-2
        country_mappings = {
            'UK': 'GB',  # United Kingdom
            'UNITED KINGDOM': 'GB',
            'BRITAIN': 'GB',
            'ENGLAND': 'GB',
            'SCOTLAND': 'GB',
            'WALES': 'GB',
            'USA': 'US',  # United States
            'UNITED STATES': 'US',
            'AMERICA': 'US',
            'USA': 'US',
            'DEUTSCHLAND': 'DE',  # Germany
            'ALLEMAGNE': 'DE',
            'FRANCE': 'FR',
            'ESPANA': 'ES',  # Spain
            'SPAIN': 'ES',
            'ITALIA': 'IT',  # Italy
            'ITALY': 'IT',
            'NEDERLAND': 'NL',  # Netherlands
            'HOLLAND': 'NL',
            'NEDERLANDEN': 'NL',
            'BELGIE': 'BE',  # Belgium
            'BELGIUM': 'BE',
            'SCHWEIZ': 'CH',  # Switzerland
            'SUISSE': 'CH',
            'SVIZZERA': 'CH',
            'OSTERREICH': 'AT',  # Austria
            'AUSTRIA': 'AT',
            'DANMARK': 'DK',  # Denmark
            'DENMARK': 'DK',
            'SVERIGE': 'SE',  # Sweden
            'SWEDEN': 'SE',
            'NORGE': 'NO',  # Norway
            'NORWAY': 'NO',
            'SUOMI': 'FI',  # Finland
            'FINLAND': 'FI',
            'ISLAND': 'IS',  # Iceland
            'ICELAND': 'IS',
            'EIRE': 'IE',  # Ireland
            'IRELAND': 'IE',
            'POLSKA': 'PL',  # Poland
            'POLAND': 'PL',
            'CESKA REPUBLIKA': 'CZ',  # Czech Republic
            'CZECH REPUBLIC': 'CZ',
            'CZECHIA': 'CZ',
            'MAGYARORSZAG': 'HU',  # Hungary
            'HUNGARY': 'HU',
            'SLOVENSKO': 'SK',  # Slovakia
            'SLOVAKIA': 'SK',
            'SLOVENIJA': 'SI',  # Slovenia
            'SLOVENIA': 'SI',
            'HRVATSKA': 'HR',  # Croatia
            'CROATIA': 'HR',
            'SRBIJA': 'RS',  # Serbia
            'SERBIA': 'RS',
            'BULGARIA': 'BG',
            'ROMANIA': 'RO',
            'ELLADA': 'GR',  # Greece
            'GREECE': 'GR',
            'TURKIYE': 'TR',  # Turkey
            'TURKEY': 'TR',
            'ROSSIYA': 'RU',  # Russia
            'RUSSIA': 'RU',
            'UKRAINA': 'UA',  # Ukraine
            'UKRAINE': 'UA',
            'BELARUS': 'BY',
            'LITHUANIA': 'LT',
            'LATVIA': 'LV',
            'ESTONIA': 'EE',
            'PORTUGAL': 'PT',
            'LUXEMBOURG': 'LU',
            'MALTA': 'MT',
            'CYPRUS': 'CY',
            'LIECHTENSTEIN': 'LI',
            'MONACO': 'MC',
            'ANDORRA': 'AD',
            'SAN MARINO': 'SM',
            'VATICAN': 'VA',
            'JAPAN': 'JP',
            'NIPPON': 'JP',
            'KOREA': 'KR',
            'SOUTH KOREA': 'KR',
            'CHINA': 'CN',
            'TAIWAN': 'TW',
            'HONG KONG': 'HK',
            'MACAU': 'MO',
            'INDIA': 'IN',
            'PAKISTAN': 'PK',
            'BANGLADESH': 'BD',
            'SRI LANKA': 'LK',
            'MALDIVES': 'MV',
            'NEPAL': 'NP',
            'BHUTAN': 'BT',
            'AFGHANISTAN': 'AF',
            'IRAN': 'IR',
            'IRAQ': 'IQ',
            'SYRIA': 'SY',
            'LEBANON': 'LB',
            'JORDAN': 'JO',
            'ISRAEL': 'IL',
            'PALESTINE': 'PS',
            'SAUDI ARABIA': 'SA',
            'UAE': 'AE',
            'UNITED ARAB EMIRATES': 'AE',
            'QATAR': 'QA',
            'KUWAIT': 'KW',
            'BAHRAIN': 'BH',
            'OMAN': 'OM',
            'YEMEN': 'YE',
            'EGYPT': 'EG',
            'LIBYA': 'LY',
            'TUNISIA': 'TN',
            'ALGERIA': 'DZ',
            'MOROCCO': 'MA',
            'SUDAN': 'SD',
            'SOUTH SUDAN': 'SS',
            'ETHIOPIA': 'ET',
            'ERITREA': 'ER',
            'DJIBOUTI': 'DJ',
            'SOMALIA': 'SO',
            'KENYA': 'KE',
            'UGANDA': 'UG',
            'TANZANIA': 'TZ',
            'RWANDA': 'RW',
            'BURUNDI': 'BI',
            'MALAWI': 'MW',
            'ZAMBIA': 'ZM',
            'ZIMBABWE': 'ZW',
            'BOTSWANA': 'BW',
            'NAMIBIA': 'NA',
            'SOUTH AFRICA': 'ZA',
            'ESWATINI': 'SZ',
            'LESOTHO': 'LS',
            'MADAGASCAR': 'MG',
            'MAURITIUS': 'MU',
            'SEYCHELLES': 'SC',
            'COMOROS': 'KM',
            'MOZAMBIQUE': 'MZ',
            'ANGOLA': 'AO',
            'CONGO': 'CD',
            'DEMOCRATIC REPUBLIC OF CONGO': 'CD',
            'REPUBLIC OF CONGO': 'CG',
            'CENTRAL AFRICAN REPUBLIC': 'CF',
            'CHAD': 'TD',
            'CAMEROON': 'CM',
            'EQUATORIAL GUINEA': 'GQ',
            'GABON': 'GA',
            'SAO TOME AND PRINCIPE': 'ST',
            'GHANA': 'GH',
            'TOGO': 'TG',
            'BENIN': 'BJ',
            'NIGER': 'NE',
            'BURKINA FASO': 'BF',
            'MALI': 'ML',
            'SENEGAL': 'SN',
            'GAMBIA': 'GM',
            'GUINEA-BISSAU': 'GW',
            'GUINEA': 'GN',
            'SIERRA LEONE': 'SL',
            'LIBERIA': 'LR',
            'IVORY COAST': 'CI',
            'COTE D\'IVOIRE': 'CI',
            'CANADA': 'CA',
            'MEXICO': 'MX',
            'GUATEMALA': 'GT',
            'BELIZE': 'BZ',
            'EL SALVADOR': 'SV',
            'HONDURAS': 'HN',
            'NICARAGUA': 'NI',
            'COSTA RICA': 'CR',
            'PANAMA': 'PA',
            'CUBA': 'CU',
            'JAMAICA': 'JM',
            'HAITI': 'HT',
            'DOMINICAN REPUBLIC': 'DO',
            'PUERTO RICO': 'PR',
            'TRINIDAD AND TOBAGO': 'TT',
            'BARBADOS': 'BB',
            'ANTIGUA AND BARBUDA': 'AG',
            'DOMINICA': 'DM',
            'GRENADA': 'GD',
            'SAINT KITTS AND NEVIS': 'KN',
            'SAINT LUCIA': 'LC',
            'SAINT VINCENT AND THE GRENADINES': 'VC',
            'BAHAMAS': 'BS',
            'ARGENTINA': 'AR',
            'BOLIVIA': 'BO',
            'BRAZIL': 'BR',
            'CHILE': 'CL',
            'COLOMBIA': 'CO',
            'ECUADOR': 'EC',
            'FALKLAND ISLANDS': 'FK',
            'FRENCH GUIANA': 'GF',
            'GUYANA': 'GY',
            'PARAGUAY': 'PY',
            'PERU': 'PE',
            'SURINAME': 'SR',
            'URUGUAY': 'UY',
            'VENEZUELA': 'VE',
            'AUSTRALIA': 'AU',
            'NEW ZEALAND': 'NZ',
            'FIJI': 'FJ',
            'PAPUA NEW GUINEA': 'PG',
            'SOLOMON ISLANDS': 'SB',
            'VANUATU': 'VU',
            'NEW CALEDONIA': 'NC',
            'FRENCH POLYNESIA': 'PF',
            'SAMOA': 'WS',
            'TONGA': 'TO',
            'KIRIBATI': 'KI',
            'TUVALU': 'TV',
            'NAURU': 'NR',
            'PALAU': 'PW',
            'MICRONESIA': 'FM',
            'MARSHALL ISLANDS': 'MH',
            'AMERICAN SAMOA': 'AS',
            'GUAM': 'GU',
            'NORTHERN MARIANA ISLANDS': 'MP',
            'US VIRGIN ISLANDS': 'VI',
            'BRITISH VIRGIN ISLANDS': 'VG',
            'ANGUILLA': 'AI',
            'ARUBA': 'AW',
            'BONAIRE': 'BQ',
            'CURACAO': 'CW',
            'SINT MAARTEN': 'SX',
            'SAINT BARTHELEMY': 'BL',
            'SAINT MARTIN': 'MF',
            'GUADELOUPE': 'GP',
            'MARTINIQUE': 'MQ',
            'REUNION': 'RE',
            'MAYOTTE': 'YT',
            'SAINT HELENA': 'SH',
            'ASCENSION ISLAND': 'AC',
            'TRISTAN DA CUNHA': 'TA',
            'SOUTH GEORGIA AND THE SOUTH SANDWICH ISLANDS': 'GS',
            'HEARD ISLAND AND MCDONALD ISLANDS': 'HM',
            'FRENCH SOUTHERN TERRITORIES': 'TF',
            'ANTARCTICA': 'AQ',
            'BOUVET ISLAND': 'BV',
            'SVALBARD AND JAN MAYEN': 'SJ',
            'GREENLAND': 'GL',
            'FAROE ISLANDS': 'FO',
            'ALAND ISLANDS': 'AX',
            'JERSEY': 'JE',
            'GUERNSEY': 'GG',
            'ISLE OF MAN': 'IM',
            'GIBRALTAR': 'GI',
            'ANDORRA': 'AD',
            'SAN MARINO': 'SM',
            'VATICAN': 'VA',
            'LIECHTENSTEIN': 'LI',
            'MONACO': 'MC',
            'MALTA': 'MT',
            'CYPRUS': 'CY',
            'TURKEY': 'TR',
            'RUSSIA': 'RU',
            'UKRAINE': 'UA',
            'BELARUS': 'BY',
            'MOLDOVA': 'MD',
            'ROMANIA': 'RO',
            'BULGARIA': 'BG',
            'ALBANIA': 'AL',
            'MONTENEGRO': 'ME',
            'SERBIA': 'RS',
            'BOSNIA AND HERZEGOVINA': 'BA',
            'CROATIA': 'HR',
            'SLOVENIA': 'SI',
            'SLOVAKIA': 'SK',
            'CZECH REPUBLIC': 'CZ',
            'CZECHIA': 'CZ',
            'HUNGARY': 'HU',
            'AUSTRIA': 'AT',
            'SWITZERLAND': 'CH',
            'LIECHTENSTEIN': 'LI',
            'GERMANY': 'DE',
            'LUXEMBOURG': 'LU',
            'BELGIUM': 'BE',
            'NETHERLANDS': 'NL',
            'DENMARK': 'DK',
            'SWEDEN': 'SE',
            'NORWAY': 'NO',
            'FINLAND': 'FI',
            'ICELAND': 'IS',
            'IRELAND': 'IE',
            'UNITED KINGDOM': 'GB',
            'FRANCE': 'FR',
            'SPAIN': 'ES',
            'PORTUGAL': 'PT',
            'ITALY': 'IT'
        }
        
        # Check mappings first (including common 2-letter variations)
        if country_code in country_mappings:
            return country_mappings[country_code]
        
        # If no mapping found, check if it's already a valid ISO code (2 letters)
        if len(country_code) == 2 and country_code.isalpha():
            return country_code
        
        # If no mapping found and not 2-letter, return as-is
        return country_code
    
    def normalize_travel_entry_country_codes(self, entry: Dict) -> Dict:
        """Normalize country codes in a travel entry"""
        normalized_entry = entry.copy()
        
        # Normalize departure and arrival country codes
        if 'departure_country' in normalized_entry:
            normalized_entry['departure_country'] = self.normalize_country_code(normalized_entry['departure_country'])
        
        if 'arrival_country' in normalized_entry:
            normalized_entry['arrival_country'] = self.normalize_country_code(normalized_entry['arrival_country'])
        
        return normalized_entry

    async def search_travel_emails_async(self) -> List[Dict]:
        """Search for travel-related emails using async processing with comprehensive keywords and gap location filtering"""
        start_time = time.time()
        print("Searching for travel-related emails asynchronously...")
        
        # Load comprehensive travel keywords
        travel_keywords = self.load_travel_keywords()
        
        # Add gap location keywords for enhanced filtering
        gap_keywords = []
        if hasattr(self, 'gaps') and self.gaps:
            gap_keywords = self.get_gap_location_keywords(self.gaps)
            print(f"Added {len(gap_keywords)} gap location keywords for enhanced filtering")
        
        # Combine all keywords
        all_keywords = travel_keywords + gap_keywords
        print(f"Loaded {len(travel_keywords)} travel keywords + {len(gap_keywords)} gap location keywords = {len(all_keywords)} total keywords")
        
        # Get all email files
        email_files = glob.glob(os.path.join(self.email_dir, "*.eml"))
        print(f"Found {len(email_files)} email files to process")
        
        # Process emails in batches asynchronously
        travel_emails = []
        processed_count = 0
        keyword_matches = 0
        
        # Create semaphore to limit concurrent operations
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def process_email_batch(batch_files):
            nonlocal keyword_matches
            batch_start = time.time()
            async with semaphore:
                tasks = [self.parse_email_direct_async(file) for file in batch_files]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                batch_travel_emails = []
                for result in results:
                    if isinstance(result, Exception):
                        continue
                    if not result:
                        continue
                    
                    subject = result['subject'].lower()
                    sender = result['sender'].lower()
                    content = result['content'].lower()
                    
                    # Check if email might contain travel info using all keywords
                    if any(keyword in subject for keyword in all_keywords) or \
                       any(keyword in sender for keyword in all_keywords) or \
                       any(keyword in content for keyword in all_keywords):
                        batch_travel_emails.append(result)
                        keyword_matches += 1
                
                batch_time = time.time() - batch_start
                print(f"  Batch processed in {batch_time:.2f}s, found {len(batch_travel_emails)} travel emails")
                return batch_travel_emails
        
        # Process files in batches
        for i in range(0, len(email_files), self.batch_size):
            batch_start = time.time()
            batch_files = email_files[i:i + self.batch_size]
            batch_results = await process_email_batch(batch_files)
            travel_emails.extend(batch_results)
            
            processed_count += len(batch_files)
            batch_time = time.time() - batch_start
            
            if processed_count % 1000 == 0:
                elapsed = time.time() - start_time
                rate = processed_count / elapsed if elapsed > 0 else 0
                print(f"Processed {processed_count}/{len(email_files)} emails... ({rate:.1f} emails/sec)")
            
            # Increased limit for comprehensive filtering
            if len(travel_emails) >= 1000:  # Increased from 300
                print(f"Found {len(travel_emails)} travel emails, stopping search...")
                break
        
        total_time = time.time() - start_time
        print(f"✅ Email filtering completed in {total_time:.2f}s")
        print(f"   • Processed: {processed_count} emails")
        print(f"   • Keyword matches: {keyword_matches}")
        print(f"   • Travel emails found: {len(travel_emails)}")
        print(f"   • Filter efficiency: {len(travel_emails)/processed_count*100:.1f}% of emails were travel-related")
        
        return travel_emails
    
    async def parse_email_direct_async(self, email_file: str) -> Optional[Dict]:
        """Parse email directly from .eml file without metadata (async version)"""
        try:
            async with aiofiles.open(email_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
                msg = email.message_from_string(content)
            
            # Extract headers
            subject = self.decode_header(msg.get('Subject', ''))
            sender = self.decode_header(msg.get('From', ''))
            date_str = msg.get('Date', '')
            
            # Parse date
            email_date = None
            if date_str:
                try:
                    # Parse email date
                    email_date = datetime.strptime(date_str.split(',')[1].strip()[:11], '%d %b %Y')
                except:
                    try:
                        email_date = datetime.strptime(date_str.split(',')[1].strip()[:11], '%d %b %Y')
                    except:
                        pass
            
            # Extract content
            content_text = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        content_text += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    elif part.get_content_type() == "text/html":
                        html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                        soup = BeautifulSoup(html_content, 'html.parser')
                        content_text += soup.get_text()
            else:
                if msg.get_content_type() == "text/plain":
                    content_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                elif msg.get_content_type() == "text/html":
                    html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    soup = BeautifulSoup(html_content, 'html.parser')
                    content_text += soup.get_text()
            
            return {
                'file': email_file,
                'subject': subject,
                'sender': sender,
                'date': email_date,
                'content': content_text.strip()
            }
            
        except Exception as e:
            return None
    
    async def extract_travel_info_with_ai_async(self, emails: List[Dict]) -> List[Dict]:
        """Use AI to extract travel information from emails - process each email only once"""
        if not emails:
            return []
        
        print(f"Using AI to extract travel info from {len(emails)} emails (processing each email only once)...")
        
        # Process all emails once with AI to extract all travel entries
        all_travel_entries = await self.analyze_all_emails_with_ai_async(emails)
        
        # Now match extracted entries to gaps
        gap_filling_entries = self.match_entries_to_gaps(all_travel_entries)
        
        return gap_filling_entries
    
    async def analyze_all_emails_with_ai_async(self, emails: List[Dict]) -> List[Dict]:
        """Process all emails once with AI to extract travel information"""
        start_time = time.time()
        all_travel_entries = []
        
        # Process emails in smaller batches to avoid context length limits
        batch_size = 8  # Reduced from 20 to prevent context overflow
        total_batches = (len(emails) + batch_size - 1) // batch_size
        
        print(f"🤖 Starting AI analysis of {len(emails)} emails in {total_batches} batches...")
        
        for i in range(0, len(emails), batch_size):
            batch_start = time.time()
            batch_emails = emails[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            # Create context for AI about all gaps
            gaps_context = self.create_gaps_context()
            
            # Send batch to AI
            entries = await self.analyze_email_batch_with_ai_async(batch_emails, gaps_context)
            all_travel_entries.extend(entries)
            
            batch_time = time.time() - batch_start
            elapsed = time.time() - start_time
            avg_time_per_batch = elapsed / batch_num
            remaining_batches = total_batches - batch_num
            eta = remaining_batches * avg_time_per_batch
            
            print(f"  Batch {batch_num}/{total_batches} completed in {batch_time:.2f}s (ETA: {eta:.1f}s) - Found {len(entries)} entries")
            
            # Add delay between batches to respect rate limits
            if batch_num < total_batches:  # Don't delay after the last batch
                await asyncio.sleep(1.0)  # 1 second delay between batches
        
        total_time = time.time() - start_time
        print(f"✅ AI analysis completed in {total_time:.2f}s")
        print(f"   • Processed: {len(emails)} emails in {total_batches} batches")
        print(f"   • Extracted: {len(all_travel_entries)} travel entries")
        print(f"   • Average: {len(all_travel_entries)/len(emails)*100:.1f}% of emails contained travel info")
        print(f"   • Rate: {len(emails)/total_time:.1f} emails/sec")
        
        return all_travel_entries
    
    def create_gaps_context(self) -> str:
        """Create context string about all gaps for AI analysis"""
        gaps_info = []
        for i, gap in enumerate(self.gaps, 1):
            gap_type = "COUNTRY" if gap['is_country_gap'] else "CITY"
            priority = "🔴" if gap['is_country_gap'] else "🟡"
            gap_days = gap.get('gap_days', gap.get('days', 'Unknown'))
            gaps_info.append(f"{priority} GAP #{i} ({gap_type}): {gap['current_arrival']} → {gap['next_departure']} [{gap_days} days]")
        
        return "GAPS TO FILL:\n" + "\n".join(gaps_info)
    
    async def call_openai_with_retry(self, prompt: str, max_retries: int = 3) -> any:
        """Call OpenAI API with exponential backoff retry logic"""
        import random
        
        for attempt in range(max_retries + 1):
            try:
                response = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: openai.ChatCompletion.create(
                        model="gpt-4o",  # Use GPT-4o for better context handling
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=1500,  # Reduced from 2000
                        temperature=0.1
                    )
                )
                return response
                
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check for rate limiting or context length errors
                if "rate_limit" in error_msg or "context_length" in error_msg or "tokens per min" in error_msg:
                    if attempt < max_retries:
                        # Exponential backoff with jitter
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        print(f"    Rate limit hit, waiting {wait_time:.1f}s before retry {attempt + 1}/{max_retries}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        print(f"    Max retries exceeded for rate limiting: {e}")
                        return None
                else:
                    # For other errors, don't retry
                    print(f"    Non-retryable error: {e}")
                    return None
        
        return None
    
    async def analyze_email_batch_with_ai_async(self, emails: List[Dict], gaps_context: str) -> List[Dict]:
        """Analyze a batch of emails with AI, considering all gaps"""
        if not emails:
            return []
        
        batch_start = time.time()
        
        # Prepare email content for AI with reduced content length
        email_content = ""
        for email in emails:
            email_content += f"\n--- EMAIL: {email['file']} ---\n"
            email_content += f"Date: {email['date']}\n"
            email_content += f"Subject: {email['subject']}\n"
            email_content += f"From: {email['sender']}\n"
            # Reduce content length to prevent context overflow
            email_content += f"Content: {email['content'][:800]}...\n"  # Reduced from 2000 to 800
        
        # Create AI prompt
        prompt = f"""
{gaps_context}

Please analyze the following emails and extract any travel information that could fill these gaps. Look for:
- Flight bookings, confirmations, itineraries
- Hotel reservations and check-ins
- Car rentals, train tickets, bus bookings
- Car lifts, informal transportation
- Any travel between the gap locations
- **Multiple flight details in single emails (connected flights, round trips, multi-city itineraries)**

IMPORTANT: If an email contains multiple flight segments (e.g., outbound and return flights, connected flights, layovers), extract ALL of them as separate entries. Each flight segment should be a separate entry in the JSON array.

EMAILS TO ANALYZE:
{email_content}

Return ONLY a JSON array of travel entries in this format:
[
  {{
    "departure_country": "XX",
    "departure_city": "City Name",
    "departure_date": "YYYY-MM-DD",
    "departure_time": "HH:MM",
    "arrival_country": "XX", 
    "arrival_city": "City Name",
    "arrival_date": "YYYY-MM-DD",
    "arrival_time": "HH:MM",
    "notes": "Description",
    "source_file": "filename.eml"
  }}
]

IMPORTANT COUNTRY CODE REQUIREMENTS:
- Use ISO 3166-1 alpha-2 country codes (2-letter codes only)
- Examples: GB (United Kingdom), US (United States), FR (France), DE (Germany)
- Common mappings: UK → GB, United Kingdom → GB, USA → US, United States → US
- Do NOT use full country names or 3-letter codes

If no travel information is found, return an empty array [].
"""
        
        try:
            ai_start = time.time()
            response = await self.call_openai_with_retry(prompt)
            ai_time = time.time() - ai_start
            
            content = response.choices[0].message.content.strip()
            
            # Try to extract JSON from response
            try:
                # Look for JSON array in the response
                json_start = content.find('[')
                json_end = content.rfind(']') + 1
                if json_start != -1 and json_end > json_start:
                    json_str = content[json_start:json_end]
                    entries = json.loads(json_str)
                    result = entries if isinstance(entries, list) else []
                else:
                    result = []
            except:
                result = []
            
            total_time = time.time() - batch_start
            print(f"    AI call: {ai_time:.2f}s, Total batch: {total_time:.2f}s, Found: {len(result)} entries")
            return result
            
        except Exception as e:
            batch_time = time.time() - batch_start
            print(f"    AI analysis error after {batch_time:.2f}s: {e}")
            return []
    
    def match_entries_to_gaps(self, all_entries: List[Dict]) -> List[Dict]:
        """Match extracted travel entries to specific gaps"""
        start_time = time.time()
        gap_filling_entries = []
        total_matches = 0
        
        print(f"\n🔍 MATCHING {len(all_entries)} EXTRACTED ENTRIES TO GAPS")
        print("=" * 60)
        
        for i, gap in enumerate(self.gaps, 1):
            gap_start = time.time()
            gap_type = "COUNTRY" if gap['is_country_gap'] else "CITY"
            priority = "🔴" if gap['is_country_gap'] else "🟡"
            
            print(f"\n{priority} GAP #{i}: {gap['current_arrival']} → {gap['next_departure']}")
            
            # Find entries that could fill this gap
            matching_entries = self.find_entries_for_gap(all_entries, gap)
            
            if matching_entries:
                print(f"   ✅ Found {len(matching_entries)} potential gap-filling entries")
                gap_filling_entries.extend(matching_entries)
                total_matches += len(matching_entries)
            else:
                print(f"   ❌ No gap-filling entries found")
            
            gap_time = time.time() - gap_start
            print(f"   ⏱️  Gap matching took {gap_time:.3f}s")
        
        total_time = time.time() - start_time
        print(f"\n✅ Gap matching completed in {total_time:.2f}s")
        print(f"   • Processed: {len(self.gaps)} gaps")
        print(f"   • Total matches: {total_matches}")
        print(f"   • Average: {total_matches/len(self.gaps):.1f} matches per gap")
        print(f"   • Rate: {len(self.gaps)/total_time:.1f} gaps/sec")
        
        return gap_filling_entries
    
    def find_entries_for_gap(self, all_entries: List[Dict], gap: Dict) -> List[Dict]:
        """Find travel entries that could fill a specific gap"""
        matching_entries = []
        
        try:
            gap_start = datetime.strptime(gap['current_arrival_date'], '%Y-%m-%d')
            gap_end = datetime.strptime(gap['next_departure_date'], '%Y-%m-%d')
        except:
            return matching_entries
        
        for entry in all_entries:
            try:
                entry_date = datetime.strptime(entry['departure_date'], '%Y-%m-%d')
                
                # Check if entry is within gap period or slightly before/after
                if (gap_start - timedelta(days=7) <= entry_date <= gap_end + timedelta(days=7)):
                    # Check if entry connects the gap locations
                    if self.entry_connects_gap(entry, gap):
                        matching_entries.append(entry)
            except:
                continue
        
        return matching_entries
    
    def entry_connects_gap(self, entry: Dict, gap: Dict) -> bool:
        """Check if a travel entry connects the gap locations"""
        # Simple connection logic - can be enhanced
        current_arrival = gap['current_arrival'].lower()
        next_departure = gap['next_departure'].lower()
        
        entry_departure = entry.get('departure_city', '').lower()
        entry_arrival = entry.get('arrival_city', '').lower()
        
        # Check if entry connects the gap
        return (current_arrival in entry_departure or entry_departure in current_arrival) and \
               (next_departure in entry_arrival or entry_arrival in next_departure)
    
    def find_emails_for_gap(self, emails: List[Dict], gap: Dict) -> List[Dict]:
        """Find emails that might contain information for a specific gap"""
        gap_emails = []
        
        # Parse gap dates
        try:
            gap_start = datetime.strptime(gap['current_arrival_date'], '%Y-%m-%d')
            gap_end = datetime.strptime(gap['next_departure_date'], '%Y-%m-%d')
        except:
            return gap_emails
        
        # Look for emails within the gap period AND much earlier (for advance bookings)
        for email in emails:
            if email['date']:
                # Check if email is within gap period
                if gap_start <= email['date'] <= gap_end:
                    gap_emails.append(email)
                # Also check emails slightly before/after the gap
                elif (gap_start - timedelta(days=7) <= email['date'] <= gap_end + timedelta(days=7)):
                    gap_emails.append(email)
                # Look much earlier for advance bookings (up to 12 months before)
                elif (gap_start - timedelta(days=365) <= email['date'] <= gap_start):
                    gap_emails.append(email)
        
        return gap_emails
    
    async def analyze_gap_with_ai_async(self, gap: Dict, gap_emails: List[Dict]) -> List[Dict]:
        """Analyze emails specifically for a gap with targeted AI prompts"""
        print(f"   Analyzing {len(gap_emails)} emails for gap: {gap['current_arrival']} → {gap['next_departure']}")
        
        # Prepare targeted context for AI
        context = f"""
        I need to find travel information that connects {gap['current_arrival']} to {gap['next_departure']}.
        
        This is a GAP in a travel itinerary where someone arrived in {gap['current_arrival']} on {gap['current_arrival_date']} 
        and then departed from {gap['next_departure']} on {gap['next_departure_date']}.
        
        I need to find the missing transportation that connects these two locations.
        
        Look for:
        - Flights from {gap['current_arrival']} to {gap['next_departure']}
        - Flights from {gap['current_arrival']} to intermediate cities, then to {gap['next_departure']}
        - Train/bus connections between these locations
        - Car lifts, rideshares, or informal transportation
        - Taxi rides, Uber/Lyft, or private car transport
        - Any transportation that would logically connect these two places
        
        Return ONLY entries that help fill this specific gap. If no relevant travel is found, return an empty array.
        
        Return the information in this JSON format:
        {{
            "travel_entries": [
                {{
                    "departure_country": "XX",
                    "departure_city": "City Name (Airport Code)",
                    "departure_date": "YYYY-MM-DD",
                    "departure_time": "HH:MM",
                    "arrival_country": "XX", 
                    "arrival_city": "City Name (Airport Code)",
                    "arrival_date": "YYYY-MM-DD",
                    "arrival_time": "HH:MM",
                    "notes": "Flight (Airline FlightNumber) or other transport details",
                    "confidence": 0.0-1.0
                }}
            ]
        }}
        """
        
        # Combine email contents for this gap
        email_texts = []
        source_files = []
        for email in gap_emails[:3]:  # Limit to first 3 emails per gap
            email_texts.append(f"Subject: {email['subject']}\nSender: {email['sender']}\nContent: {email['content'][:1500]}")
            source_files.append(email['file'])
        
        full_context = context + "\n\n" + "\n\n---\n\n".join(email_texts)
        
        try:
            # Use asyncio to run the OpenAI call in a thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": f"You are an expert at finding specific travel connections. Focus ONLY on transportation that connects {gap['current_arrival']} to {gap['next_departure']}. Be very specific and targeted."},
                        {"role": "user", "content": full_context}
                    ],
                    max_tokens=1000,
                    temperature=0.1
                )
            )
            
            # Parse AI response
            ai_response = response.choices[0].message.content
            
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    entries = result.get('travel_entries', [])
                    
                    # Add source file information to each entry
                    for i, entry in enumerate(entries):
                        if i < len(source_files):
                            entry['source_file'] = source_files[i]
                        else:
                            entry['source_file'] = source_files[0] if source_files else 'Unknown'
                    
                    return entries
                except json.JSONDecodeError:
                    print(f"   Could not parse AI response as JSON")
                    return []
            else:
                print(f"   No JSON found in AI response")
                return []
                
        except Exception as e:
            print(f"   Error calling OpenAI API: {e}")
            return []
    
    async def analyze_period_with_ai_async(self, period: str, period_emails: List[Dict]) -> List[Dict]:
        """Analyze a specific time period with AI (async version)"""
        print(f"Analyzing emails from {period}...")
        
        # Prepare context for AI
        context = f"""
        I need to extract travel information from emails from {period}.
        
        Please analyze the following emails and extract any travel information.
        Look for flights, trains, buses, or other transportation.
        
        Return the information in this JSON format:
        {{
            "travel_entries": [
                {{
                    "departure_country": "XX",
                    "departure_city": "City Name (Airport Code)",
                    "departure_date": "YYYY-MM-DD",
                    "departure_time": "HH:MM",
                    "arrival_country": "XX", 
                    "arrival_city": "City Name (Airport Code)",
                    "arrival_date": "YYYY-MM-DD",
                    "arrival_time": "HH:MM",
                    "notes": "Flight (Airline FlightNumber) or other transport details",
                    "confidence": 0.0-1.0
                }}
            ]
        }}
        """
        
        # Combine email contents for this period with source file tracking
        email_texts = []
        source_files = []
        for email in period_emails[:5]:  # Limit per period
            email_texts.append(f"Subject: {email['subject']}\nSender: {email['sender']}\nContent: {email['content'][:1500]}")
            source_files.append(email['file'])
        
        full_context = context + "\n\n" + "\n\n---\n\n".join(email_texts)
        
        try:
            # Use asyncio to run the OpenAI call in a thread pool
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are an expert at extracting travel information from emails. Extract all travel-related information you can find."},
                        {"role": "user", "content": full_context}
                    ],
                    max_tokens=2000,
                    temperature=0.1
                )
            )
            
            # Parse AI response
            ai_response = response.choices[0].message.content
            
            # Try to extract JSON from response
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    entries = result.get('travel_entries', [])
                    
                    # Add source file information to each entry
                    for i, entry in enumerate(entries):
                        if i < len(source_files):
                            entry['source_file'] = source_files[i]
                        else:
                            entry['source_file'] = source_files[0] if source_files else 'Unknown'
                    
                    return entries
                except json.JSONDecodeError:
                    print(f"Could not parse AI response as JSON for {period}")
                    return []
            else:
                print(f"No JSON found in AI response for {period}")
                return []
                
        except Exception as e:
            print(f"Error calling OpenAI API for {period}: {e}")
            return []
    
    def clean_travel_entry(self, entry: Dict, source_file: str = None) -> Dict:
        """Clean and validate travel entry"""
        # Remove confidence field and clean up the entry
        cleaned_entry = {}
        
        # Required fields with defaults
        cleaned_entry['departure_country'] = entry.get('departure_country', 'Unknown')
        cleaned_entry['departure_city'] = entry.get('departure_city', 'Unknown')
        cleaned_entry['departure_date'] = entry.get('departure_date', '')
        cleaned_entry['departure_time'] = entry.get('departure_time', 'Unknown')
        cleaned_entry['arrival_country'] = entry.get('arrival_country', 'Unknown')
        cleaned_entry['arrival_city'] = entry.get('arrival_city', 'Unknown')
        cleaned_entry['arrival_date'] = entry.get('arrival_date', '')
        cleaned_entry['arrival_time'] = entry.get('arrival_time', 'Unknown')
        cleaned_entry['notes'] = entry.get('notes', 'Unknown')
        
        # Add source file information
        if source_file:
            cleaned_entry['source_file'] = os.path.basename(source_file)
        else:
            cleaned_entry['source_file'] = 'Unknown'
        
        # Clean up dates - replace "Unknown" with empty string
        if cleaned_entry['departure_date'] in ['Unknown', 'null', '']:
            cleaned_entry['departure_date'] = ''
        if cleaned_entry['arrival_date'] in ['Unknown', 'null', '']:
            cleaned_entry['arrival_date'] = ''
            
        # Clean up times - replace "Unknown" with empty string
        if cleaned_entry['departure_time'] in ['Unknown', 'null', '']:
            cleaned_entry['departure_time'] = ''
        if cleaned_entry['arrival_time'] in ['Unknown', 'null', '']:
            cleaned_entry['arrival_time'] = ''
        
        # Normalize country codes to ISO 3166-1 alpha-2 format
        cleaned_entry = self.normalize_travel_entry_country_codes(cleaned_entry)
            
        return cleaned_entry
    
    def add_connection_analysis(self, data: List[Dict]) -> List[Dict]:
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
                
                # Extract country and city from current entry
                current_country = self.extract_country(entry.get('arrival_city', ''))
                current_city = self.extract_city(entry.get('arrival_city', ''))
                
                # Extract country and city from next entry
                next_country = self.extract_country(next_entry.get('departure_city', ''))
                next_city = self.extract_city(next_entry.get('departure_city', ''))
                
                # Check if countries match
                country_match = current_country.lower() == next_country.lower() if current_country and next_country else False
                
                # Check if cities match
                city_match = current_city.lower() == next_city.lower() if current_city and next_city else False
                
                # Add analysis columns
                entry['next_country_match'] = '✅' if country_match else '❌'
                entry['next_city_match'] = '✅' if city_match else '❌'
                entry['next_country'] = next_country if next_country else 'Unknown'
                entry['next_city'] = next_city if next_city else 'Unknown'
                
                # Log the analysis
                if country_match or city_match:
                    print(f"  {i+1}. {entry.get('arrival_city', 'Unknown')} → {next_entry.get('departure_city', 'Unknown')}")
                    if country_match:
                        print(f"     ✅ Country match: {current_country}")
                    if city_match:
                        print(f"     ✅ City match: {current_city}")
            else:
                # Last entry - no next entry to compare
                entry['next_country_match'] = 'N/A'
                entry['next_city_match'] = 'N/A'
                entry['next_country'] = 'N/A'
                entry['next_city'] = 'N/A'
            
            data[i] = entry
        
        # Count matches
        country_matches = sum(1 for entry in data if entry.get('next_country_match') == '✅')
        city_matches = sum(1 for entry in data if entry.get('next_city_match') == '✅')
        
        print(f"\n📊 CONNECTION ANALYSIS SUMMARY:")
        print(f"   • Country matches: {country_matches}/{len(data)-1}")
        print(f"   • City matches: {city_matches}/{len(data)-1}")
        print(f"   • Total connections: {country_matches + city_matches}")
        
        return data
    
    def extract_country(self, location: str) -> str:
        """Extract country from location string (e.g., 'London (GB)' -> 'GB')"""
        if not location or location == 'Unknown':
            return ''
        
        # Look for country code in parentheses
        import re
        match = re.search(r'\(([A-Z]{2})\)', location)
        if match:
            return match.group(1)
        
        # If no country code, return the full location
        return location
    
    def extract_city(self, location: str) -> str:
        """Extract city from location string (e.g., 'London (GB)' -> 'London')"""
        if not location or location == 'Unknown':
            return ''
        
        # Remove country code in parentheses
        import re
        city = re.sub(r'\s*\([A-Z]{2}\)', '', location).strip()
        return city
    
    async def run_async(self):
        """Run the complete gap finding process with async processing"""
        print(f"Starting Async Travel Parser with {self.max_workers} workers...")
        overall_start = time.time()
        
        # Load existing data
        load_start = time.time()
        self.load_travel_data()
        load_time = time.time() - load_start
        print(f"📊 Data loading: {load_time:.2f}s")
        
        # Identify gaps
        gap_start = time.time()
        self.identify_gaps()
        gap_time = time.time() - gap_start
        print(f"📊 Gap identification: {gap_time:.2f}s")
        
        # Search for travel-related emails asynchronously (with gap location filtering)
        search_start = time.time()
        travel_emails = await self.search_travel_emails_async()
        search_time = time.time() - search_start
        print(f"📊 Email search: {search_time:.2f}s")
        
        if travel_emails:
            # Analyze emails with AI asynchronously
            ai_start = time.time()
            raw_entries = await self.extract_travel_info_with_ai_async(travel_emails)
            ai_time = time.time() - ai_start
            print(f"📊 AI processing: {ai_time:.2f}s")
            
            # Clean and validate entries with source file information
            clean_start = time.time()
            self.found_entries = []
            for entry in raw_entries:
                source_file = entry.get('source_file', 'Unknown')
                cleaned_entry = self.clean_travel_entry(entry, source_file)
                self.found_entries.append(cleaned_entry)
            clean_time = time.time() - clean_start
            print(f"📊 Entry cleaning: {clean_time:.2f}s")
            
            print(f"Found {len(self.found_entries)} potential travel entries from emails")
            
            # Print found entries for debugging
            print("\nFound travel entries:")
            for i, entry in enumerate(self.found_entries):
                print(f"  {i+1}. {entry.get('departure_city', 'Unknown')} -> {entry.get('arrival_city', 'Unknown')} on {entry.get('departure_date', 'Unknown')} (from {entry.get('source_file', 'Unknown')})")
        else:
            print("No travel-related emails found")
        
        # Detect incongruent events in original data
        incongruent_events = self.detect_incongruent_events(self.travel_data)
        
        # Generate complete table
        complete_data = self.generate_complete_table()
        
        # Add connection analysis columns
        complete_data = self.add_connection_analysis(complete_data)
        
        # Check if gaps are filled
        gaps_filled, gaps_remaining = self.check_gaps_filled(complete_data)
        
        # Save results with timestamped filename matching input style
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        output_file = f"all-travel-{timestamp}.csv"
        self.save_complete_table(complete_data, output_file)
        
        end_time = time.time()
        total_time = end_time - overall_start
        
        print(f"\n🎉 PROCESS COMPLETE!")
        print(f"📊 PERFORMANCE SUMMARY:")
        print(f"   • Total time: {total_time:.2f}s")
        print(f"   • Data loading: {load_time:.2f}s ({load_time/total_time*100:.1f}%)")
        print(f"   • Gap identification: {gap_time:.2f}s ({gap_time/total_time*100:.1f}%)")
        print(f"   • Email search: {search_time:.2f}s ({search_time/total_time*100:.1f}%)")
        if travel_emails:
            print(f"   • AI processing: {ai_time:.2f}s ({ai_time/total_time*100:.1f}%)")
            print(f"   • Entry cleaning: {clean_time:.2f}s ({clean_time/total_time*100:.1f}%)")
        print(f"📊 RESULTS:")
        print(f"   • Found {len(self.found_entries)} potential travel entries from emails")
        print(f"   • Gaps filled: {gaps_filled}/{len(self.gaps)} ({gaps_filled/len(self.gaps)*100:.1f}%)")
        print(f"   • Gaps remaining: {gaps_remaining}")
        print(f"   • Incongruent events detected: {len(incongruent_events)}")
        print(f"   • Complete itinerary saved to: {output_file}")
        if travel_emails:
            print(f"   • Processing rate: {len(travel_emails)/total_time:.1f} emails/sec")
            print(f"   • AI efficiency: {len(self.found_entries)/len(travel_emails)*100:.1f}% of emails yielded travel entries")
    
    def run(self):
        """Synchronous wrapper for async run"""
        asyncio.run(self.run_async())
    
    def generate_complete_table(self):
        """Generate complete travel table with gaps filled"""
        print("Generating complete travel table...")
        
        # Create new table with gaps filled
        complete_data = []
        used_entries = set()  # Track which found entries we've used
        
        for i, entry in enumerate(self.travel_data):
            # Add source_file field to existing entries (set to 'Original' for existing data)
            entry_with_source = entry.copy()
            entry_with_source['source_file'] = 'Original'
            complete_data.append(entry_with_source)
            
            # Check if there's a gap after this entry
            if i < len(self.travel_data) - 1:
                current_arrival = self.extract_city_name(entry['arrival_city'])
                next_departure = self.extract_city_name(self.travel_data[i + 1]['departure_city'])
                
                # Look for a travel entry that fills this gap
                for j, found_entry in enumerate(self.found_entries):
                    if j in used_entries:
                        continue
                    
                    found_departure = self.extract_city_name(found_entry.get('departure_city', ''))
                    found_arrival = self.extract_city_name(found_entry.get('arrival_city', ''))
                    
                    # Check if this entry fills the gap
                    if (found_departure.lower() == current_arrival.lower() and 
                        found_arrival.lower() == next_departure.lower()):
                        
                        complete_data.append(found_entry)
                        used_entries.add(j)
                        print(f"✅ FILLED GAP: {current_arrival} → {next_departure} (via {found_entry.get('departure_city', 'Unknown')} → {found_entry.get('arrival_city', 'Unknown')} from {found_entry.get('source_file', 'Unknown')})")
                        break
        
        return complete_data
    
    def detect_incongruent_events(self, travel_data: List[Dict]) -> List[Dict]:
        """Detect incongruent events like multiple trips from same location"""
        print(f"\n🔍 DETECTING INCONGRUENT EVENTS")
        print("=" * 60)
        
        incongruent_events = []
        
        # Group entries by departure city and date
        city_departures = {}
        for entry in travel_data:
            city = entry['departure_city']
            date = entry['departure_date']
            key = f"{city}_{date}"
            
            if key not in city_departures:
                city_departures[key] = []
            city_departures[key].append(entry)
        
        # Find cities with multiple departures on same date
        for key, entries in city_departures.items():
            if len(entries) > 1:
                city, date = key.split('_', 1)
                event = {
                    'type': 'multiple_departures',
                    'city': city,
                    'date': date,
                    'count': len(entries),
                    'entries': entries,
                    'description': f"Multiple departures from {city} on {date}"
                }
                incongruent_events.append(event)
                print(f"⚠️  INCONGRUENT: {event['description']} ({len(entries)} entries)")
        
        # Check for overlapping time periods
        for i, entry1 in enumerate(travel_data):
            for j, entry2 in enumerate(travel_data[i+1:], i+1):
                if (entry1['departure_city'] == entry2['departure_city'] and
                    entry1['departure_date'] == entry2['departure_date'] and
                    entry1['departure_time'] and entry2['departure_time']):
                    
                    # Check if times are close (within 2 hours)
                    try:
                        time1 = datetime.strptime(entry1['departure_time'], '%H:%M')
                        time2 = datetime.strptime(entry2['departure_time'], '%H:%M')
                        time_diff = abs((time1 - time2).total_seconds() / 3600)
                        
                        if time_diff < 2:  # Less than 2 hours apart
                            event = {
                                'type': 'overlapping_times',
                                'city': entry1['departure_city'],
                                'date': entry1['departure_date'],
                                'time1': entry1['departure_time'],
                                'time2': entry2['departure_time'],
                                'entries': [entry1, entry2],
                                'description': f"Overlapping departures from {entry1['departure_city']} on {entry1['departure_date']} at {entry1['departure_time']} and {entry2['departure_time']}"
                            }
                            incongruent_events.append(event)
                            print(f"⚠️  OVERLAPPING: {event['description']}")
                    except:
                        pass
        
        if not incongruent_events:
            print("✅ No incongruent events detected")
        else:
            print(f"\n📊 INCONGRUENT EVENTS SUMMARY:")
            print(f"   • Total events: {len(incongruent_events)}")
            print(f"   • Multiple departures: {len([e for e in incongruent_events if e['type'] == 'multiple_departures'])}")
            print(f"   • Overlapping times: {len([e for e in incongruent_events if e['type'] == 'overlapping_times'])}")
        
        print("=" * 60)
        return incongruent_events

    def check_gaps_filled(self, complete_data: List[Dict], verbose=True):
        """Check if all gaps have been filled in the complete data"""
        if verbose:
            print("\n🔍 CHECKING IF GAPS ARE FILLED")
            print("=" * 60)
        
        gaps_filled = 0
        gaps_remaining = 0
        
        for gap in self.gaps:
            gap_index = gap['gap_index']
            current_arrival = gap['current_arrival']
            next_departure = gap['next_departure']
            
            # Check if there's a connecting entry between the gap
            found_connection = False
            for i in range(gap_index + 1, len(complete_data)):
                entry = complete_data[i]
                entry_departure = self.extract_city_name(entry.get('departure_city', ''))
                entry_arrival = self.extract_city_name(entry.get('arrival_city', ''))
                
                # Check if this entry connects the gap
                if (entry_departure.lower() == current_arrival.lower() and 
                    entry_arrival.lower() == next_departure.lower()):
                    found_connection = True
                    if verbose:
                        print(f"✅ GAP #{gap['gap_number']:2d} FILLED: {current_arrival} → {next_departure} (via {entry.get('source_file', 'Unknown')})")
                    break
            
            if not found_connection:
                gaps_remaining += 1
                if verbose:
                    priority_icon = "🔴" if gap.get('is_country_gap', False) else "🟡"
                    gap_type = gap.get('gap_type', 'UNKNOWN')
                    print(f"{priority_icon} GAP #{gap['gap_number']:2d} UNFILLED ({gap_type}): {current_arrival} → {next_departure}")
            else:
                gaps_filled += 1
        
        if verbose:
            print(f"\n📊 GAP FILLING RESULTS:")
            print(f"   • Gaps filled: {gaps_filled}/{len(self.gaps)} ({gaps_filled/len(self.gaps)*100:.1f}%)")
            print(f"   • Gaps remaining: {gaps_remaining}")
            print("=" * 60)
        
        return gaps_filled, gaps_remaining
    
    def save_complete_table(self, complete_data: List[Dict], output_file: str):
        """Save complete travel table to CSV with chronological sorting"""
        print(f"Saving complete table to {output_file}...")
        
        # Sort the complete data chronologically before saving
        complete_data = self.sort_travel_data_chronologically(complete_data)
        
        # Match the exact format of the input file plus new connection analysis columns
        fieldnames = [
            'departure_country', 'departure_city', 'departure_date', 'departure_time',
            'arrival_country', 'arrival_city', 'arrival_date', 'arrival_time', 'notes',
            'source_file', 'next_country_match', 'next_city_match', 'next_country', 'next_city'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(complete_data)
        
        print(f"Complete table saved with {len(complete_data)} entries (chronologically sorted)")

def main():
    parser = argparse.ArgumentParser(description='Travel Itinerary Gap Filler')
    parser.add_argument('--csv', default='all-travel-20250916-2241.csv', help='Input CSV file path')
    parser.add_argument('--emails', default='mail_20250630_192936', help='Email directory path')
    parser.add_argument('--workers', type=int, default=8, help='Number of parallel workers')
    parser.add_argument('--gaps-only', action='store_true', help='Only identify gaps, do not process emails')
    parser.add_argument('--check-gaps', help='Check if gaps are filled in existing CSV file')
    
    args = parser.parse_args()
    
    # Check if files exist
    if not os.path.exists(args.csv):
        print(f"❌ Error: CSV file {args.csv} not found!")
        return
    
    if not args.gaps_only and not args.check_gaps:
        if not os.path.exists(args.emails):
            print(f"❌ Error: Email directory {args.emails} not found!")
            return
    
    # Create parser instance
    travel_parser = AsyncTravelParser(args.csv, args.emails, args.workers)
    
    if args.check_gaps:
        # Check gaps in existing file
        print("🔍 CHECKING GAPS IN EXISTING FILE")
        print("=" * 60)
        travel_parser.load_travel_data()
        travel_parser.identify_gaps()
        
        # Load the file to check
        check_data = []
        with open(args.check_gaps, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            check_data = list(reader)
        
        gaps_filled, gaps_remaining = travel_parser.check_gaps_filled(check_data)
        return
    
    if args.gaps_only:
        # Only identify gaps
        print("🔍 GAP IDENTIFICATION ONLY")
        print("=" * 60)
        travel_parser.load_travel_data()
        travel_parser.identify_gaps()
        return
    
    # Full processing
    travel_parser.run()

if __name__ == "__main__":
    main()

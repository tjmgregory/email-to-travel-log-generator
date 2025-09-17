# AGENTS.md

## Dev environment setup

- Install deps: `pip install -r requirements.txt`
- Create venv: `python3 -m venv venv`
- Activate venv: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
- Set OpenAI API key in `.env`: `OPEN_AI_KEY=your_key_here`

## Testing instructions

- Run all tests: `python test_requirements.py`
- Run gap identification only: `python async_travel_parser.py --gaps-only`
- Check gaps in existing file: `python async_travel_parser.py --check-gaps filename.csv`
- All tests must pass before committing changes
- Test coverage must include gap type differentiation (city vs country gaps)

## Code style

- Python 3.8+ with type hints
- Use async/await patterns for I/O operations
- Follow PEP 8 style guidelines
- Use descriptive variable names and docstrings
- Prefer functional patterns where possible

## Critical requirements for agents

- **Gap type differentiation is mandatory** - always distinguish city vs country gaps
- **Country gaps are critical** - they affect visa calculations and require priority
- **City gaps are moderate priority** - may indicate car lifts or local transport
- **Source file tracking** - every entry must have source attribution
- **Chronological ordering** - maintain proper date/time sequence
- **Data sorting** - all input and output data must be chronologically sorted

## Key algorithms to understand

### Gap Identification Logic

- Gaps occur when `arrival_city != next_departure_city`
- Country gaps: `arrival_country != next_departure_country`
- City gaps: `arrival_country == next_departure_country` but different cities
- **Chronological ordering**: All data is sorted by departure date/time before processing

### AI Processing Strategy

- Gap-focused AI extraction targets specific geographical connections
- Searches emails up to 12 months before travel dates for advance bookings
- Detects car lifts, informal transportation, and various transport methods
- Uses batch processing for large email datasets

## File structure and where to look

- `async_travel_parser.py` - Main production script (start here)
- `test_requirements.py` - Comprehensive test suite (run before changes)
- `PRD_Travel_Itinerary_Gap_Filler.md` - Complete product requirements
- `all-travel-*.csv` - Input/output travel data files
- `mail_*/` - Email export directory (25k+ .eml files)

## Common patterns for modifications

### Adding New Gap Detection Logic

```python
# Always check both city and country
is_country_gap = current_country.lower() != next_country.lower()
gap_type = "COUNTRY" if is_country_gap else "CITY"
priority_icon = "🔴" if is_country_gap else "🟡"
```

### Testing Gap Types

```python
# Test country gap
self.assertTrue(gap['is_country_gap'])
self.assertEqual(gap['gap_type'], 'COUNTRY')

# Test city gap  
self.assertFalse(gap['is_country_gap'])
self.assertEqual(gap['gap_type'], 'CITY')
```

### CLI Reporting Standards

- Use visual indicators: 🔴 for country gaps, 🟡 for city gaps, ✅ for filled, ❌ for unfilled
- Always show gap type in reports
- Provide summary statistics by gap type

## Performance considerations

- Use async/await for I/O operations
- Parallel processing with ThreadPoolExecutor
- Batch processing for large email datasets
- Configurable worker counts for different environments

## Error handling patterns

- Graceful handling of malformed email files
- Robust date parsing with fallbacks
- API rate limiting compliance
- Memory-efficient processing for large datasets

## Security requirements

- OpenAI API key stored in `.env` file (not committed)
- Local processing only (no data sent to external services except OpenAI)
- No persistent storage of email content
- Secure API key management

## Troubleshooting common issues

- **Gap identification issues**: Check city name extraction logic
- **AI extraction failures**: Verify OpenAI API key and rate limits
- **Performance problems**: Adjust worker count or batch size
- **Test failures**: Ensure gap type differentiation is properly implemented

## Development workflow

1. **Before making changes**: Run tests to ensure current state is working
2. **When adding features**: Update both code and tests simultaneously
3. **When modifying gap logic**: Ensure gap type differentiation is maintained
4. **Before committing**: Run full test suite and check gap identification
5. **For CLI changes**: Test with both `--gaps-only` and full processing modes

# Product Requirements Document (PRD)
## Travel Itinerary Gap Filler

### 1. Executive Summary

**Product Name**: Travel Itinerary Gap Filler  
**Version**: 1.0  
**Date**: January 2025  
**Status**: Complete  

A Python-based system that automatically identifies and fills gaps in personal travel itineraries by parsing email data using AI-powered extraction. The system processes large email exports to find missing travel entries and generates a complete, cohesive travel history.

### 2. Problem Statement

**Current State**: Users have incomplete travel itineraries with gaps where arrival cities don't match subsequent departure cities, creating geographical discontinuities in their travel history.

**Pain Points**:
- Manual gap identification is time-consuming and error-prone
- Travel information is scattered across thousands of emails
- No automated way to extract structured travel data from unstructured email content
- Missing travel entries create geographical gaps in personal travel records
- Gaps represent missing transportation between locations (not time spent in one place)
- Advance bookings made months before travel are not captured in current time-based searches
- Incongruent events (multiple trips from same location) indicate missed flights or booking errors
- Car lifts and other informal transportation methods are not captured
- Lack of clear CLI reporting makes gap analysis difficult

**Business Impact**: Incomplete travel records affect personal documentation, expense tracking, and travel pattern analysis.

### 3. Product Overview

**Core Functionality**: Automatically identify gaps in travel itineraries and fill them by extracting travel information from email data using AI.

**Key Features**:
- Gap identification in existing travel CSV files
- Email parsing and content extraction
- AI-powered travel information extraction
- Cohesiveness validation between travel entries
- Parallel processing for performance optimization
- Complete itinerary generation with gap filling
- Advance booking detection (up to 12 months before travel)
- Incongruent event detection and reporting
- Car lift and informal transportation detection
- Enhanced CLI reporting with gap analysis

### 4. User Stories

**As a frequent traveler**, I want to:
- Upload my existing travel CSV and email export
- Automatically identify gaps in my travel history
- Fill missing travel entries from my email data
- Generate a complete, cohesive travel itinerary
- Track which email file each travel entry came from
- Validate that travel entries make logical sense
- Find advance bookings made months before travel
- Detect incongruent events (missed flights, booking errors)
- Capture car lifts and informal transportation
- Get clear CLI reports showing where gaps exist

**As a data analyst**, I want to:
- Process large email datasets efficiently
- Extract structured travel data from unstructured content
- Track data provenance (source files) for each entry
- Validate data quality and cohesiveness
- Generate reports on travel patterns

### 5. Functional Requirements

#### 5.1 Core Features

**FR-1: Gap Identification**
- Parse existing travel CSV files
- Identify geographical gaps where arrival city ≠ next departure city
- **Differentiate gap types**: City gaps (same country) vs Country gaps (different countries)
- **Country gaps**: Critical for visa calculations, require immediate attention
- **City gaps**: Less critical, may indicate car lifts or local transportation
- Gaps represent missing transportation between locations
- Generate gap report with details and gap type classification
- Detect incongruent events (multiple trips from same location)
- Report potential missed flights or booking errors

**FR-2: Email Processing**
- Parse .eml email files from export
- Extract headers (subject, sender, date)
- Extract and clean email content (text and HTML)
- Filter emails for travel-related content using comprehensive keyword matching
- **Gap location filtering**: Include city and country names from identified gaps in search criteria
- Search emails up to 12 months before travel dates (advance bookings)
- Include emails from gap periods plus buffer zones

**FR-3: AI-Powered Extraction**
- Use OpenAI GPT-4 for travel information extraction
- Parse emails by time periods for context
- Extract structured travel data (departure/arrival cities, dates, times, notes)
- **Multi-flight extraction**: Handle multiple flight details in single emails (e.g., connected flights, round trips)
- Validate extracted data quality
- Detect car lifts and informal transportation methods
- Focus on specific gap-filling connections

**FR-4: Gap Filling**
- Match extracted travel entries to identified gaps
- Insert missing entries in chronological order
- Track source file for each extracted entry
- Generate complete itinerary with source attribution

**FR-5: Performance Optimization**
- Parallel email processing using ThreadPoolExecutor
- Async AI processing for concurrent API calls
- Batch processing for large datasets
- Configurable worker counts

**FR-6: CLI Reporting**
- Enhanced gap analysis with detailed reporting
- **Gap type differentiation**: City gaps vs Country gaps with priority indicators
- **Priority indicators**: 🔴 Country gaps (critical), 🟡 City gaps (moderate)
- Incongruent event detection and flagging
- Clear visual indicators for gap status
- Progress tracking during processing
- Summary statistics and metrics by gap type

**FR-7: Incongruent Event Detection**
- Identify multiple trips from the same departure location
- Flag potential missed flights or booking errors
- Detect overlapping or conflicting travel entries
- Report suspicious patterns in travel data
- Provide recommendations for data cleanup

**FR-8: Enhanced Email Filtering**
- **Gap location search**: Include city and country names from identified gaps in email filtering
- **Contextual filtering**: Search for emails mentioning specific gap locations (e.g., "Bangkok", "Kuala Lumpur")
- **Comprehensive coverage**: Ensure no relevant emails are missed due to location-specific content
- **Smart keyword expansion**: Dynamically add gap location terms to search criteria

**FR-9: Multi-Flight AI Extraction**
- **Connected flight handling**: Extract multiple flight segments from single emails
- **Round trip detection**: Identify outbound and return flights in same email
- **Complex itineraries**: Handle multi-city trips and layover connections
- **Batch processing**: Process all flight details in one AI call per email
- **Structured output**: Return multiple travel entries per email when applicable

**FR-10: Country Code Normalization**
- **ISO 3166-1 alpha-2 compliance**: Ensure all country codes use standard 2-letter format
- **Automatic normalization**: Convert common variations to ISO codes (UK → GB, United Kingdom → GB)
- **AI prompt consistency**: Include country code standards in AI extraction prompts
- **Data validation**: Validate country codes during data processing
- **Consistency enforcement**: Prevent mixing of different country code formats

#### 5.2 Data Requirements

**Input Data**:
- Travel CSV file with existing entries
- Email export directory (.eml files)
- OpenAI API key for AI processing

**Output Data**:
- Complete travel itinerary CSV (timestamped filename: `all-travel-YYYYMMDD-HHMM.csv`)
- Gap analysis report with incongruent event detection
- Processing performance metrics
- Source file attribution for each entry
- CLI reports with gap status and recommendations

**Data Format**:
```csv
departure_country,departure_city,departure_date,departure_time,
arrival_country,arrival_city,arrival_date,arrival_time,notes,
source_file
```

**Country Code Standards**:
- **Format**: ISO 3166-1 alpha-2 country codes (2-letter codes)
- **Examples**: `GB` (United Kingdom), `US` (United States), `FR` (France), `DE` (Germany)
- **Consistency**: All country codes must use the same standard throughout the dataset
- **Normalization**: Convert common variations to ISO codes (e.g., `UK` → `GB`, `United Kingdom` → `GB`)

#### 5.3 Quality Requirements

**QR-1: Accuracy**
- 90%+ accuracy in travel information extraction
- Valid date parsing and validation
- Logical cohesiveness between entries

**QR-2: Performance**
- Process 25,000+ emails in under 10 minutes
- 3-8x speedup with parallelization
- Memory efficient processing

**QR-3: Reliability**
- Graceful error handling
- Robust date parsing
- API rate limit compliance

### 6. Technical Requirements

#### 6.1 Architecture

**Components**:
- Email Parser: .eml file processing
- AI Extractor: OpenAI GPT-4 integration
- Gap Analyzer: CSV analysis and gap identification
- Parallel Processor: Multi-threading and async processing
- Data Validator: Cohesiveness and quality checks

**Dependencies**:
- Python 3.8+
- OpenAI API
- BeautifulSoup4 for HTML parsing
- aiofiles for async file operations
- concurrent.futures for parallelization

#### 6.2 Performance Specifications

**Processing Capacity**:
- Handle 25,000+ email files
- Process 100+ travel entries
- Support multiple time periods

**Response Times**:
- Email parsing: < 0.1s per file
- AI extraction: < 5s per batch
- Total processing: < 10 minutes for full dataset

**Scalability**:
- Configurable worker counts
- Batch processing for large datasets
- Memory-efficient streaming

#### 6.3 Security Requirements

**Data Protection**:
- Local processing only (no data sent to external services except OpenAI)
- API key stored in .env file
- No persistent storage of email content

**API Security**:
- Rate limiting compliance
- Error handling for API failures
- Secure API key management

### 7. User Interface

#### 7.1 Command Line Interface

**Usage**:
```bash
python async_travel_parser.py
```

**Configuration**:
- CSV file path
- Email directory path
- Worker count settings
- API key management

#### 7.2 Output Format

**Console Output**:
- Processing progress indicators
- Gap identification results with detailed analysis
- Incongruent event detection and flagging
- Performance metrics
- Error messages and warnings
- Clear visual indicators for gap status (✅ filled, ❌ unfilled)
- Summary statistics and recommendations

**File Output**:
- Complete travel itinerary CSV
- Processing logs
- Performance reports

### 8. Success Metrics

#### 8.1 Performance Metrics

- **Processing Speed**: 3-8x improvement over sequential processing
- **Accuracy**: 90%+ correct travel information extraction
- **Completeness**: 95%+ gap filling success rate
- **Reliability**: < 5% processing failures

#### 8.2 User Experience Metrics

- **Ease of Use**: Single command execution
- **Time to Complete**: < 10 minutes for full dataset
- **Error Rate**: < 5% user intervention required
- **Output Quality**: Cohesive, logical travel itinerary

### 9. Implementation Plan

#### 9.1 Development Phases

**Phase 1: Core Functionality** ✅
- Basic email parsing
- Gap identification
- AI integration
- Sequential processing

**Phase 2: Performance Optimization** ✅
- Parallel processing implementation
- Async operations
- Performance testing
- Optimization tuning

**Phase 3: Production Ready** ✅
- Error handling improvements
- Documentation
- Testing and validation
- Cleanup and finalization

#### 9.2 Deliverables

**Code Files**:
- `async_travel_parser.py` - Main production script
- `requirements.txt` - Dependencies
- `PRD_Travel_Itinerary_Gap_Filler.md` - This document

**Documentation**:
- Usage instructions
- Performance benchmarks
- Troubleshooting guide

### 10. Future Enhancements

#### 10.1 Potential Improvements

- **GUI Interface**: Web-based or desktop application
- **Additional Data Sources**: Calendar integration, booking confirmations
- **Advanced Analytics**: Travel pattern analysis, cost tracking
- **Export Formats**: JSON, Excel, Google Sheets integration
- **Real-time Processing**: Live email monitoring

#### 10.2 Scalability Considerations

- **Cloud Processing**: AWS/Azure integration
- **Database Storage**: PostgreSQL/MongoDB for large datasets
- **API Rate Limiting**: Advanced queue management
- **Caching**: Redis for processed data

### 11. Risk Assessment

#### 11.1 Technical Risks

- **API Rate Limits**: Mitigated by parallel processing controls
- **Memory Usage**: Mitigated by batch processing
- **Data Quality**: Mitigated by validation and error handling

#### 11.2 Business Risks

- **Data Privacy**: Mitigated by local processing
- **Cost Control**: Mitigated by efficient API usage
- **Reliability**: Mitigated by comprehensive error handling

### 12. Conclusion

The Travel Itinerary Gap Filler successfully addresses the core problem of incomplete travel records by leveraging AI-powered email parsing and intelligent gap filling. The system provides significant performance improvements through parallelization and delivers a complete, cohesive travel itinerary from scattered email data.

**Key Success Factors**:
- Robust email parsing capabilities
- Accurate AI-powered information extraction
- Efficient parallel processing
- Comprehensive data validation
- User-friendly interface

The system is production-ready and provides a solid foundation for future enhancements and scalability improvements.

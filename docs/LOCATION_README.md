# NYC Location Extraction Consumer

**Ticket 3.3**: Spark Streaming Consumer for location extraction and NYC neighborhood assignment

## Overview

This consumer processes streaming data from Kafka and enriches it with NYC location information:

1. **Coordinate-based location** - Maps lat/lon to neighborhoods and boroughs
2. **Text-based extraction** - Uses spaCy NER to extract location mentions from text
3. **Normalization** - Standardizes location names using NYC neighborhood database
4. **Enrichment** - Adds neighborhood and borough metadata to all records

## Architecture

```
Kafka Topics → Location Consumer → Enriched Data
                      ↓
              ┌──────────────────┐
              │ Location Sources │
              ├──────────────────┤
              │ 1. Coordinates   │  311 data with lat/lon
              │ 2. Text NER      │  Reddit, Bluesky, RSS mentions
              │ 3. Normalization │  Standardize names
              └──────────────────┘
```

## Location Extraction Methods

### 1. Coordinate-based (Highest Accuracy)
- NYC 311 records include precise lat/lon coordinates
- Maps coordinates to neighborhoods using boundary data
- Extracts borough from ZIP code

### 2. Text-based NER (Medium Accuracy)
- Uses spaCy's Named Entity Recognition
- Extracts GPE (Geopolitical Entity), LOC (Location), FAC (Facility) entities
- Examples:
  - "Flu outbreak in Williamsburg" → extracts "Williamsburg"
  - "Brooklyn residents reporting symptoms" → extracts "Brooklyn"

### 3. Normalization (Standardization)
- Handles common aliases:
  - "UES" → "Upper East Side"
  - "Bed-Stuy" → "Bedford-Stuyvesant"
  - "Fidi" → "Financial District"
- Landmark to neighborhood mapping:
  - "Times Square" → "Midtown"
  - "Prospect Park" → "Park Slope"

## NYC Neighborhoods Database

Comprehensive mapping of 50+ NYC neighborhoods across 5 boroughs:

### Manhattan (16 neighborhoods)
- Upper East Side, Upper West Side, Harlem, East Harlem
- Washington Heights, Inwood, Midtown, Chelsea
- Greenwich Village, East Village, Lower East Side
- Chinatown, SoHo, TriBeCa, Financial District, Battery Park City

### Brooklyn (13 neighborhoods)
- Williamsburg, Greenpoint, Bushwick, Bedford-Stuyvesant
- Park Slope, Prospect Heights, Crown Heights, Flatbush
- Sunset Park, Bay Ridge, Brighton Beach, Coney Island, Downtown Brooklyn

### Queens (8 neighborhoods)
- Astoria, Long Island City, Flushing, Jackson Heights
- Elmhurst, Forest Hills, Jamaica, Rockaway

### Bronx (9 neighborhoods)
- Riverdale, Kingsbridge, Fordham, Belmont
- Morris Park, Pelham Bay, Hunts Point, Mott Haven, Concourse

### Staten Island (4 neighborhoods)
- St. George, Stapleton, Tottenville, New Dorp

## Installation

### 1. Install Dependencies

```bash
# Activate virtual environment
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm
```

### 2. Verify Kafka is Running

```bash
# Check Kafka is accessible
docker-compose ps | grep kafka

# Kafka should be on localhost:9092
```

## Usage

### Basic Usage

```bash
# Run with default settings
python run_location_consumer.py
```

### Advanced Options

```bash
# Custom Kafka servers and topics
python run_location_consumer.py \
  --kafka-servers localhost:9092 \
  --topics nyc_311,reddit,bluesky \
  --output-dir data/locations \
  --checkpoint-dir checkpoints/locations

# Use different spaCy model (more accurate but slower)
python run_location_consumer.py --spacy-model en_core_web_md
```

### Command-Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--kafka-servers` | localhost:9092 | Kafka bootstrap servers |
| `--topics` | reddit,bluesky,rss,nyc_311,nyc_press,nyc_covid | Comma-separated topics |
| `--output-dir` | data/locations | Output directory for enriched data |
| `--checkpoint-dir` | checkpoints/locations | Spark checkpoint directory |
| `--spacy-model` | en_core_web_sm | spaCy NER model (sm/md/lg) |

## Output Format

### Enriched Record Example

```json
{
  "post_id": "abc123",
  "source": "reddit",
  "text": "Anyone else sick with flu in Williamsburg?",
  "timestamp": "2025-12-05T10:00:00",
  "location_extraction": {
    "extracted_locations": ["Williamsburg"],
    "normalized_locations": ["Williamsburg"],
    "neighborhood": "Williamsburg",
    "borough": "Brooklyn",
    "location_source": "text_extraction"
  },
  "batch_id": 0,
  "processed_at": "2025-12-05T17:30:00.123456"
}
```

### NYC 311 Example (with coordinates)

```json
{
  "source": "NYC_311",
  "type": "Rodent",
  "location": {
    "zip": "11211",
    "lat": "40.7081",
    "lon": "-73.9571"
  },
  "location_extraction": {
    "extracted_locations": [],
    "normalized_locations": [],
    "neighborhood": "Williamsburg",
    "borough": "Brooklyn",
    "location_source": "coordinates"
  },
  "batch_id": 0,
  "processed_at": "2025-12-05T17:30:00.123456"
}
```

### Location Extraction Fields

| Field | Type | Description |
|-------|------|-------------|
| `extracted_locations` | List[str] | Raw location entities from NER |
| `normalized_locations` | List[str] | Standardized location names |
| `neighborhood` | str or null | NYC neighborhood name |
| `borough` | str or null | NYC borough (Manhattan, Brooklyn, etc.) |
| `location_source` | str or null | Source of location data (coordinates/text_extraction) |

## Output Files

Enriched records are written to JSON files in the output directory:

```
data/locations/
├── locations_batch_0_20251205_173000.json
├── locations_batch_1_20251205_173030.json
└── locations_batch_2_20251205_173100.json
```

## Performance

- **Throughput**: 5-20 records/sec (depends on text length and NER complexity)
- **NER Processing**: ~50-200ms per record
- **Coordinate Lookup**: ~1ms per record
- **Batch Size**: Configurable via Spark settings

### Performance Tuning

For higher throughput:

1. Use smaller spaCy model (`en_core_web_sm`)
2. Limit text length (currently 5000 chars max)
3. Increase Spark parallelism
4. Process only specific topics with location data

## Integration with Pipeline

### Downstream Use Cases

1. **Geospatial Analysis** - Map disease reports by neighborhood
2. **Hotspot Detection** - Identify outbreak clusters
3. **Borough-level Aggregation** - Track trends by borough
4. **Neighborhood Comparison** - Compare rates across neighborhoods

### Pipeline Flow

```
Scrapers → Kafka → Location Consumer → Enriched Data
                          ↓
                  Deduplication Consumer
                          ↓
                  Analysis & Visualization
```

## Troubleshooting

### spaCy Model Not Found

```bash
# Download the model
python -m spacy download en_core_web_sm

# Verify installation
python -c "import spacy; nlp = spacy.load('en_core_web_sm'); print('OK')"
```

### No Locations Extracted

- **Check text content**: Some records may not contain location mentions
- **Verify NER model**: Ensure spaCy model is loaded correctly
- **Review normalized locations**: Check if locations are NYC-related

### Low Accuracy

- **Upgrade spaCy model**: Use `en_core_web_md` or `en_core_web_lg`
- **Add more aliases**: Update `NYC_LOCATION_ALIASES` in `nyc_neighborhoods.py`
- **Refine boundaries**: Adjust neighborhood lat/lon ranges

## Development

### Adding New Neighborhoods

Edit `spark_consumers/nyc_neighborhoods.py`:

```python
BROOKLYN_NEIGHBORHOODS = {
    "New Neighborhood": {
        "lat_range": (40.XX, 40.YY),
        "lon_range": (-73.XX, -73.YY),
        "zips": ["11XXX"]
    }
}
```

### Adding Location Aliases

```python
NYC_LOCATION_ALIASES = {
    "nickname": "Official Neighborhood Name",
    "the heights": "Washington Heights"
}
```

## Testing

The consumer can be tested with sample Kafka data:

```bash
# Start Kafka
docker-compose up -d

# Publish test data (if test script exists)
python test_location_consumer.py

# Run consumer
python run_location_consumer.py --topics reddit

# Check output
ls -lh data/locations/
cat data/locations/*.json | python -m json.tool
```

## Dependencies

- **PySpark 3.5.3** - Streaming framework
- **spaCy 3.8.3** - NER and NLP
- **geopy 2.4.1** - Geospatial utilities (future use)
- **shapely 2.0.6** - Geometric operations (future use)

## Future Enhancements

1. **GeoJSON boundaries** - Use precise neighborhood polygons
2. **Distance calculations** - Find nearest neighborhood for edge cases
3. **Street address parsing** - Extract specific addresses
4. **Landmark database** - Expand landmark-to-neighborhood mapping
5. **Historical tracking** - Track location mentions over time

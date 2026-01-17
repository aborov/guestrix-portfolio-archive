# Airbnb Property Data Scraper

This system allows hosts to automatically import property data from their Airbnb listings into the concierge knowledge base, simplifying the property setup process.

## 🚀 Quick Start

### Prerequisites

1. **Install Dependencies**
   ```bash
   pip install beautifulsoup4 selenium lxml
   ```

2. **Chrome Browser** (for Selenium option)
   - Download ChromeDriver if you plan to use Selenium
   - Or install via Homebrew: `brew install chromedriver` (macOS)

### Basic Usage

#### Option 1: Preview Only (Recommended First)
```bash
python example_airbnb_import.py
```

#### Option 2: Command Line with Custom URL
```bash
python example_airbnb_import.py --user-url "https://www.airbnb.com/users/show/YOUR_USER_ID" --property-id "your_property_id"
```

#### Option 3: Direct Scraper Demo
```bash
python example_airbnb_import.py --demo-direct
```

## 📋 Features

### What Gets Scraped
- ✅ Property titles and descriptions
- ✅ Location information
- ✅ Complete amenities lists
- ✅ Property images
- ✅ Guest reviews and ratings
- ✅ Property type classification
- ✅ Host information

### What Gets Generated
- 🧠 **Knowledge Items**: Structured data for the concierge system
- 🔍 **AI-Enhanced Content**: Q&A pairs generated from property data
- 🏷️ **Categorized Information**: Amenities, location, and property details
- 📊 **Embeddings**: For improved search and retrieval

## 🛠️ Technical Implementation

### Core Components

#### 1. AirbnbScraper (`concierge/utils/airbnb_scraper.py`)
The main scraping engine that:
- Fetches user profile pages
- Discovers all listings for a user
- Extracts detailed property information
- Handles both static and dynamic content

#### 2. AirbnbPropertyIntegrator (`concierge/utils/airbnb_integration.py`)
The integration layer that:
- Connects scraper with knowledge base
- Enhances data with AI-generated content
- Manages duplicate detection and updates
- Provides summary and preview functions

### Usage Examples

#### Python API Usage

```python
from concierge.utils.airbnb_integration import preview_airbnb_properties, import_airbnb_properties

# Preview properties without importing
preview = preview_airbnb_properties(
    property_id="your_property_id",
    user_url="https://www.airbnb.com/users/show/13734172",
    use_selenium=False
)

print(f"Found {preview['property_count']} properties")
print(f"Total amenities: {preview['total_amenities']}")

# Import to knowledge base
result = import_airbnb_properties(
    property_id="your_property_id", 
    user_url="https://www.airbnb.com/users/show/13734172"
)

print(f"Created {result['knowledge_items_created']} knowledge items")
```

#### Direct Scraper Usage

```python
from concierge.utils.airbnb_scraper import AirbnbScraper

scraper = AirbnbScraper(use_selenium=False)
result = scraper.scrape_user_properties("https://www.airbnb.com/users/show/13734172")

# Save to file
with open('scraped_data.json', 'w') as f:
    json.dump(result, f, indent=2)
```

## 🎯 Use Cases

### For Hosts
1. **Quick Setup**: Import existing Airbnb data instead of manual entry
2. **Consistent Information**: Ensure concierge has accurate property details
3. **Comprehensive Amenities**: Auto-populate all available amenities
4. **Professional Descriptions**: Use proven Airbnb descriptions

### For Property Managers
1. **Bulk Import**: Process multiple properties at once
2. **Standardized Data**: Consistent format across all properties
3. **AI Enhancement**: Generate additional Q&A content automatically
4. **Easy Updates**: Re-import when property details change

## 🔧 Configuration Options

### Scraping Methods

#### Standard HTTP Requests (Default)
- **Pros**: Fast, lightweight, works for most pages
- **Cons**: May miss JavaScript-generated content
- **Use when**: Basic property information is sufficient

#### Selenium WebDriver
- **Pros**: Handles dynamic content, JavaScript, complex pages
- **Cons**: Slower, requires browser installation
- **Use when**: Standard method fails or more data needed

```python
# Use Selenium
scraper = AirbnbScraper(use_selenium=True, headless=True)
```

### Rate Limiting
The scraper includes built-in rate limiting:
- 1-2 second delays between requests
- Respectful of Airbnb's servers
- Configurable timing

## 📊 Output Format

### Preview Results
```json
{
  "property_count": 3,
  "total_amenities": 45,
  "unique_amenities_count": 32,
  "average_rating": 4.8,
  "total_reviews": 127,
  "listings_detail": [
    {
      "title": "Cozy Downtown Apartment",
      "location": "Downtown Portland, OR",
      "amenities_count": 15,
      "rating": 4.9,
      "review_count": 43,
      "url": "https://www.airbnb.com/rooms/12345"
    }
  ]
}
```

### Knowledge Items Generated
```json
{
  "title": "Property: Cozy Downtown Apartment",
  "content": "Property: Cozy Downtown Apartment\n\nLocation: Downtown Portland, OR\n\nDescription: Beautiful apartment in the heart of downtown...",
  "category": "property",
  "source": "airbnb_scraper",
  "metadata": {
    "listing_url": "https://www.airbnb.com/rooms/12345",
    "location": "Downtown Portland, OR",
    "amenity_count": 15,
    "rating": 4.9
  }
}
```

## 🚨 Important Considerations

### Legal and Ethical
- ✅ **Respect robots.txt**: The scraper follows website guidelines
- ✅ **Rate Limiting**: Implements delays to avoid overloading servers
- ✅ **Personal Use**: Intended for hosts scraping their own listings
- ⚠️ **Terms of Service**: Ensure compliance with Airbnb's ToS

### Technical Limitations
- **Dynamic Content**: Some data may require Selenium
- **Rate Limits**: Airbnb may impose restrictions on automated access
- **Page Structure**: Changes to Airbnb's website may require updates
- **Geographic Variations**: Different regions may have different layouts

### Best Practices
1. **Start with Preview**: Always preview before importing
2. **Use Standard Method First**: Try without Selenium initially
3. **Verify Data**: Review scraped data for accuracy
4. **Regular Updates**: Re-scrape when property details change
5. **Backup First**: Save existing knowledge base before bulk imports

## 🐛 Troubleshooting

### Common Issues

#### "No listings found"
- **Cause**: Profile page doesn't show listings or scraper can't find them
- **Solution**: Try with Selenium enabled, check if profile is public

#### "beautifulsoup4 not found"
- **Cause**: Missing dependency
- **Solution**: `pip install beautifulsoup4`

#### "ChromeDriver not found"
- **Cause**: Selenium can't find Chrome browser driver
- **Solution**: Install ChromeDriver or disable Selenium

#### Rate limiting errors
- **Cause**: Too many requests too quickly
- **Solution**: Wait and retry, check for IP blocking

### Debug Mode
Enable verbose logging:
```bash
python example_airbnb_import.py --verbose
```

## 🔮 Future Enhancements

### Planned Features
- [ ] **Batch Processing**: Handle multiple properties at once
- [ ] **Incremental Updates**: Only update changed information
- [ ] **Image Processing**: Download and optimize property images
- [ ] **Multi-platform Support**: Extend to VRBO, Booking.com
- [ ] **Scheduled Updates**: Automatic periodic re-scraping
- [ ] **Advanced AI**: Better content generation and categorization

### Integration Opportunities
- [ ] **Dashboard Integration**: Web interface for scraping
- [ ] **API Endpoints**: RESTful API for remote scraping
- [ ] **Webhook Support**: Trigger scraping from external events
- [ ] **Analytics**: Track scraping success rates and data quality

## 🤝 Contributing

### Development Setup
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run tests: `python -m pytest tests/`
4. Make changes and submit PR

### Adding New Scrapers
Follow the pattern in `airbnb_scraper.py`:
1. Create new scraper class
2. Implement required methods
3. Add to integration layer
4. Update documentation

## 📞 Support

For issues or questions:
1. Check the troubleshooting section above
2. Review the example code in `example_airbnb_import.py`
3. Test with the direct scraper demo first
4. Create an issue with detailed error information

## 📄 License

This project is part of the concierge system and follows the same license terms. 
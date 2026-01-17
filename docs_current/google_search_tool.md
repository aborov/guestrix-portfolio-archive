# Google Search Tool Integration for Guestrix

This document explains how the Google Search tool is integrated into the Guestrix text chat feature to enhance responses about property locations, nearby attractions, and other location-related questions.

## Overview

The Google Search tool allows the Gemini AI model to search the web for real-time information when answering guest questions, particularly for:

- Property locations and surrounding areas
- Nearby tourist attractions, restaurants, and points of interest
- Current events happening in the area
- Transportation options and directions
- Local recommendations

This integration works alongside our existing RAG (Retrieval-Augmented Generation) system. The RAG system continues to handle property-specific information, while the Google Search tool provides supplementary information about the surrounding area and real-time details.

## Implementation Details

### API Integration

The Google Search tool is implemented using Gemini's function calling capability. We define a search tool and pass it to the model during generation:

```python
search_tool = {
    "name": "searchTool",
    "description": "Search the web for real-time information.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to use to search the web."
            }
        },
        "required": ["query"]
    }
}

response = model.generate_content(
    prompt,
    tools=[search_tool],
    tool_config={"search_tool_use": "auto"}
)
```

The `tool_config={"search_tool_use": "auto"}` setting allows Gemini to automatically determine when to use the search tool based on the query content.

### Prompt Guidance

We've updated our prompts to include specific instructions for when the model should use the search tool:

```
IMPORTANT: Use the searchTool for location-related questions or to get up-to-date information about tourist attractions, 
restaurants, or events nearby. When asked about places to visit, local transportation, recommended restaurants, or current 
events in the area, use searchTool with a specific query to provide accurate and timely information.
```

This guidance helps the model decide when to rely on the provided context (property information and RAG results) and when to search for additional information.

### Fallback Behavior

If the search tool encounters an error or is unavailable, the system gracefully degrades to using just the Gemini model without search capabilities:

```python
try:
    # Generate response with Google Search tool
    response = model.generate_content(
        prompt,
        tools=[search_tool],
        tool_config={"search_tool_use": "auto"}
    )
except Exception as tool_error:
    # Fallback to regular generation if tool setup fails
    logging.error(f"Error setting up Google Search tool: {tool_error}")
    logging.warning("Falling back to standard Gemini generation without Google Search tool")
    response = model.generate_content(prompt)
```

## User Experience

From the guest's perspective, they will now receive more informative and up-to-date responses about the area surrounding their accommodation. For example:

- When asked "What are some good restaurants near the property?", the AI can provide current recommendations with actual restaurant names and details
- When asked "How far is the beach from here?", the AI can give more accurate distance information
- When asked "What events are happening this weekend?", the AI can provide current event information

The integration is seamless - guests won't know whether the information comes from our property database or from Google Search.

## Testing

A test script (`test_google_search_tool.py`) is provided to verify the functionality of the Google Search tool integration. This script:

1. Tests various location-related queries with different property contexts
2. Verifies that the model appropriately uses the search tool for relevant queries
3. Tests fallback behavior when needed

Run the test script using:

```bash
python test_google_search_tool.py
```

## Limitations

- The search tool adds some latency to responses compared to non-search responses
- Results are dependent on the quality of available search information for the location
- The model may occasionally use search when not needed or vice versa
- Very specific local information might still be missing if not available online

## Future Improvements

- Fine-tune when search is triggered with more specific prompt engineering
- Integrate location-specific knowledge sources beyond general web search
- Explore caching frequently requested location information
- Add the ability to display images of nearby attractions (when UI supports it) 
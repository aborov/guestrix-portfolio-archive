#!/bin/bash

# Path to the JavaScript file
JS_FILE="../concierge/static/js/guest_dashboard_main.js"

# Create a backup
cp "$JS_FILE" "${JS_FILE}.bak.$(date +%s)"

# Remove the duplicate fetchPropertyDetails function
START_LINE=$(grep -n "// Helper function to fetch property details" "$JS_FILE" | cut -d : -f 1)
END_LINE=$(grep -n "// Function to fetch property knowledge items from Firestore" "$JS_FILE" | cut -d : -f 1)
END_LINE=$((END_LINE - 1))

if [ -n "$START_LINE" ] && [ -n "$END_LINE" ]; then
    echo "Removing duplicate fetchPropertyDetails function from lines $START_LINE to $END_LINE"
    
    # Create a temporary file without the duplicate function
    sed -i.bak "${START_LINE},${END_LINE}c\\
// Helper function fetchPropertyDetails is imported from guest_dashboard_utils.js" "$JS_FILE"
fi

# Remove the duplicate fetchPropertyKnowledgeItems function
START_LINE=$(grep -n "// Function to fetch property knowledge items from Firestore" "$JS_FILE" | cut -d : -f 1)
END_LINE=$(grep -n "// Render Reservations" "$JS_FILE" | cut -d : -f 1)
END_LINE=$((END_LINE - 1))

if [ -n "$START_LINE" ] && [ -n "$END_LINE" ]; then
    echo "Removing duplicate fetchPropertyKnowledgeItems function from lines $START_LINE to $END_LINE"
    
    # Create a temporary file without the duplicate function
    sed -i.bak "${START_LINE},${END_LINE}c\\
// Helper function fetchPropertyKnowledgeItems is imported from guest_dashboard_utils.js" "$JS_FILE"
fi

echo "Fix completed! Original file backed up as ${JS_FILE}.bak.*" 
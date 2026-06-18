#!/bin/bash

# Test script for the Global Agricultural Machinery Demand Monitor API

echo "Testing API with sample posts..."

# Test 1: Single Kubota seat demand from Africa
curl -X POST http://localhost:3000/api/process-raw-data \
  -H "Content-Type: application/json" \
  -d '{
    "id": "test-001",
    "content": "URGENT! Looking for Kubota seat for L2201 tractor. Need immediately in Nigeria. Contact ASAP",
    "location": "Lagos, Nigeria",
    "source": "forum"
  }'

echo -e "\n\n--- Test 2: Multiple posts ---"

# Test 2: Array of posts
curl -X POST http://localhost:3000/api/process-raw-data \
  -H "Content-Type: application/json" \
  -d '[
    {
      "id": "test-002",
      "content": "Looking for Kubota filter for M7040. Urgent purchase needed in Kenya",
      "location": "Nairobi, Kenya",
      "source": "google_search"
    },
    {
      "id": "test-003",
      "content": "久保田 L3204 座椅 急购，需要立即发货到泰国曼谷",
      "location": "Bangkok, Thailand",
      "source": "web"
    },
    {
      "id": "test-004",
      "content": "Need Kubota seat urgently for our farm. Located in Vietnam",
      "location": "Ho Chi Minh City, Vietnam",
      "source": "forum"
    }
  ]'

echo -e "\n\n--- Test 3: Google Search API ---"

# Test 3: Manual Google Search trigger
curl -X POST http://localhost:3000/api/google-search \
  -H "Content-Type: application/json" \
  -d '{
    "keywords": ["Kubota tractor parts forum", "tractor seat replacement"]
  }'

echo -e "\n\nDone!"

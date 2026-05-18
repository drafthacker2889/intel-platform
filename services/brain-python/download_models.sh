#!/bin/bash
# Download multilingual spaCy models for brain-python

set -e

echo "Downloading spaCy models for multilingual support..."

# English model (small)
echo "Downloading en_core_web_sm..."
python -m spacy download en_core_web_sm

# Russian model
echo "Downloading ru_core_news_sm..."
python -m spacy download ru_core_news_sm

# Chinese model
echo "Downloading zh_core_web_sm..."
python -m spacy download zh_core_web_sm

# German model
echo "Downloading de_core_news_sm..."
python -m spacy download de_core_news_sm

echo "All multilingual spaCy models downloaded successfully!"

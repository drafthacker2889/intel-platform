# Download multilingual spaCy models for brain-python (Windows)

Write-Host "Downloading spaCy models for multilingual support..."

# English model (small)
Write-Host "Downloading en_core_web_sm..."
python -m spacy download en_core_web_sm

# Russian model
Write-Host "Downloading ru_core_news_sm..."
python -m spacy download ru_core_news_sm

# Chinese model
Write-Host "Downloading zh_core_web_sm..."
python -m spacy download zh_core_web_sm

# German model
Write-Host "Downloading de_core_news_sm..."
python -m spacy download de_core_news_sm

Write-Host "All multilingual spaCy models downloaded successfully!" -ForegroundColor Green

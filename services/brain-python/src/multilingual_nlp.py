"""
Multilingual NLP support: mBERT embeddings + language detection.

Handles: English, Russian, Chinese, German threat intelligence.
"""

import logging
import os
from typing import Any, List, Dict, Tuple
from functools import lru_cache

import spacy
from langdetect import detect_langs, LangDetectException


class MultilingualNLPManager:
    """
    Manages multilingual NLP with language detection and entity extraction.
    
    Supported languages: en, ru, zh, de
    Falls back to English model if language unsupported or detection fails.
    """
    
    # Language-to-spaCy model mapping
    LANGUAGE_MODELS = {
        "en": "en_core_web_sm",      # English
        "ru": "ru_core_news_sm",     # Russian
        "zh": "zh_core_web_sm",      # Chinese
        "de": "de_core_news_sm",     # German
    }
    
    # Language names
    LANGUAGE_NAMES = {
        "en": "English",
        "ru": "Russian",
        "zh": "Chinese",
        "de": "German",
    }
    
    def __init__(self, logger: logging.Logger, prefer_model: str = "en"):
        self.logger = logger
        self.prefer_model = prefer_model
        self._models: Dict[str, Any] = {}  # Lazy-loaded model cache
        self._load_model(prefer_model)  # Pre-load default
    
    def _load_model(self, lang_code: str):
        """Lazy-load spaCy model for language."""
        if lang_code in self._models:
            return self._models[lang_code]
        
        model_name = self.LANGUAGE_MODELS.get(lang_code, self.LANGUAGE_MODELS["en"])
        
        try:
            nlp = spacy.load(model_name)
            self._models[lang_code] = nlp
            self.logger.info(f'"Loaded {model_name} for language {lang_code}"')
            return nlp
        except OSError:
            self.logger.warning(
                f'"Model {model_name} not found, falling back to English"'
            )
            if "en" not in self._models:
                self._models["en"] = spacy.load("en_core_web_sm")
            return self._models["en"]
    
    def detect_language(self, text: str) -> Tuple[str, float]:
        """
        Detect language of text.
        
        Returns: (language_code, confidence)
        """
        if not text or len(text.strip()) < 10:
            return "en", 0.5  # Default to English for short text
        
        try:
            results = detect_langs(text[:500])
            # results is a list of Language objects sorted by probability desc
            code_map = {
                "en": "en", "ru": "ru", "zh-cn": "zh", "zh-tw": "zh", "de": "de",
            }
            for lang_result in results:
                mapped = code_map.get(lang_result.lang, None)
                if mapped:
                    return mapped, round(lang_result.prob, 4)
            # No supported language detected — fall back to English with low confidence
            return "en", round(results[0].prob if results else 0.3, 4)

        except LangDetectException:
            self.logger.debug('"Language detection failed, using English"')
            return "en", 0.3
    
    def extract_entities(self, text: str) -> List[Dict]:
        """
        Extract named entities from multilingual text.
        
        Returns list of entities with type and offsets.
        """
        lang_code, confidence = self.detect_language(text)
        
        if lang_code not in self.LANGUAGE_MODELS:
            lang_code = "en"
        
        nlp = self._load_model(lang_code)
        
        try:
            doc = nlp(text[:100000])  # Limit to 100K chars
            
            entities = []
            for ent in doc.ents:
                # Map spaCy labels to standard types
                entity_type = self._map_entity_type(ent.label_, lang_code)
                
                entities.append({
                    "text": ent.text,
                    "type": entity_type,
                    "start": ent.start_char,
                    "end": ent.end_char,
                    "spacy_label": ent.label_,
                    "language": lang_code,
                })
            
            return entities
        
        except Exception as e:
            self.logger.error(f'"Entity extraction failed for {lang_code}: {e}"')
            return []
    
    def _map_entity_type(self, spacy_label: str, lang_code: str) -> str:
        """
        Map spaCy entity labels to standard types.
        Different models use different label sets.
        """
        label_mapping = {
            # Common labels
            "PERSON": "PERSON",
            "PER": "PERSON",
            "ORG": "ORG",
            "ORGANIZATION": "ORG",
            "GPE": "LOCATION",
            "LOC": "LOCATION",
            "LOCATION": "LOCATION",
            "PRODUCT": "PRODUCT",
            "FACILITY": "LOCATION",
            # Email/domain detection
            "EMAIL": "EMAIL",
            "URL": "URL",
            # Fallback
        }
        
        return label_mapping.get(spacy_label, "ENTITY")
    
    def extract_keywords(self, text: str, keywords: List[str]) -> List[str]:
        """
        Extract relevant keywords from text (language-agnostic).
        """
        found = []
        text_lower = text.lower()
        
        for kw in keywords:
            if kw.lower() in text_lower:
                found.append(kw)
        
        return found
    
    def get_language_info(self, text: str) -> Dict:
        """Get language detection info for a document."""
        lang_code, confidence = self.detect_language(text)
        
        return {
            "language_code": lang_code,
            "language_name": self.LANGUAGE_NAMES.get(lang_code, "Unknown"),
            "detection_confidence": confidence,
            "supported": lang_code in self.LANGUAGE_MODELS,
        }

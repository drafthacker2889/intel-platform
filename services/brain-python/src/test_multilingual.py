"""
Unit tests for multilingual NLP module.
"""

import unittest
import logging
from src.multilingual_nlp import MultilingualNLPManager


class TestMultilingualNLP(unittest.TestCase):
    """Test cases for MultilingualNLPManager."""
    
    @classmethod
    def setUpClass(cls):
        """Setup test fixtures (run once)."""
        cls.logger = logging.getLogger("test")
        cls.nlp = MultilingualNLPManager(cls.logger)
    
    def test_language_detection_english(self):
        """Test detection of English text."""
        text = "LockBit leaked database of Fortune 500 company with 50000 records"
        lang_code, confidence = self.nlp.detect_language(text)
        
        self.assertEqual(lang_code, "en")
        self.assertGreater(confidence, 0.5)
    
    def test_language_detection_russian(self):
        """Test detection of Russian text."""
        text = "Лазарус украл базу данных компании Fortune 500 с 50000 записей"
        lang_code, confidence = self.nlp.detect_language(text)
        
        self.assertEqual(lang_code, "ru")
        self.assertGreater(confidence, 0.5)
    
    def test_language_detection_chinese(self):
        """Test detection of Chinese text."""
        text = "拉撒路集团窃取了财富500强公司的数据库，涉及50000条记录"
        lang_code, confidence = self.nlp.detect_language(text)
        
        self.assertEqual(lang_code, "zh")
        self.assertGreater(confidence, 0.5)
    
    def test_language_detection_german(self):
        """Test detection of German text."""
        text = "Lazarus stahl die Datenbank des Fortune-500-Unternehmens mit 50000 Datensätzen"
        lang_code, confidence = self.nlp.detect_language(text)
        
        self.assertEqual(lang_code, "de")
        self.assertGreater(confidence, 0.5)
    
    def test_language_detection_short_text(self):
        """Test detection of short text (defaults to English)."""
        text = "abc"
        lang_code, confidence = self.nlp.detect_language(text)
        
        self.assertEqual(lang_code, "en")
        self.assertLess(confidence, 0.5)
    
    def test_language_detection_empty_text(self):
        """Test detection of empty text."""
        text = ""
        lang_code, confidence = self.nlp.detect_language(text)
        
        self.assertEqual(lang_code, "en")
        self.assertLess(confidence, 0.5)
    
    def test_entity_extraction_english(self):
        """Test entity extraction from English text."""
        text = "LockBit attacked Fortune 500 company in New York"
        entities = self.nlp.extract_entities(text)
        
        self.assertGreater(len(entities), 0)
        entity_texts = [ent["text"] for ent in entities]
        entity_types = [ent["type"] for ent in entities]
        
        # Should have at least organization entities
        self.assertTrue(any(et in ["ORG", "ORGANIZATION"] for et in entity_types))
    
    def test_entity_extraction_russian(self):
        """Test entity extraction from Russian text."""
        text = "Лазарус украл базу данных Сбербанка"
        entities = self.nlp.extract_entities(text)
        
        self.assertGreater(len(entities), 0)
        
        # All entities should have language set to Russian
        for ent in entities:
            self.assertEqual(ent["language"], "ru")
    
    def test_entity_extraction_with_confidence(self):
        """Test that extracted entities have required fields."""
        text = "John Smith from Apple Inc contacted the FBI"
        entities = self.nlp.extract_entities(text)
        
        for ent in entities:
            self.assertIn("text", ent)
            self.assertIn("type", ent)
            self.assertIn("language", ent)
            self.assertIn("start", ent)
            self.assertIn("end", ent)
            self.assertIn("spacy_label", ent)
    
    def test_get_language_info(self):
        """Test get_language_info method."""
        text = "Это русский текст о безопасности"
        info = self.nlp.get_language_info(text)
        
        self.assertIn("language_code", info)
        self.assertIn("language_name", info)
        self.assertIn("detection_confidence", info)
        self.assertIn("supported", info)
        
        self.assertEqual(info["language_code"], "ru")
        self.assertEqual(info["language_name"], "Russian")
    
    def test_extract_keywords_english(self):
        """Test keyword extraction (language-agnostic)."""
        text = "admin password leaked from database dump"
        keywords = ["admin password", "database", "configuration", "backup"]
        
        found = self.nlp.extract_keywords(text, keywords)
        
        self.assertIn("admin password", found)
        self.assertIn("database", found)
        self.assertNotIn("configuration", found)
    
    def test_extract_keywords_case_insensitive(self):
        """Test keyword extraction is case-insensitive."""
        text = "ADMIN PASSWORD found in DATABASE"
        keywords = ["admin password", "database"]
        
        found = self.nlp.extract_keywords(text, keywords)
        
        self.assertEqual(len(found), 2)
    
    def test_language_names_mapping(self):
        """Test that all supported languages have names."""
        for lang_code in self.nlp.LANGUAGE_NAMES:
            self.assertIn(lang_code, self.nlp.LANGUAGE_MODELS)
            self.assertIsInstance(self.nlp.LANGUAGE_NAMES[lang_code], str)
            self.assertGreater(len(self.nlp.LANGUAGE_NAMES[lang_code]), 0)
    
    def test_model_lazy_loading(self):
        """Test that models are lazy-loaded on demand."""
        initial_count = len(self.nlp._models)
        
        # Extract entities from Russian text (forces load)
        self.nlp.extract_entities("Русский текст")
        
        # Should have loaded Russian model
        final_count = len(self.nlp._models)
        self.assertGreaterEqual(final_count, initial_count)
    
    def test_entity_type_mapping(self):
        """Test entity type mapping to standard types."""
        # Test internal mapping function
        mappings = [
            ("PERSON", "PERSON"),
            ("PER", "PERSON"),
            ("ORG", "ORG"),
            ("GPE", "LOCATION"),
            ("LOC", "LOCATION"),
            ("PRODUCT", "PRODUCT"),
        ]
        
        for spacy_label, expected_type in mappings:
            mapped = self.nlp._map_entity_type(spacy_label, "en")
            self.assertEqual(mapped, expected_type)
    
    def test_text_truncation(self):
        """Test that very long text is truncated before processing."""
        very_long_text = "word " * 50000  # 250,000 characters
        
        # Should not raise exception (max 100k chars)
        entities = self.nlp.extract_entities(very_long_text)
        
        # Should return (possibly empty) list
        self.assertIsInstance(entities, list)


class TestMultilingualDataGenerator(unittest.TestCase):
    """Test cases for synthetic multilingual data generation."""
    
    def test_generate_critical_sample(self):
        """Test CRITICAL sample generation."""
        from generate_multilingual_data import MultilingualDataGenerator
        
        gen = MultilingualDataGenerator()
        
        for lang in ["en", "ru", "zh", "de"]:
            sample = gen._generate_critical_sample(lang)
            
            self.assertIn("text", sample)
            self.assertIn("expected_label", sample)
            self.assertIn("language", sample)
            self.assertIn("entities", sample)
            
            self.assertEqual(sample["expected_label"], "CRITICAL")
            self.assertEqual(sample["language"], lang)
            self.assertGreater(len(sample["text"]), 0)
    
    def test_generate_high_sample(self):
        """Test HIGH sample generation."""
        from generate_multilingual_data import MultilingualDataGenerator
        
        gen = MultilingualDataGenerator()
        sample = gen._generate_high_sample("en")
        
        self.assertEqual(sample["expected_label"], "HIGH")
    
    def test_generate_medium_sample(self):
        """Test MEDIUM sample generation."""
        from generate_multilingual_data import MultilingualDataGenerator
        
        gen = MultilingualDataGenerator()
        sample = gen._generate_medium_sample("ru")
        
        self.assertEqual(sample["expected_label"], "MEDIUM")
        self.assertEqual(sample["language"], "ru")
    
    def test_generate_low_sample(self):
        """Test LOW sample generation."""
        from generate_multilingual_data import MultilingualDataGenerator
        
        gen = MultilingualDataGenerator()
        sample = gen._generate_low_sample("zh")
        
        self.assertEqual(sample["expected_label"], "LOW")
        self.assertEqual(sample["language"], "zh")
    
    def test_full_dataset_generation(self):
        """Test full multilingual dataset generation."""
        from generate_multilingual_data import MultilingualDataGenerator
        
        gen = MultilingualDataGenerator()
        samples = gen.generate(samples_per_language=100)
        
        # Should generate 400 samples (100 per language)
        self.assertEqual(len(samples), 400)
        
        # Check distribution
        by_lang = {}
        by_label = {}
        
        for sample in samples:
            lang = sample["language"]
            label = sample["expected_label"]
            
            by_lang[lang] = by_lang.get(lang, 0) + 1
            by_label[label] = by_label.get(label, 0) + 1
        
        # Each language should have 100 samples
        for lang in ["en", "ru", "zh", "de"]:
            self.assertEqual(by_lang[lang], 100)
        
        # Check label distribution (roughly) across all generated samples
        total = len(samples)
        expected_critical = int(total * 0.10)
        expected_high = int(total * 0.30)

        self.assertLessEqual(abs(by_label["CRITICAL"] - expected_critical), 4)
        self.assertLessEqual(abs(by_label["HIGH"] - expected_high), 8)


if __name__ == "__main__":
    unittest.main()

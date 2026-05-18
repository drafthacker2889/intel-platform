"""
Language-specific ML model routing and pipeline management.

Routes documents to language-specific risk models for improved accuracy.
Supports independent models trained on language-specific threat data.
"""

import logging
import os
from typing import Dict, Optional, Tuple
from pathlib import Path

import joblib
import numpy as np


class LanguageModelRouter:
    """
    Routes documents to language-specific risk models.
    
    Falls back to default model if language-specific model unavailable.
    """
    
    SUPPORTED_LANGUAGES = {"en", "ru", "zh", "de"}
    DEFAULT_LANGUAGE = "en"
    
    def __init__(self, model_path: Path, logger: logging.Logger):
        """
        Initialize router with models from specified directory.
        
        Expected structure:
            model_path/
            ├── risk_model.joblib              (default English model)
            ├── risk_model_en.joblib           (explicit English)
            ├── risk_model_ru.joblib           (Russian)
            ├── risk_model_zh.joblib           (Chinese)
            ├── risk_model_de.joblib           (German)
            ├── scaler.pkl                     (default scaler)
            ├── scaler_en.pkl                  (English scaler)
            ├── scaler_ru.pkl                  (Russian scaler)
            ├── scaler_zh.pkl                  (Chinese scaler)
            └── scaler_de.pkl                  (German scaler)
        """
        self.model_path = Path(model_path)
        self.logger = logger
        self._models = {}      # Cache: lang_code -> model
        self._scalers = {}     # Cache: lang_code -> scaler
        
        # Load default model (English) first
        self._load_model("en")
    
    def _load_model(self, lang_code: str) -> bool:
        """Load model and scaler for language. Returns True if successful."""
        if lang_code in self._models:
            return True
        
        # Try language-specific model first
        lang_model_path = self.model_path / f"risk_model_{lang_code}.joblib"
        if lang_model_path.exists():
            try:
                model = joblib.load(lang_model_path)
                self._models[lang_code] = model
                self.logger.info(f'Loaded {lang_code} model: {lang_model_path}')
            except Exception as e:
                self.logger.warning(f'Failed to load {lang_code} model: {e}')
                return False
        else:
            # Fallback to default model if language-specific not found
            default_model_path = self.model_path / "risk_model.joblib"
            if default_model_path.exists() and lang_code != "en":
                try:
                    model = joblib.load(default_model_path)
                    self._models[lang_code] = model
                    self.logger.debug(f'Using default model for {lang_code}')
                except Exception as e:
                    self.logger.warning(f'Failed to load default model: {e}')
                    return False
            else:
                return False
        
        # Load corresponding scaler
        lang_scaler_path = self.model_path / f"scaler_{lang_code}.pkl"
        if lang_scaler_path.exists():
            try:
                scaler = joblib.load(lang_scaler_path)
                self._scalers[lang_code] = scaler
                self.logger.debug(f'Loaded {lang_code} scaler')
            except Exception as e:
                self.logger.warning(f'Failed to load {lang_code} scaler: {e}')
        else:
            # Fallback to default scaler
            default_scaler_path = self.model_path / "scaler.pkl"
            if default_scaler_path.exists():
                try:
                    scaler = joblib.load(default_scaler_path)
                    self._scalers[lang_code] = scaler
                    self.logger.debug(f'Using default scaler for {lang_code}')
                except Exception as e:
                    self.logger.warning(f'Failed to load scaler: {e}')
        
        return lang_code in self._models
    
    def predict_risk(
        self,
        features: np.ndarray,
        lang_code: str,
    ) -> Tuple[float, str, np.ndarray]:
        """
        Predict risk score and label using language-specific model.
        
        Args:
            features: Feature vector (output of featurize())
            lang_code: Language code (en, ru, zh, de, or auto-detected)
        
        Returns:
            (risk_score, risk_label, probabilities)
            - risk_score: 0.0-1.0 (higher = more risky)
            - risk_label: "LOW", "MEDIUM", "HIGH", "CRITICAL"
            - probabilities: [p_low, p_medium, p_high, p_critical]
        """
        # Normalize language code
        if lang_code not in self.SUPPORTED_LANGUAGES:
            self.logger.debug(f'Unsupported language {lang_code}, using default')
            lang_code = self.DEFAULT_LANGUAGE
        
        # Load model if not cached
        if lang_code not in self._models:
            if not self._load_model(lang_code):
                self.logger.warning(f'Could not load model for {lang_code}, using default')
                lang_code = self.DEFAULT_LANGUAGE
                if not self._load_model(lang_code):
                    raise RuntimeError(f'No models available for {lang_code}')
        
        model = self._models[lang_code]
        scaler = self._scalers.get(lang_code)
        
        # Scale features if scaler available
        if scaler is not None:
            features_scaled = scaler.transform([features])[0]
        else:
            features_scaled = features
        
        # Predict
        prediction = model.predict([features_scaled])[0]  # 0-3 (LOW-CRITICAL)
        probabilities = model.predict_proba([features_scaled])[0]
        
        # Map numeric prediction to label
        labels = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "CRITICAL"}
        risk_label = labels.get(prediction, "LOW")
        
        # Risk score: weighted combination of prediction and probability
        risk_score = (prediction * 0.4 + np.max(probabilities) * 0.6) / 3.0
        
        return risk_score, risk_label, probabilities
    
    def get_language_model_info(self, lang_code: str) -> Dict:
        """Get information about available model for language."""
        if lang_code not in self.SUPPORTED_LANGUAGES:
            lang_code = self.DEFAULT_LANGUAGE
        
        model_path = self.model_path / f"risk_model_{lang_code}.joblib"
        default_model_path = self.model_path / "risk_model.joblib"
        scaler_path = self.model_path / f"scaler_{lang_code}.pkl"
        
        info = {
            "language": lang_code,
            "model_available": model_path.exists() or default_model_path.exists(),
            "model_type": "language-specific" if model_path.exists() else "default",
            "model_path": str(model_path),
            "has_scaler": scaler_path.exists(),
            "cached": lang_code in self._models,
        }
        
        if model_path.exists():
            info["model_size_mb"] = model_path.stat().st_size / 1024 / 1024
        elif default_model_path.exists():
            info["model_size_mb"] = default_model_path.stat().st_size / 1024 / 1024
        
        return info
    
    def get_all_available_models(self) -> Dict[str, Dict]:
        """Get info about all available models."""
        available = {}
        
        for lang_code in self.SUPPORTED_LANGUAGES:
            info = self.get_language_model_info(lang_code)
            if info["model_available"]:
                available[lang_code] = info
        
        return available


class LanguagePipeline:
    """
    Language-specific document processing pipeline.
    
    Handles language detection, feature extraction, and risk scoring
    with language-specific considerations.
    """
    
    def __init__(
        self,
        model_router: LanguageModelRouter,
        logger: logging.Logger,
    ):
        self.router = model_router
        self.logger = logger
    
    def process_document(
        self,
        text: str,
        lang_code: str,
        features: np.ndarray,
    ) -> Dict:
        """
        Process document through language-specific pipeline.
        
        Args:
            text: Document text
            lang_code: Detected language code
            features: Pre-computed feature vector
        
        Returns:
            Dict with risk assessment and language info
        """
        # Get risk prediction
        risk_score, risk_label, probabilities = self.router.predict_risk(
            features, lang_code
        )
        
        # Get model info
        model_info = self.router.get_language_model_info(lang_code)
        
        return {
            "language_code": lang_code,
            "risk_score": float(risk_score),
            "risk_label": risk_label,
            "risk_probabilities": {
                "low": float(probabilities[0]),
                "medium": float(probabilities[1]),
                "high": float(probabilities[2]),
                "critical": float(probabilities[3]),
            },
            "model_used": model_info["model_type"],
            "confidence": float(np.max(probabilities)),
        }


class LanguageSpecificFeatures:
    """
    Extract language-specific features for improved risk scoring.
    """
    
    # Language-specific threat keywords
    LANGUAGE_KEYWORDS = {
        "en": [
            "database", "leak", "breach", "stolen", "compromised",
            "exploit", "vulnerability", "malware", "ransomware",
            "credential", "password", "admin", "root", "access",
        ],
        "ru": [
            "база", "утечка", "взлом", "украдено", "скомпрометировано",
            "эксплуатация", "уязвимость", "вредонос", "вымоготель",
            "учетные данные", "пароль", "администратор", "рут", "доступ",
        ],
        "zh": [
            "数据库", "泄露", "违规", "被盗", "被入侵",
            "利用", "漏洞", "恶意软件", "勒索软件",
            "凭证", "密码", "管理员", "访问权限",
        ],
        "de": [
            "datenbank", "lecks", "verstoß", "gestohlen", "kompromittiert",
            "ausnutzung", "sicherheitslücke", "malware", "ransomware",
            "anmeldeinformation", "passwort", "administrator", "zugriff",
        ],
    }
    
    @staticmethod
    def extract_language_keywords(text: str, lang_code: str) -> int:
        """Count language-specific threat keywords in text."""
        keywords = LanguageSpecificFeatures.LANGUAGE_KEYWORDS.get(lang_code, [])
        text_lower = text.lower()
        
        count = sum(1 for kw in keywords if kw.lower() in text_lower)
        return count
    
    @staticmethod
    def detect_suspicious_patterns(text: str, lang_code: str) -> int:
        """Detect language-specific suspicious patterns."""
        score = 0
        
        if lang_code == "en":
            # English-specific patterns
            if "admin password" in text.lower():
                score += 3
            if "database dump" in text.lower():
                score += 2
        
        elif lang_code == "ru":
            # Russian-specific patterns
            if "утечка данных" in text.lower():
                score += 3
            if "база данных" in text.lower():
                score += 2
        
        elif lang_code == "zh":
            # Chinese-specific patterns
            if "数据泄露" in text:
                score += 3
            if "数据库" in text:
                score += 2
        
        elif lang_code == "de":
            # German-specific patterns
            if "datenleck" in text.lower():
                score += 3
            if "datenbank" in text.lower():
                score += 2
        
        return score

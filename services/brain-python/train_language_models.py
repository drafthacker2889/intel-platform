"""
Train language-specific risk scoring models.

Trains separate RandomForest classifiers for each language (en, ru, zh, de)
using language-localized synthetic training data.
"""

import json
import logging
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LanguageSpecificModelTrainer:
    """Train per-language risk models."""
    
    LANGUAGES = ["en", "ru", "zh", "de"]
    
    def __init__(self, data_path: Path, model_path: Path):
        self.data_path = Path(data_path)
        self.model_path = Path(model_path)
        self.model_path.mkdir(parents=True, exist_ok=True)
    
    def load_language_data(self, lang_code: str) -> tuple:
        """Load synthetic data for specific language."""
        data_file = self.data_path / f"multilingual_eval_cases.json"
        
        if not data_file.exists():
            logger.warning(f'Data file {data_file} not found')
            return None, None
        
        with open(data_file, 'r', encoding='utf-8') as f:
            all_data = json.load(f)
        
        # Filter data for language
        lang_data = [item for item in all_data if item.get("language") == lang_code]
        
        logger.info(f'Loaded {len(lang_data)} samples for {lang_code}')
        
        if not lang_data:
            logger.warning(f'No data found for language {lang_code}')
            return None, None
        
        # Extract features and labels
        X = np.array([self._extract_features(item) for item in lang_data])
        y = np.array([self._label_to_int(item.get("risk_label", "LOW")) for item in lang_data])
        
        return X, y
    
    def _extract_features(self, item: dict) -> list:
        """Extract features from data item."""
        text = item.get("text", "")
        entities = item.get("entities", [])
        keywords = item.get("keywords", [])
        
        return [
            len(entities),          # entity_count
            len(keywords),          # keyword_count
            len(text),              # text_length
            text.count("@"),        # @_count
            text.count("://"),      # url_count
        ]
    
    def _label_to_int(self, label: str) -> int:
        """Convert risk label to integer."""
        mapping = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
        return mapping.get(label, 0)
    
    def _int_to_label(self, value: int) -> str:
        """Convert integer to risk label."""
        mapping = {0: "LOW", 1: "MEDIUM", 2: "HIGH", 3: "CRITICAL"}
        return mapping.get(value, "LOW")
    
    def train_language_model(self, lang_code: str) -> dict:
        """Train RandomForest model for specific language."""
        logger.info(f'Training model for {lang_code}...')
        
        # Load data
        X, y = self.load_language_data(lang_code)
        if X is None:
            logger.error(f'Could not load data for {lang_code}')
            return {"status": "error", "language": lang_code}
        
        # Split data
        n_samples = len(X)
        split_idx = int(0.8 * n_samples)
        indices = np.random.permutation(n_samples)
        
        X_train = X[indices[:split_idx]]
        X_test = X[indices[split_idx:]]
        y_train = y[indices[:split_idx]]
        y_test = y[indices[split_idx:]]
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Train model
        model = RandomForestClassifier(
            n_estimators=150,
            max_depth=8,
            min_samples_split=5,
            min_samples_leaf=2,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train_scaled, y_train)
        
        # Evaluate
        train_score = model.score(X_train_scaled, y_train)
        test_score = model.score(X_test_scaled, y_test)
        
        # Cross-validation
        cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)
        cv_scores = cross_val_score(
            model, X_train_scaled, y_train, cv=cv, scoring="f1_weighted"
        )
        
        # Per-class metrics
        predictions = model.predict(X_test_scaled)
        per_class_accuracy = {}
        for label in range(4):
            mask = y_test == label
            if mask.sum() > 0:
                accuracy = (predictions[mask] == y_test[mask]).sum() / mask.sum()
                per_class_accuracy[self._int_to_label(label)] = accuracy
        
        # Save model
        model_path = self.model_path / f"risk_model_{lang_code}.joblib"
        joblib.dump(model, model_path)
        
        # Save scaler
        scaler_path = self.model_path / f"scaler_{lang_code}.pkl"
        joblib.dump(scaler, scaler_path)
        
        logger.info(f'{lang_code} model training complete')
        logger.info(f'  Train accuracy: {train_score:.4f}')
        logger.info(f'  Test accuracy: {test_score:.4f}')
        logger.info(f'  CV F1 (mean): {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})')
        
        return {
            "status": "success",
            "language": lang_code,
            "train_accuracy": train_score,
            "test_accuracy": test_score,
            "cv_f1_mean": cv_scores.mean(),
            "cv_f1_std": cv_scores.std(),
            "per_class_accuracy": per_class_accuracy,
            "model_path": str(model_path),
            "scaler_path": str(scaler_path),
            "train_samples": len(X_train),
            "test_samples": len(X_test),
        }
    
    def train_all_languages(self) -> dict:
        """Train models for all supported languages."""
        results = {}
        
        for lang_code in self.LANGUAGES:
            logger.info(f'\\n=== Training {lang_code} model ===')
            result = self.train_language_model(lang_code)
            results[lang_code] = result
        
        logger.info(f'\\n=== Training Summary ===')
        for lang_code, result in results.items():
            if result["status"] == "success":
                logger.info(
                    f'{lang_code}: test_acc={result["test_accuracy"]:.4f}, '
                    f'cv_f1={result["cv_f1_mean"]:.4f}'
                )
        
        return results


def main():
    """Train all language-specific models."""
    script_dir = Path(__file__).parent
    data_path = script_dir.parent / "evals"
    model_path = script_dir.parent / "models"
    
    trainer = LanguageSpecificModelTrainer(data_path, model_path)
    results = trainer.train_all_languages()
    
    # Save results summary
    summary_path = model_path / "training_results.json"
    with open(summary_path, 'w') as f:
        # Convert numpy types for JSON serialization
        results_serializable = {}
        for lang, data in results.items():
            if isinstance(data, dict):
                data_copy = data.copy()
                for key, value in data_copy.items():
                    if isinstance(value, np.floating):
                        data_copy[key] = float(value)
                    elif isinstance(value, dict):
                        for k, v in value.items():
                            if isinstance(v, np.floating):
                                value[k] = float(v)
                results_serializable[lang] = data_copy
            else:
                results_serializable[lang] = data
        
        json.dump(results_serializable, f, indent=2)
    
    logger.info(f'\\nResults saved to {summary_path}')


if __name__ == "__main__":
    main()

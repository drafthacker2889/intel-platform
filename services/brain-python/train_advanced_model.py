"""
Advanced ML model training with synthetic data + data augmentation.

Combines English and multilingual synthetic datasets with augmentation techniques:
- Class balancing (handle imbalanced labels)
- Cross-validation with stratification
- Feature importance analysis
- Model interpretability
"""

import json
import logging
import sys
from pathlib import Path
from typing import List, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score, roc_curve,
    precision_recall_fscore_support,
)
import joblib

# Add src to path for featurize import
sys.path.insert(0, str(Path(__file__).parent / "src"))
from featurize import featurize


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("train_advanced")


class SyntheticDataLoader:
    """Load and combine English + multilingual synthetic datasets."""
    
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
    
    def load(self) -> Tuple[List[str], List[str]]:
        """Load both English and multilingual datasets."""
        all_texts = []
        all_labels = []
        
        # Load English synthetic data
        en_path = self.base_path / "evals" / "risk_eval_cases.json"
        if en_path.exists():
            logger.info(f"Loading English synthetic data from {en_path}")
            with open(en_path, "r", encoding="utf-8") as f:
                en_samples = json.load(f)
            
            for sample in en_samples:
                all_texts.append(sample["text"])
                all_labels.append(sample["expected_label"])
            
            logger.info(f"Loaded {len(en_samples)} English samples")
        else:
            logger.warning(f"English dataset not found: {en_path}")
        
        # Load multilingual synthetic data
        ml_path = self.base_path / "evals" / "multilingual_eval_cases.json"
        if ml_path.exists():
            logger.info(f"Loading multilingual synthetic data from {ml_path}")
            with open(ml_path, "r", encoding="utf-8") as f:
                ml_samples = json.load(f)
            
            for sample in ml_samples:
                all_texts.append(sample["text"])
                all_labels.append(sample["expected_label"])
            
            logger.info(f"Loaded {len(ml_samples)} multilingual samples")
        else:
            logger.warning(f"Multilingual dataset not found: {ml_path}")
        
        if not all_texts:
            raise ValueError("No training data found. Run generate_synthetic_data.py and generate_multilingual_data.py first.")
        
        logger.info(f"Total dataset size: {len(all_texts)} samples")
        
        return all_texts, all_labels


class DataAugmentor:
    """Apply data augmentation techniques to synthetic data."""
    
    @staticmethod
    def augment_by_paraphrasing(texts: List[str], labels: List[str]) -> Tuple[List[str], List[str]]:
        """
        Simple augmentation: add variations of high-risk sentences.
        In production, could use back-translation or semantic paraphrasing.
        """
        augmented_texts = []
        augmented_labels = []
        
        # Paraphrase templates for CRITICAL/HIGH samples
        paraphrase_map = {
            "CRITICAL": [
                lambda t: f"URGENT: {t}",
                lambda t: f"[BREACH] {t}",
                lambda t: f"{t} (verified)",
                lambda t: f"⚠️ WARNING: {t}",
            ],
            "HIGH": [
                lambda t: f"[ALERT] {t}",
                lambda t: f"Risk: {t}",
                lambda t: f"{t} [RESEARCH]",
            ],
        }
        
        for text, label in zip(texts, labels):
            augmented_texts.append(text)
            augmented_labels.append(label)
            
            # Add augmented versions for high-risk labels
            if label in paraphrase_map:
                for transform in paraphrase_map[label][:2]:  # Limit to 2 per sample
                    try:
                        augmented_text = transform(text)
                        augmented_texts.append(augmented_text)
                        augmented_labels.append(label)
                    except:
                        pass  # Skip failed transforms
        
        logger.info(f"Data augmentation: {len(texts)} → {len(augmented_texts)} samples")
        return augmented_texts, augmented_labels


class AdvancedModelTrainer:
    """Train RandomForest with advanced techniques."""
    
    LABEL_TO_CLASS = {
        "CRITICAL": 3,
        "HIGH": 2,
        "MEDIUM": 1,
        "LOW": 0,
    }
    
    CLASS_NAMES = {v: k for k, v in LABEL_TO_CLASS.items()}
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.label_mapping = self.LABEL_TO_CLASS
    
    def train(self, texts: List[str], labels: List[str], model_path: Path):
        """Train model with advanced techniques."""
        
        # Convert labels to numeric
        numeric_labels = np.array([self.label_mapping[label] for label in labels])
        
        logger.info("Extracting features from texts...")
        X = np.array([featurize(text, []) for text in texts])
        y = numeric_labels
        
        logger.info(f"Feature matrix shape: {X.shape}")
        logger.info(f"Label distribution: {np.bincount(y)}")
        
        # Split with stratification
        X_train, X_test, y_train, y_test = train_test_split(
            X, y,
            test_size=0.2,
            stratify=y,
            random_state=42,
        )
        
        logger.info(f"Train size: {len(X_train)}, Test size: {len(X_test)}")
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train with class weighting (handle class imbalance)
        logger.info("Training RandomForestClassifier...")
        self.model = RandomForestClassifier(
            n_estimators=150,
            max_depth=8,
            min_samples_split=5,
            min_samples_leaf=2,
            class_weight="balanced",  # Handle imbalanced classes
            n_jobs=-1,
            random_state=42,
        )
        
        self.model.fit(X_train_scaled, y_train)
        
        # Cross-validation
        logger.info("Running cross-validation...")
        k = min(3, np.min(np.bincount(y_train)))  # k-fold where k = min(3, smallest class size)
        cv_scores = cross_val_score(
            self.model, X_train_scaled, y_train,
            cv=StratifiedKFold(n_splits=k),
            scoring="f1_weighted",
        )
        logger.info(f"Cross-val scores (F1): {cv_scores} (mean: {cv_scores.mean():.3f} ± {cv_scores.std():.3f})")
        
        # Evaluate on test set
        y_pred = self.model.predict(X_test_scaled)
        y_pred_proba = self.model.predict_proba(X_test_scaled)
        
        logger.info("\n" + "="*60)
        logger.info("TEST SET EVALUATION")
        logger.info("="*60)
        
        logger.info(f"\nClassification Report:\n{classification_report(y_test, y_pred, target_names=list(self.CLASS_NAMES.values()))}")
        
        logger.info(f"\nConfusion Matrix:\n{confusion_matrix(y_test, y_pred)}")
        
        # Precision, Recall, F1 per class
        precision, recall, f1, support = precision_recall_fscore_support(y_test, y_pred, average=None)
        for i, class_name in self.CLASS_NAMES.items():
            logger.info(f"{class_name:12} | P={precision[i]:.3f} R={recall[i]:.3f} F1={f1[i]:.3f} Support={support[i]}")
        
        # ROC-AUC (one-vs-rest)
        try:
            roc_auc = roc_auc_score(y_test, y_pred_proba, multi_class="ovr", average="weighted")
            logger.info(f"ROC-AUC (weighted): {roc_auc:.3f}")
        except Exception as e:
            logger.warning(f"ROC-AUC calculation failed: {e}")
        
        # Feature importance
        logger.info(f"\n{'='*60}")
        logger.info("FEATURE IMPORTANCE")
        logger.info(f"{'='*60}")
        
        feature_names = ["keyword_count", "entity_count", "text_length", "url_count", "@_count"]
        importances = self.model.feature_importances_
        sorted_idx = np.argsort(importances)[::-1]
        
        for idx in sorted_idx:
            logger.info(f"{feature_names[idx]:20} {importances[idx]:6.3f}")
        
        # Training accuracy
        y_train_pred = self.model.predict(X_train_scaled)
        train_accuracy = np.mean(y_train_pred == y_train)
        logger.info(f"\nTraining accuracy: {train_accuracy:.3f}")
        logger.info(f"Test accuracy: {np.mean(y_pred == y_test):.3f}")
        
        # Save model
        logger.info(f"\nSaving model to {model_path}...")
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, model_path)
        
        # Save scaler
        scaler_path = model_path.parent / "scaler.pkl"
        joblib.dump(self.scaler, scaler_path)
        logger.info(f"Saved scaler to {scaler_path}")
        
        logger.info("Training complete! ✓")


def main():
    base_path = Path(__file__).parent
    
    # Load data
    loader = SyntheticDataLoader(base_path)
    texts, labels = loader.load()
    
    # Apply augmentation
    augmentor = DataAugmentor()
    texts_aug, labels_aug = augmentor.augment_by_paraphrasing(texts, labels)
    
    # Train model
    trainer = AdvancedModelTrainer()
    model_path = base_path / "models" / "risk_model_advanced.joblib"
    trainer.train(texts_aug, labels_aug, model_path)
    
    # Also save with original name for compatibility
    compat_path = base_path / "models" / "risk_model.joblib"
    joblib.dump(trainer.model, compat_path)
    logger.info(f"Saved compatibility model to {compat_path}")


if __name__ == "__main__":
    main()
